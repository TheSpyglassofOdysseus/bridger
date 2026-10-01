#!/usr/bin/env bash
set -euo pipefail

if ! command -v ss >/dev/null 2>&1; then
  echo "ss is required (usually provided by iproute2)." >&2
  exit 2
fi

echo "== Listening TCP/UDP sockets =="
ss -H -lntup 2>/dev/null || ss -H -lnt 2>/dev/null || true

cat <<'EOF'

Review every listener bound to 0.0.0.0, *, or [::].
A wildcard bind does not prove the cloud firewall exposes the port, but it
means the process is willing to accept traffic on non-loopback interfaces.
Raw Bridger/Desktop Commander listeners should remain loopback-only.
EOF
