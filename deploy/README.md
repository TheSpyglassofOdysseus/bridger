# Deployment templates

These files are examples for a **new public Bridger installation**. They are not snapshots of the maintainer's production host.

## Public reference layout

- service user: `bridger`
- code: `/opt/bridger`
- service home: `/home/bridger`
- protected environment: `/etc/bridger/bridger.env`

Change those paths consistently if your host uses another layout.

## Start small

For a first interactive deployment, review:

- `bridge-mcp.service`
- `bridge-actions.service`
- `bridge-interactive-facade.service` (optional compact facade)
- `bridge.env.example`
- `nginx-bridge.conf.example` only if you intentionally need a public HTTPS edge

Do not install every unit merely because it exists.

## Compatibility names

The product is **Bridger**. Some service filenames, environment variables, and headers retain the older `bridge-*` / `X-Bridge-Key` names for compatibility. Treat those as stable interface identifiers, not separate products.

## Advanced / optional units

Passrail execution-owner/worker units and the legacy mailbox adapter support durable/scheduled workflows. They are not required for ordinary interactive Bridger use.

The Secure MCP Tunnel unit is client-specific reference material. Use the current official client/provider documentation before installing a tunnel binary or copying a registration flow.

## Systemd security posture

The HTTP Actions and compact-facade templates are intentionally more sandboxed than the raw MCP backend. On the reference systemd version, offline security analysis rates those templates in the "OK" range after hardening.

The MCP/Desktop Commander service still has broader exposure by design because its purpose is authorized host filesystem/process access. Its template removes privilege escalation/capabilities and protects kernel/control-group settings, but does **not** use filesystem/network restrictions that would silently prevent the user-authorized host operations Bridger exists to perform.

Do not interpret a systemd exposure score as proof of safety. The primary boundaries remain: dedicated unprivileged service account, loopback-only raw listener, explicit authentication at the remote edge, and deliberate user authorization.

## Before installing any unit

1. Read it.
2. Confirm every path/user exists.
3. Verify the referenced environment file permissions.
4. Verify the backend binds only to loopback.
5. Run `systemd-analyze verify` when available.
6. Keep a rollback copy of any existing unit you replace.
