#!/usr/bin/env node
import { randomUUID } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';

const BACKEND_PORT = Number(process.env.BRIDGE_DC_PORT || '18877');
const BACKEND_KEY = process.env.MCP_PROXY_API_KEY || '';
const MAX_CHARS = clamp(Number(process.env.BRIDGER_INTERACTIVE_MAX_CHARS || '12000'), 2000, 64000);
const MAX_LINES = clamp(Number(process.env.BRIDGER_INTERACTIVE_MAX_LINES || '200'), 40, 1000);
const CONCURRENCY = clamp(Number(process.env.BRIDGER_INTERACTIVE_CONCURRENCY || '1'), 1, 8);
const ARTIFACT_DIR = process.env.BRIDGER_INTERACTIVE_ARTIFACT_DIR || path.join(os.homedir(), '.local/state/bridger-interactive/artifacts');

fs.mkdirSync(ARTIFACT_DIR, { recursive: true, mode: 0o700 });
try { fs.chmodSync(ARTIFACT_DIR, 0o700); } catch {}

function clamp(value, min, max) {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, Math.trunc(value)));
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", "'\\''")}'`;
}

function resultText(result) {
  if (!result || !Array.isArray(result.content)) return JSON.stringify(result ?? null);
  return result.content
    .filter(item => item && item.type === 'text' && typeof item.text === 'string')
    .map(item => item.text)
    .join('\n');
}

function parsePid(text) {
  const m = String(text).match(/Process started with PID\s+(\d+)/i);
  return m ? Number(m[1]) : null;
}

function looksRunning(text) {
  return /Process is running|Use read_process_output|⏳/i.test(String(text));
}

function looksWaiting(text) {
  return /waiting for input|detected:/i.test(String(text));
}

function writeArtifact(text) {
  const name = `${new Date().toISOString().replaceAll(':','').replaceAll('.','-')}-${randomUUID()}.txt`;
  const target = path.join(ARTIFACT_DIR, name);
  fs.writeFileSync(target, text, { encoding: 'utf8', mode: 0o600, flag: 'wx' });
  return target;
}

function boundText(text) {
  const raw = String(text ?? '');
  const lines = raw.split('\n');
  let clipped = lines.slice(0, MAX_LINES).join('\n');
  if (clipped.length > MAX_CHARS) clipped = clipped.slice(0, MAX_CHARS);
  const truncated = raw.length > clipped.length || lines.length > MAX_LINES;
  if (!truncated) return { text: raw, truncated: false, artifact: null };
  const artifact = writeArtifact(raw);
  return {
    text: `${clipped}\n\n[Bridger truncated this interactive result. Full output: ${artifact}]`,
    truncated: true,
    artifact,
  };
}

function boundedResult(result) {
  const content = Array.isArray(result?.content) ? result.content : [];
  const text = resultText(result);
  const nonText = content.filter(item => item && item.type !== 'text');
  let combined = text;
  if (nonText.length || result?.structuredContent) {
    const artifact = writeArtifact(JSON.stringify({ content: nonText, structuredContent: result?.structuredContent ?? null }, null, 2));
    const note = `[Bridger stored ${nonText.length} non-text block(s) / structured content as an owner-only artifact: ${artifact}]`;
    combined = combined ? `${combined}\n\n${note}` : note;
  }
  const bounded = boundText(combined);
  return {
    content: [{ type: 'text', text: bounded.text }],
    isError: Boolean(result?.isError),
  };
}


if (process.argv.includes('--self-test')) {
  const quoted = shellQuote("a'b");
  if (quoted !== String.raw`'a'\''b'`) throw new Error(`shellQuote self-test failed: ${quoted}`);
  const sample = Array.from({ length: MAX_LINES + 20 }, (_, i) => `line-${i}`).join('\n');
  const bounded = boundText(sample);
  if (!bounded.truncated || !bounded.artifact || !fs.existsSync(bounded.artifact)) throw new Error('boundText self-test failed');
  fs.unlinkSync(bounded.artifact);
  console.log('BRIDGER_INTERACTIVE_SELF_TEST=PASS');
  process.exit(0);
}

if (!BACKEND_KEY) {
  console.error('BRIDGER_INTERACTIVE=FAIL reason=MCP_PROXY_API_KEY_missing');
  process.exit(2);
}

class Backend {
  constructor() {
    this.client = null;
    this.transport = null;
    this.tools = null;
    this.toolsAt = 0;
  }

  async connect() {
    if (this.client) return;
    const client = new Client({ name: 'bridger-interactive-facade', version: '0.1.0' }, { capabilities: {} });
    const transport = new StreamableHTTPClientTransport(new URL(`http://127.0.0.1:${BACKEND_PORT}/mcp`), {
      requestInit: { headers: { 'X-API-Key': BACKEND_KEY } },
    });
    await client.connect(transport);
    this.client = client;
    this.transport = transport;
  }

  async reset() {
    try { await this.transport?.close(); } catch {}
    this.client = null;
    this.transport = null;
    this.tools = null;
    this.toolsAt = 0;
  }

  async call(name, args = {}) {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        await this.connect();
        metrics.backendCalls += 1;
        return await this.client.callTool({ name, arguments: args });
      } catch (error) {
        await this.reset();
        if (attempt) throw error;
      }
    }
  }

  async listTools() {
    if (this.tools && Date.now() - this.toolsAt < 60000) return this.tools;
    await this.connect();
    metrics.backendCalls += 1;
    const listed = await this.client.listTools();
    this.tools = listed.tools || [];
    this.toolsAt = Date.now();
    return this.tools;
  }
}

class Semaphore {
  constructor(limit) { this.limit = limit; this.active = 0; this.waiters = []; }
  async acquire() {
    if (this.active < this.limit) { this.active += 1; return; }
    await new Promise(resolve => this.waiters.push(resolve));
    this.active += 1;
  }
  release() {
    this.active -= 1;
    const next = this.waiters.shift();
    if (next) next();
  }
  async run(fn) {
    await this.acquire();
    try { return await fn(); } finally { this.release(); }
  }
}

const backend = new Backend();
const gate = new Semaphore(CONCURRENCY);
const metrics = { calls: 0, backendCalls: 0, truncated: 0, startedAt: new Date().toISOString() };

const HIGH_LEVEL = [
  {
    name: 'bridger_inspect_repo',
    description: 'Preferred low-chatter repository inspection. Returns pwd, branch/status, remotes, recent commits, and optional bounded diff summary in one call.',
    inputSchema: {
      type: 'object', required: ['path'], additionalProperties: false,
      properties: {
        path: { type: 'string' },
        recent_commits: { type: 'integer', minimum: 1, maximum: 10, default: 5 },
        include_diff: { type: 'boolean', default: false },
      },
    },
  },
  {
    name: 'bridger_inspect_service',
    description: 'Preferred low-chatter systemd diagnosis. Returns active state, key unit properties, and bounded recent warning/error logs in one call.',
    inputSchema: {
      type: 'object', required: ['service'], additionalProperties: false,
      properties: {
        service: { type: 'string' },
        minutes: { type: 'integer', minimum: 1, maximum: 120, default: 15 },
        log_lines: { type: 'integer', minimum: 10, maximum: 100, default: 40 },
      },
    },
  },
  {
    name: 'bridger_read_bundle',
    description: 'Preferred low-chatter file read for up to 8 files. Reads bounded excerpts and returns one compact result.',
    inputSchema: {
      type: 'object', required: ['paths'], additionalProperties: false,
      properties: {
        paths: { type: 'array', minItems: 1, maxItems: 8, items: { type: 'string' } },
        offset: { type: 'integer', default: 0 },
        lines_per_file: { type: 'integer', minimum: 1, maximum: 200, default: 80 },
      },
    },
  },
  {
    name: 'bridger_run_bounded',
    description: 'Preferred terminal tool for ordinary commands. Runs a command and automatically performs a small amount of process polling so the chat usually receives one final bounded result instead of start/poll/poll chatter.',
    inputSchema: {
      type: 'object', required: ['command'], additionalProperties: false,
      properties: {
        command: { type: 'string' },
        timeout_ms: { type: 'integer', minimum: 100, maximum: 30000, default: 12000 },
        poll_rounds: { type: 'integer', minimum: 0, maximum: 4, default: 2 },
      },
    },
  },
  {
    name: 'bridger_edit_file',
    description: 'Preferred focused text edit. Replaces an exact block in one file and returns a bounded result.',
    inputSchema: {
      type: 'object', required: ['file_path', 'old_string', 'new_string'], additionalProperties: false,
      properties: {
        file_path: { type: 'string' }, old_string: { type: 'string' }, new_string: { type: 'string' },
        expected_replacements: { type: 'integer', minimum: 1, maximum: 100, default: 1 },
      },
    },
  },
  {
    name: 'bridger_write_file',
    description: 'Preferred bounded file write/append operation for ordinary text files.',
    inputSchema: {
      type: 'object', required: ['path', 'content'], additionalProperties: false,
      properties: { path: { type: 'string' }, content: { type: 'string' }, mode: { type: 'string', enum: ['rewrite', 'append'], default: 'rewrite' } },
    },
  },
  {
    name: 'bridger_raw_catalog',
    description: 'Advanced fallback discovery. Returns a small matching subset of the hidden raw Desktop Commander tool catalog when the compact Bridger tools do not cover a task.',
    inputSchema: {
      type: 'object', additionalProperties: false,
      properties: { query: { type: 'string', default: '' }, limit: { type: 'integer', minimum: 1, maximum: 10, default: 6 } },
    },
  },
  {
    name: 'bridger_raw_tool',
    description: 'Advanced fallback only. Invoke one hidden raw Desktop Commander tool after consulting bridger_raw_catalog. Prefer compact Bridger tools whenever possible.',
    inputSchema: {
      type: 'object', required: ['name', 'arguments'], additionalProperties: false,
      properties: { name: { type: 'string' }, arguments: { type: 'object', additionalProperties: true } },
    },
  },
  {
    name: 'bridger_stats',
    description: 'Return compact in-memory interactive-facade traffic counters for diagnosing chat/tool pressure.',
    inputSchema: { type: 'object', additionalProperties: false, properties: {} },
  },
];

function annotateRaw(tool) {
  const copy = structuredClone(tool);
  const preferred = tool.name === 'start_process' ? ' Prefer bridger_run_bounded for ordinary commands.'
    : tool.name === 'read_process_output' ? ' Prefer bridger_run_bounded unless a process is genuinely long-running.'
    : tool.name === 'read_file' ? ' Prefer bridger_read_bundle when reading multiple files.' : '';
  copy.description = `[Advanced fallback] ${tool.description || tool.name}.${preferred} Interactive responses are size-bounded.`;
  return copy;
}

function boundedRawArgs(name, args) {
  const out = { ...(args || {}) };
  if (name === 'read_file') out.length = clamp(Number(out.length ?? 200), 1, 200);
  if (name === 'read_process_output') out.length = clamp(Number(out.length ?? 120), 1, 200);
  if (name === 'get_more_search_results') out.length = clamp(Number(out.length ?? 100), 1, 200);
  return out;
}

async function settledProcess(command, timeoutMs, pollRounds) {
  const pieces = [];
  let result = await backend.call('start_process', { command, timeout_ms: timeoutMs, origin: 'llm' });
  pieces.push(resultText(result));
  let text = pieces.at(-1) || '';
  const pid = parsePid(text);
  if (pid && looksRunning(text) && !looksWaiting(text)) {
    for (let i = 0; i < pollRounds; i += 1) {
      result = await backend.call('read_process_output', { pid, offset: 0, length: 120, timeout_ms: 4000 });
      text = resultText(result);
      if (text) pieces.push(text);
      if (!looksRunning(text) || looksWaiting(text) || /finished execution|exit code/i.test(text)) break;
    }
  }
  return { content: [{ type: 'text', text: pieces.filter(Boolean).join('\n') }] };
}

async function highLevel(name, args) {
  if (name === 'bridger_inspect_repo') {
    const commits = clamp(Number(args.recent_commits ?? 5), 1, 10);
    const q = shellQuote(args.path);
    const diff = args.include_diff ? `; echo '=== DIFF STAT ==='; git diff --stat | head -60; echo '=== DIFF NAMES ==='; git diff --name-only | head -80` : '';
    const cmd = `cd ${q} && echo '=== PWD ===' && pwd && echo '=== STATUS ===' && git status --short --branch && echo '=== REMOTES ===' && git remote -v | head -8 && echo '=== RECENT ===' && git log -${commits} --oneline --decorate${diff}`;
    return settledProcess(cmd, 12000, 1);
  }
  if (name === 'bridger_inspect_service') {
    const service = String(args.service || '');
    if (!/^[A-Za-z0-9_.@:-]+$/.test(service)) throw new Error('service contains unsupported characters');
    const minutes = clamp(Number(args.minutes ?? 15), 1, 120);
    const logLines = clamp(Number(args.log_lines ?? 40), 10, 100);
    const q = shellQuote(service);
    const cmd = `echo '=== ACTIVE ==='; systemctl is-active ${q} 2>&1 || true; echo '=== UNIT ==='; systemctl show ${q} -p MainPID -p ActiveEnterTimestamp -p NRestarts -p ExecMainStatus --no-pager 2>&1; echo '=== RECENT WARNINGS ==='; journalctl -u ${q} --since '-${minutes} min' -p warning --no-pager -n ${logLines} 2>&1`;
    return settledProcess(cmd, 12000, 1);
  }
  if (name === 'bridger_read_bundle') {
    const paths = Array.isArray(args.paths) ? args.paths.slice(0, 8) : [];
    const offset = Number.isFinite(Number(args.offset)) ? Math.trunc(Number(args.offset)) : 0;
    const length = clamp(Number(args.lines_per_file ?? 80), 1, 200);
    const out = [];
    for (const file of paths) {
      const result = await backend.call('read_file', { path: String(file), offset, length, origin: 'llm' });
      out.push(`===== ${file} =====\n${resultText(result)}`);
    }
    return { content: [{ type: 'text', text: out.join('\n\n') }] };
  }
  if (name === 'bridger_run_bounded') {
    return settledProcess(String(args.command || ''), clamp(Number(args.timeout_ms ?? 12000), 100, 30000), clamp(Number(args.poll_rounds ?? 2), 0, 4));
  }
  if (name === 'bridger_edit_file') {
    return backend.call('edit_block', {
      file_path: String(args.file_path || ''), old_string: String(args.old_string ?? ''), new_string: String(args.new_string ?? ''),
      expected_replacements: clamp(Number(args.expected_replacements ?? 1), 1, 100), origin: 'llm',
    });
  }
  if (name === 'bridger_write_file') {
    return backend.call('write_file', { path: String(args.path || ''), content: String(args.content ?? ''), mode: args.mode === 'append' ? 'append' : 'rewrite', origin: 'llm' });
  }
  if (name === 'bridger_raw_catalog') {
    const query = String(args.query || '').toLowerCase();
    const limit = clamp(Number(args.limit ?? 6), 1, 10);
    const tools = (await backend.listTools())
      .filter(tool => !query || `${tool.name} ${tool.description || ''}`.toLowerCase().includes(query))
      .slice(0, limit)
      .map(tool => ({ name: tool.name, description: tool.description || '', inputSchema: tool.inputSchema || {} }));
    return { content: [{ type: 'text', text: JSON.stringify(tools) }] };
  }
  if (name === 'bridger_raw_tool') {
    const rawName = String(args.name || '');
    if (!rawName || rawName.startsWith('bridger_')) throw new Error('invalid raw tool name');
    const rawArgs = boundedRawArgs(rawName, args.arguments || {});
    if (rawName === 'start_process' && Number(rawArgs.timeout_ms ?? 0) >= 3000) {
      return settledProcess(String(rawArgs.command || ''), clamp(Number(rawArgs.timeout_ms), 100, 30000), 2);
    }
    return backend.call(rawName, rawArgs);
  }
  if (name === 'bridger_stats') {
    return { content: [{ type: 'text', text: JSON.stringify({ ...metrics, active: gate.active, queued: gate.waiters.length, maxChars: MAX_CHARS, maxLines: MAX_LINES, concurrency: CONCURRENCY, advertisedTools: HIGH_LEVEL.length }) }] };
  }
  throw new Error(`unknown high-level tool: ${name}`);
}

const server = new Server({ name: 'bridger-interactive', version: '0.1.0' }, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: HIGH_LEVEL };
});

server.setRequestHandler(CallToolRequestSchema, async request => {
  const started = Date.now();
  metrics.calls += 1;
  const { name, arguments: args = {} } = request.params;
  let rawResult;
  try {
    if (name === 'bridger_stats') {
      rawResult = await highLevel(name, args);
    } else {
      rawResult = await gate.run(async () => {
        if (HIGH_LEVEL.some(tool => tool.name === name)) return highLevel(name, args);
        const safeArgs = boundedRawArgs(name, args);
        if (name === 'start_process' && Number(safeArgs.timeout_ms ?? 0) >= 3000) {
          return settledProcess(String(safeArgs.command || ''), clamp(Number(safeArgs.timeout_ms), 100, 30000), 2);
        }
        return backend.call(name, safeArgs);
      });
    }
    const result = boundedResult(await rawResult);
    if (result.content[0].text.includes('[Bridger truncated')) metrics.truncated += 1;
    console.error(JSON.stringify({ event: 'tool', name, ms: Date.now() - started, backendCalls: metrics.backendCalls, chars: result.content[0].text.length, active: gate.active, queued: gate.waiters.length }));
    return result;
  } catch (error) {
    console.error(JSON.stringify({ event: 'tool_error', name, ms: Date.now() - started, error: String(error?.message || error) }));
    return { content: [{ type: 'text', text: `Bridger interactive error: ${String(error?.message || error)}` }], isError: true };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
console.error(JSON.stringify({ event: 'ready', backendPort: BACKEND_PORT, maxChars: MAX_CHARS, maxLines: MAX_LINES, concurrency: CONCURRENCY }));
