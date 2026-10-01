# Changelog

## Unreleased

## 0.2.0 — easy setup

- Add a guided ARM64 quick installer that provisions a dedicated Bridger service account, a private Node 22 runtime, pinned dependencies, loopback-only MCP services, generated credentials, Tailscale, health checks, and an AI handoff file.
- Add an OpenAI Secure MCP Tunnel wizard that downloads and checksum-verifies OpenAI's official tunnel client, stores tunnel/MCP credentials in protected local files, runs tunnel diagnostics, and installs the tunnel as a systemd service.
- Add `quick-status`, `tunnel-status`, safe uninstall, and explicit purge/rollback commands.
- Make the beginner path five visible steps: server → Bridger → secure tunnel → ChatGPT plugin → build.
- Add `docs/EASY-SETUP.md` as the default happy path while retaining detailed manual/operator documentation for troubleshooting and advanced configurations.
- Validate the appliance path in a clean ARM64 Debian/systemd environment, including the official Tailscale package path, service startup, authentication boundaries, tunnel dry-run, systemd verification, safe uninstall, and purge.
- Add Personal AI Server Starter onboarding with an AI-readable handoff.
- Document Oracle Always Free/OCI CLI capacity fallback without assuming the original reference allocation.
- Keep domains, public MCP exposure, Passrail, and paid resources optional and outside the default installer.

## 0.1.0 — publication candidate

- Self-hosted Desktop Commander MCP runtime behind `mcp-proxy`.
- Authenticated Bridge Actions facade with named direct operations.
- Private GitHub mailbox transport for Scheduled Tasks.
- Durable pre-execution claims and `unknown_outcome` no-replay semantics.
- Request/receipt binding by source comment, request digest, and tool.
- Explicit conflict receipts for duplicate request IDs with different payloads.
- Unit tests for authentication, idempotency, replay, crash recovery, and receipt spoofing.
