# Bridger

**Self-hosted, controlled machine access for AI clients — with optional durable [Passrail](https://github.com/TheSpyglassofOdysseus/passrail) coordination for scheduled work.**

## New here? Build your own personal AI server

If you want the shortest path, start with [`docs/EASY-SETUP.md`](docs/EASY-SETUP.md): existing ARM64 Linux server → one installer → Tailscale approval → OpenAI tunnel wizard (for ChatGPT) → plugin/app connection → start building. If you want to understand every layer, use [`START_HERE.md`](START_HERE.md). The repository also includes a self-contained static landing page in [`site/index.html`](site/index.html).

The starter path combines a Linux VM (Oracle Cloud is the reference path), Tailscale private networking, optional Cloudflare domain/DNS for intentionally public web services, Git/GitHub for source and recovery, and Bridger as the controlled AI-to-host execution boundary.

**Private by default. Public intentionally.** A domain is optional, and no paid cloud resource or domain purchase should be automated without explicit human approval after current cost is shown.

## Bridger is three pieces

A working Bridger setup has three required layers:

1. **Your server** — a Linux machine you control that stays available after the chat ends.
2. **Bridger MCP on that server** — the server-side program that exposes bounded tools for files, commands, repositories, and services.
3. **Your AI-side connection** — a plugin/app/connector that points your AI client at **your** Bridger MCP endpoint.

For ChatGPT's private path, that third layer has two account-side steps: **OpenAI Secure MCP Tunnel + your personal ChatGPT plugin connection**. The tunnel keeps the MCP server private; the plugin lets your ChatGPT workspace select that tunnel. Each user creates these in their own OpenAI account/workspace. ChatGPT plugin/MCP capabilities depend on plan and workspace permissions. Other MCP-capable clients have their own connection flow.

Bridger does **not** include or share the maintainer's ChatGPT account, API keys, plugin credentials, credits, or usage.

## What you do not need

Bridger is meant to reduce the cost of experimenting with persistent AI compute, not create another shopping list.

- **No dedicated Mac mini or home server.** A small Linux cloud VM can be the always-on machine. You do not need to buy dedicated hardware or leave a desktop running at home.
- **No paid VPS is required to try the reference path.** The starter is designed around Oracle Always Free ARM compute when your account is eligible and capacity is available. As of 2026-10-01 Oracle documents 2 Always Free A1 OCPUs, 12 GB RAM, and 200 GB total combined boot/block storage in the tenancy's home region. The original Bridger server was provisioned under the older 4 OCPU / 24 GB / 200 GB entitlement. Start with [Oracle Free Tier](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm), then use [OCI Cloud Shell](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/cloudshellintro.htm) or the [OCI CLI quickstart](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm) so your AI can inspect the tenancy before provisioning.
- **No purchased domain is required.** Tailscale is enough for private access. If you want a shareable hostname, a free DNS/subdomain service can work; a custom domain is optional.
- **No particular AI mode is built into Bridger.** You bring an AI account/client that supports the MCP actions you need. When your client can operate Bridger outside a limited agent mode, you can reserve that allowance for work that actually needs it. On ChatGPT, plugin/full-MCP availability depends on plan and workspace permissions; Bridger does not bypass provider usage limits or billing.

You can start small, learn the system, and spend money only when a real requirement justifies it.

AI assistants should read [`AI_HANDOFF.md`](AI_HANDOFF.md) before guiding a deployment. The design decisions and objections behind the starter are recorded in [`docs/STARTER-COUNTER-REVIEW.md`](docs/STARTER-COUNTER-REVIEW.md).

Bridger turns a machine you control into a small, auditable machine-execution boundary without depending on a hosted remote-desktop relay. It reuses the upstream Desktop Commander MCP tool surface and keeps the raw machine backend on loopback.

**Start with interactive Bridger.** [Passrail](docs/PASSRAIL.md) is the optional durable-work layer for scheduled/unattended workflows; it is not required to give an AI controlled access to your server.

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

Bridger is intended for Linux hosts with systemd and Python 3.11+. **v0.2 is release-certified on ARM64 Ubuntu/Debian for the easy installer; x86_64 remains experimental until independently clean-room tested.** The easy installer brings its own private Node.js 22 runtime, so it does not replace system Node.

Use [`docs/EASY-SETUP.md`](docs/EASY-SETUP.md):

1. get an ARM64 Linux server;
2. run `scripts/quick-install.sh`;
3. authorize Tailscale;
4. for ChatGPT, run `scripts/setup-openai-tunnel.sh`;
5. select that tunnel when creating your personal ChatGPT plugin connection;
6. run harmless canaries and start building.

The manual beginner/operator docs remain available for unsupported distributions, troubleshooting, and advanced Passrail/public-web configurations.

## Status

The reference deployment has exercised the interactive facade, direct Passrail path, replay/ambiguity protections, service restarts, and cold-start operations. The public starter intentionally presents a smaller first-run surface than the maintainer deployment.

Bridger is intentionally small. It is not a remote desktop UI, not an autonomous coding agent, not a generic workflow engine, and not a claim of sandboxed or exactly-once AI control. It is a controlled execution boundary for tools you deliberately authorize.

## Security

Remote operations are inherently privileged. The legacy `X-Bridge-Key` is high-authority machine control; the narrow Passrail key is lower authority but still security-sensitive. Read [`SECURITY.md`](SECURITY.md) and [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md) before exposing Bridger beyond localhost.

## License

MIT. See [`LICENSE`](LICENSE). Third-party packages retain their own licenses; see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
