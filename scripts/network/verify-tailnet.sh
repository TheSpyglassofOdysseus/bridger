#!/usr/bin/env bash
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale command not found." >&2
  exit 2
fi

echo "== Tailscale version =="
tailscale version | head -1

echo
echo "== Tailscale addresses =="
tailscale ip -4 2>/dev/null || true
tailscale ip -6 2>/dev/null || true

echo
echo "== Tailnet status =="
if command -v jq >/dev/null 2>&1; then
  tailscale status --json | jq '{
    BackendState,
    TailscaleIPs,
    Self: {
      HostName: .Self.HostName,
      DNSName: .Self.DNSName,
      Online: .Self.Online,
      ExitNode: .Self.ExitNode
    }
  }'
else
  tailscale status
fi

cat <<'EOF'

This verifies local Tailscale state only. Also test connectivity from the
trusted client you intend to use for administration.
EOF
