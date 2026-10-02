# Quick start

New to server administration or handing this repository to another AI user? Begin with [../START_HERE.md](../START_HERE.md) and [../AI_HANDOFF.md](../AI_HANDOFF.md).

This is the operator-focused reference deployment, not a one-command root installer. The **interactive Bridger path works without Passrail**. Add the durable/scheduled Passrail layer only after the interactive path is healthy.

## Prerequisites

- Linux with systemd
- Python 3.11+
- Node.js 22+ and npm
- nginx, Caddy, or another TLS reverse proxy when a public HTTPS edge is required
- a dedicated service account (examples use `bridger`)
- GitHub CLI (`gh`) only if using the legacy scheduled-mailbox compatibility adapter

## 1. Install the code

The public templates assume:

- code: `/opt/bridger`
- service user: `bridger`
- service home: `/home/bridger`
- protected environment: `/etc/bridger/bridger.env`

Create/adapt those paths for your host. Install the pinned Node runtime dependencies:

```bash
cd /opt/bridger/selfhosted
npm ci
```

## 2. Configure secrets

Copy `deploy/bridge.env.example` to `/etc/bridger/bridger.env`, replace every placeholder you actually use, and restrict it so only root and the Bridger service account can read it.

Generate independent high-entropy values for `MCP_PROXY_API_KEY` and `BRIDGE_ACTIONS_KEY`. Keep Passrail variables unset/unused until you intentionally enable the advanced durable-work layer.

## 3. Start the interactive core first

Review the files in `deploy/` before installing them.

For the initial interactive deployment, the important pieces are:

- `bridge-mcp.service` — loopback-only Desktop Commander MCP backend;
- `bridge-actions.service` — authenticated loopback Actions facade for clients that need it;
- `bridge-interactive-facade.service` — optional compact low-chatter MCP facade.

Confirm raw MCP listeners bind only to loopback before creating any remote edge.

## 4. Connect an AI client

Client connection mechanisms evolve independently from Bridger. Read [beginner/06-connect-your-ai.md](beginner/06-connect-your-ai.md) and use the **current official documentation for your AI client** rather than copying stale registration/tunnel steps.

The invariant is stable: the client reaches a bounded/authenticated Bridger edge; the raw Desktop Commander backend stays loopback-only.

## 5. Test the core

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q selfhosted tests
scripts/check.sh
```

Then prove harmless canaries such as reading `/etc/hostname` and running a bounded `printf bridger-probe`.

## 6. Add Passrail only if you need durable/scheduled work

[Passrail](PASSRAIL.md) is **optional durable-work infrastructure**. It adds durable work identity, claims/leases, retry policy, and explicit `UNKNOWN_OUTCOME` handling. It is not required for ordinary interactive AI-to-server work. The standalone public project and installer live at https://github.com/TheSpyglassofOdysseus/passrail.

If you enable it, review [ARCHITECTURE.md](ARCHITECTURE.md) and [THREAT-MODEL.md](THREAT-MODEL.md) before installing the advanced execution-owner/worker pieces.

## 7. Public exposure is a separate decision

A Tailscale-only deployment is complete. If you intentionally publish a web/API edge, use [beginner/07-cloudflare-domain-dns.md](beginner/07-cloudflare-domain-dns.md) and [beginner/08-public-web.md](beginner/08-public-web.md).

Do not expose the raw MCP listener, databases, SSH, or administrative dashboards merely for convenience.
