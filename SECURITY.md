# Security policy

Bridger can execute filesystem and process operations on a host. Treat deployment configuration as privileged infrastructure.

## Supported version

Security fixes target the latest public release and `main`.

## Reporting a vulnerability

Do **not** post credentials, tokens, private hostnames/IPs, mailbox contents, exploit details, or proof-of-concept code in a public issue.

Use GitHub **Private Vulnerability Reporting** / Security Advisories for the public repository when available. If private reporting is unavailable, open only a minimal public issue asking maintainers to enable a private reporting channel; do not include technical vulnerability details.

## Public/private boundary

The public Bridger repository is source code and documentation only.

A normal Bridger installation does **not** require access to any maintainer-operated server, Tailnet, domain, mailbox, database, or control plane. Public examples must use synthetic identifiers and placeholders.

Do not copy account IDs, tunnel registrations, plugin IDs, OAuth client identifiers, Tailscale device names, cloud resource identifiers, production hostnames, or credentials from another deployment.

The interactive core is designed to run on infrastructure the user controls. Optional providers such as Oracle Cloud, Tailscale, Cloudflare, GitHub, and an AI client remain separate third-party trust boundaries with their own security and privacy policies.

## Deployment rules

- Keep MCP, Actions, Passrail, cloud, tunnel, and AI-client secrets out of Git, logs, screenshots, shell history, and issue/PR comments.
- Bind the raw MCP runtime to loopback and terminate any required remote authentication/TLS at a controlled edge.
- Prefer Tailscale or another private network for administration. Public exposure is a separate deliberate decision.
- Use a dedicated OS account and least-privilege filesystem/process policy appropriate to the host.
- Keep the high-authority interactive credential separate from lower-authority scheduled/durable-work credentials.
- Do not expose SSH, databases, raw MCP/Desktop Commander, or administrative dashboards publicly merely for convenience.
- Treat `UNKNOWN_OUTCOME` as a reconciliation state. Never automatically replay a mutating request whose outcome is ambiguous.
- Before repeating a consequential operation after a timeout or lost response, inspect actual state.
- Rotate/revoke any secret immediately if it is accidentally disclosed.
- Backups are not considered valid until a restore has been tested.
- Preserve a recovery path that does not depend on the same credential or service being recovered.

## Release hygiene

The private development repository is **not** the public release artifact. Public releases are generated as a fresh, one-commit export and scanned for private coordinates and secret material before publication.

The public release must not include:

- maintainer production hostnames/IPs;
- cloud tenancy/resource IDs;
- personal email addresses or domains unrelated to Bridger;
- operational logs/receipts;
- private research/issues/PRs;
- live tunnel/plugin/app registration IDs;
- real API keys, SSH keys, certificates, or environment files.

See `docs/THREAT-MODEL.md` and `docs/RELEASE.md` for additional controls.
