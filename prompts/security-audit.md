# Security-audit prompt

```text
Audit this Bridger starter deployment without changing it.

Read SECURITY.md, docs/THREAT-MODEL.md, AI_HANDOFF.md, and
docs/STARTER-ARCHITECTURE.md.

Inspect:
- listening sockets and cloud/public exposure;
- whether raw MCP/Desktop Commander is loopback-only;
- SSH authentication posture;
- Tailscale state;
- secret file ownership/permissions;
- systemd services and failure state;
- reverse-proxy configuration;
- repositories for accidentally tracked secrets/private coordinates;
- backup freshness and the most recent restore test;
- disk capacity and security-update status;
- current documented cost/free-tier assumptions.

Separate observations from recommendations. Mark anything you cannot verify as
UNKNOWN rather than assuming it is safe. Do not mutate the host during the audit.
```
