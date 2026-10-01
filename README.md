# Bridger

**Self-hosted, controlled machine access for AI clients — with optional durable Passrail coordination for scheduled work.**

## New here? Build your own personal AI server

If you are comfortable with AI but not necessarily a Linux/sysadmin expert, start with [`START_HERE.md`](START_HERE.md). The repository also includes a self-contained static landing page in [`site/index.html`](site/index.html) with a copyable one-shot prompt for AI-assisted setup.

The starter path combines a Linux VM (Oracle Cloud is the reference path), Tailscale private networking, optional Cloudflare domain/DNS for intentionally public web services, Git/GitHub for source and recovery, and Bridger as the controlled AI-to-host execution boundary.

**Private by default. Public intentionally.** A domain is optional, and no paid cloud resource or domain purchase should be automated without explicit human approval after current cost is shown.

AI assistants should read [`AI_HANDOFF.md`](AI_HANDOFF.md) before guiding a deployment. The design decisions and objections behind the starter are recorded in [`docs/STARTER-COUNTER-REVIEW.md`](docs/STARTER-COUNTER-REVIEW.md).

Bridger turns a machine you control into a small, auditable machine-execution boundary without depending on a hosted remote-desktop relay. It reuses the upstream Desktop Commander MCP tool surface and keeps the raw machine backend on loopback.

**Start with interactive Bridger.** Passrail is an optional advanced layer for durable/scheduled work; it is not required to give an AI controlled access to your server.

Some filenames, service names, environment variables, and headers retain the older `bridge-*` / `X-Bridge-Key` identifiers for compatibility. The product name is Bridger.

## Interactive stability

For multi-chat use, Bridger can place a low-chatter compatibility facade in front of Desktop Commander. Fresh chats discover a compact Bridger tool surface instead of the full backend catalog, while legacy raw tool names remain accepted for already-open sessions. The facade adds bounded repo/service/file/command operations, response-size limits, and host-side backpressure. See [`docs/INTERACTIVE-FACADE.md`](docs/INTERACTIVE-FACADE.md). Scheduled Passrail execution is unaffected.

## Why Bridger exists

AI is much more useful when it can safely reach a machine that persists after the chat ends. Bridger provides that controlled machine boundary: authenticated access, bounded tools, loopback-only raw backend, and explicit operational limits.

For users who later need unattended or scheduled work, the optional Passrail integration adds durable work identity, claims/leases, retry policy, and explicit `UNKNOWN_OUTCOME` handling. GitHub may remain source/review/release authority; it does not need to become the runtime command bus.

The legacy GitHub mailbox adapter remains source-level compatibility/migration code rather than the recommended new-user architecture.

## Architecture

```text
Interactive client -> TLS edge -> legacy Actions/MCP -------------------+
                                                                          |
Scheduled/app client -> narrow Passrail ingress -> Passrail SQLite        |
                                                -> local claim/grant       |
                                                -> owner-only Unix socket  |
                                                                          v
                                         execution-attempt ledger -> loopback MCP
                                                                          |
                                                                          v
                                                               Desktop Commander
                                                                          |
                                                                          v
                                                                     managed host
```

## Safety properties

- MCP backend binds to loopback behind your TLS/authentication edge.
- The narrow `X-Passrail-Key` is different from the legacy high-authority `X-Bridge-Key` and cannot authenticate machine-control routes.
- Narrow ingress is project-allowlisted and accepts only `bridger-executor` envelopes.
- Passrail claim tokens terminate at Passrail; they are never sent to Bridger.
- A short-lived HMAC execution grant binds one live Passrail claim to an exact work/envelope/attempt/execution/request/risk identity, and expires no later than the claim lease.
- Direct Passrail -> Bridger execution uses an owner-only Unix socket with same-UID `SO_PEERCRED` verification; it opens no new TCP listener.
- The execution ledger persists `EXECUTING` before machine dispatch and binds attempts to request/tool plus Passrail authority when present.
- Exact authorized replay returns existing terminal evidence rather than repeating the host effect; changed request or authority hard-conflicts.
- Consequential direct work requires `NO_AUTO_RETRY` and project authority/version evidence.
- A crash, lost response, or ambiguous host result becomes `UNKNOWN_OUTCOME`; Bridger does not blindly replay it.
- A successful consequential machine call does not by itself make Passrail `DONE`; project postcondition reconciliation is required and preserves the ambiguity history.
- Legacy GitHub compatibility traffic and direct Passrail traffic share the same execution ledger, preventing competing runtime authorities.

## Components

- `@wonderwhy-er/desktop-commander@0.2.50` — upstream MCP filesystem/process/search/editing engine.
- `mcp-proxy@6.7.18` — HTTP MCP transport bound to loopback.
- `selfhosted/bridge-gpt-actions.py` — legacy interactive Actions plus the separate narrow Passrail ingress surface.
- `selfhosted/bridge_passrail_ingress.py` — allowlisted publish/status-only scheduled/app capability.
- `selfhosted/passrail_direct_worker.py` — local Passrail claimant and settlement adapter.
- `selfhosted/bridge_execution_grant.py` — exact-request execution-grant validation.
- `selfhosted/bridge_direct_socket.py` — owner-only same-UID Unix socket transport.
- `selfhosted/bridge_execution_ledger.py` — transport-neutral attempt identity, replay defense, crash recovery, and evidence.
- `selfhosted/bridge_scheduled_mailbox.py` — private-GitHub compatibility adapter and current single execution-ledger owner during migration.

Both upstream Node dependencies are pinned and MIT-licensed.

## Quick start

Bridger is intended for Linux hosts with systemd, Python 3.11+, and Node.js 22+. **v0.1 is release-certified on ARM64 Linux; x86_64 is experimental until independently clean-room tested.** A public reverse proxy is optional; a Tailscale-only private deployment is complete.

1. Start with [`START_HERE.md`](START_HERE.md).
2. Install the interactive core using [`docs/beginner/05-install-bridger.md`](docs/beginner/05-install-bridger.md).
3. Connect your AI using [`docs/beginner/06-connect-your-ai.md`](docs/beginner/06-connect-your-ai.md).
4. Run `scripts/check.sh` and harmless read/process canaries.
5. Add Passrail only if you actually need durable/scheduled work.

## Status

The reference deployment has exercised the interactive facade, direct Passrail path, replay/ambiguity protections, service restarts, and cold-start operations. The public starter intentionally presents a smaller first-run surface than the maintainer deployment.

Bridger is intentionally small. It is not a remote desktop UI, not an autonomous coding agent, not a generic workflow engine, and not a claim of sandboxed or exactly-once AI control. It is a controlled execution boundary for tools you deliberately authorize.

## Security

Remote operations are inherently privileged. The legacy `X-Bridge-Key` is high-authority machine control; the narrow Passrail key is lower authority but still security-sensitive. Read [`SECURITY.md`](SECURITY.md) and [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md) before exposing Bridger beyond localhost.

## License

MIT. See [`LICENSE`](LICENSE). Third-party packages retain their own licenses; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
