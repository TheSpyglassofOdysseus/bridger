#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${BRIDGER_TUNNEL_ENV_FILE:-/etc/bridger/openai-tunnel.env}"
SERVICE="${BRIDGER_TUNNEL_SERVICE:-bridger-openai-tunnel.service}"
HEALTH_FILE="${BRIDGER_TUNNEL_HEALTH_FILE:-/run/bridger-tunnel/health.url}"

line() { printf '%-24s %s\n' "$1" "$2"; }

echo "Bridger OpenAI tunnel status"
echo "============================"

state="$(systemctl is-active "$SERVICE" 2>/dev/null || true)"
line "Service" "${state:-not installed}"

tunnel_id=""
if [[ -r "$ENV_FILE" ]]; then
  tunnel_id="$(sed -n 's/^CONTROL_PLANE_TUNNEL_ID=//p' "$ENV_FILE" | head -1)"
fi
line "Tunnel ID" "${tunnel_id:-not configured}"

if [[ -s "$HEALTH_FILE" ]]; then
  base="$(cat "$HEALTH_FILE")"
  line "Health base" "$base"
  if curl -fsS --max-time 2 "$base/healthz" >/dev/null 2>&1; then
    line "Health" "PASS"
  else
    line "Health" "FAIL"
  fi
  if curl -fsS --max-time 2 "$base/readyz" >/dev/null 2>&1; then
    line "Ready" "PASS"
  else
    line "Ready" "FAIL"
  fi
else
  line "Health URL" "not available"
fi

code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:18879/mcp || true)"
if [[ "$code" == "401" ]]; then
  line "Local MCP auth" "PASS (unauthenticated request rejected)"
else
  line "Local MCP auth" "HTTP ${code:-unreachable}"
fi

echo
echo "Credentials are intentionally not displayed."
echo "OpenAI tunnel settings: https://platform.openai.com/settings/organization/tunnels"
echo "ChatGPT plugins:        https://chatgpt.com/plugins"
