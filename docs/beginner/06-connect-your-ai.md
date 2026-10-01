# 6. Connect your AI

Bridger is intentionally **AI-client agnostic**, but the easiest documented ChatGPT path is now automated.

The stable rule is:

> The remote AI reaches an authenticated Bridger edge. The raw Desktop Commander MCP backend stays on loopback.

Do not solve connectivity by opening ports 18877 or 18879 to the public Internet.

## ChatGPT: recommended private path

If you used the Bridger easy installer, run:

```bash
sudo /opt/bridger/scripts/setup-openai-tunnel.sh
```

The wizard uses OpenAI Secure MCP Tunnel so your private Bridger server does not need a public MCP listener.

The human/account steps are:

1. open OpenAI Platform tunnel settings;
2. create a tunnel in your own Platform organization/workspace;
3. create a runtime API key with the tunnel permissions OpenAI currently requires;
4. let the Bridger tunnel wizard validate and install the client;
5. open ChatGPT Plugins;
6. create a developer-mode plugin/app;
7. choose **Tunnel** for Connection;
8. select your tunnel or paste its `tunnel_id`;
9. review the discovered tools before enabling the connection.

Current OpenAI entry points:

- Tunnel settings: https://platform.openai.com/settings/organization/tunnels
- ChatGPT Plugins: https://chatgpt.com/plugins
- Secure MCP Tunnel docs: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- Developer mode / MCP app availability: https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt

OpenAI account/workspace capabilities change independently from Bridger. Confirm your account can create the required MCP/plugin connection before spending time provisioning infrastructure.

## What the tunnel wizard handles

The wizard:

- downloads the latest official `openai/tunnel-client` Linux release;
- verifies it against OpenAI's published SHA-256 manifest;
- stores the OpenAI runtime key in a protected local file;
- stores Bridger's local MCP credential separately;
- configures the tunnel to reach `http://127.0.0.1:18879/mcp`;
- sends Bridger's `X-API-Key` only to that local MCP origin using a file reference;
- runs `tunnel-client doctor --explain`;
- installs a hardened systemd service;
- waits for the tunnel `/readyz` endpoint before declaring success.

It does **not** copy the maintainer's tunnel, plugin ID, API key, account, credits, or usage.

Check it with:

```bash
sudo /opt/bridger/scripts/tunnel-status.sh
```

## Other AI clients

Other MCP-capable clients use their own connection/authentication flow.

Possible patterns include:

- a client on your own device reaching Bridger over Tailscale;
- another vendor's supported private MCP tunnel;
- a deliberately configured authenticated HTTPS edge.

The invariant stays the same: keep the raw MCP backend private and expose only the bounded/authenticated edge the client actually needs.

## First canary

Once your AI connection exists, start read-only:

```text
Inspect my Bridger deployment without changing anything.
Read /etc/hostname, inspect the Bridger services, and verify that the raw MCP
backend and compact facade are still loopback-only. Report any problem before
making changes.
```

Then give the AI:

```bash
cat /home/bridger/BRIDGER-HANDOFF.txt
```

The handoff intentionally excludes credentials.

## Do not call it connected until

- the intended AI client can discover Bridger's bounded tool surface;
- a harmless read/process canary succeeds;
- a missing/wrong credential fails closed;
- raw MCP remains loopback-only;
- the tunnel reports ready (when using the ChatGPT tunnel path);
- you know how to revoke/rotate the remote credential.

A domain and Passrail remain optional.
