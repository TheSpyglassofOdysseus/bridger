#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${BRIDGER_ENV_FILE:-/etc/bridger/bridger.env}"
INSTALL_DIR="${BRIDGER_INSTALL_DIR:-/opt/bridger}"
RUNTIME_DIR="${BRIDGER_RUNTIME_DIR:-/opt/bridger-runtime}"

line() { printf '%-30s %s\n' "$1" "$2"; }

echo "Bridger status"
echo "=============="

ref="unknown"
if [[ -r "$INSTALL_DIR/.bridger-install-ref" ]]; then
  ref="$(cat "$INSTALL_DIR/.bridger-install-ref")"
fi
line "Installed source" "$ref"

if [[ -x "$RUNTIME_DIR/node/bin/node" ]]; then
  line "Private Node" "$("$RUNTIME_DIR/node/bin/node" --version)"
else
  line "Private Node" "missing"
fi

for service in bridge-mcp.service bridge-interactive-facade.service; do
  state="$(systemctl is-active "$service" 2>/dev/null || true)"
  line "$service" "${state:-not installed}"
done

echo
echo "Listeners"
echo "---------"
listeners="$(ss -lntH 2>/dev/null | grep -E ':(18877|18879)([[:space:]]|$)' || true)"
if [[ -n "$listeners" ]]; then
  awk '{print $4}' <<<"$listeners"
else
  echo "No Bridger listeners detected."
fi

if grep -Eq '(0\.0\.0\.0|\[::\]|\*):(18877|18879)([[:space:]]|$)' <<<"$listeners"; then
  echo "Boundary: WARNING — a Bridger listener appears wildcard-bound." >&2
else
  echo "Boundary: loopback-only for detected Bridger ports."
fi

echo
echo "Authentication"
echo "--------------"
code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:18879/mcp || true)"
if [[ "$code" == "401" ]]; then
  echo "Unauthenticated facade request: rejected (401) ✓"
else
  echo "Unauthenticated facade request: HTTP ${code:-unreachable}"
fi
if [[ -s "$ENV_FILE" ]]; then
  echo "Credential file: present (value not shown)"
else
  echo "Credential file: missing"
fi

echo
echo "Tailscale"
echo "---------"
if command -v tailscale >/dev/null 2>&1; then
  tailscale status --json 2>/dev/null | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    print("installed; status unavailable")
    raise SystemExit
s=d.get("Self",{})
print("state:", d.get("BackendState","unknown"))
print("online:", s.get("Online",False))
print("dns:", s.get("DNSName") or "not assigned")' || true
else
  echo "not installed"
fi

echo
echo "OpenAI tunnel"
echo "-------------"
tunnel_state="$(systemctl is-active bridger-openai-tunnel.service 2>/dev/null || true)"
if [[ "$tunnel_state" == "active" ]]; then
  line "Tunnel service" "active"
  if [[ -s /run/bridger-tunnel/health.url ]]; then
    tunnel_health="$(cat /run/bridger-tunnel/health.url)"
    ready_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "$tunnel_health/readyz" || true)"
    if [[ "$ready_code" == "200" ]]; then
      line "Tunnel ready" "yes"
    else
      line "Tunnel ready" "no (HTTP ${ready_code:-unreachable})"
    fi
  fi
  if [[ -r /etc/bridger/openai-tunnel.env ]]; then
    sed -n 's/^CONTROL_PLANE_TUNNEL_ID=/Tunnel ID: /p' /etc/bridger/openai-tunnel.env
  fi
else
  line "Tunnel service" "not configured"
fi

echo
echo "Next"
echo "----"
echo "Local compact MCP: http://127.0.0.1:18879/mcp"
echo "AI handoff: /home/bridger/BRIDGER-HANDOFF.txt"
if [[ "$tunnel_state" != "active" ]]; then
  echo "ChatGPT tunnel setup: sudo /opt/bridger/scripts/setup-openai-tunnel.sh"
fi
echo "Secrets are intentionally not displayed."

exit 0
