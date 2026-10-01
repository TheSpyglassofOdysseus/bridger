#!/usr/bin/env bash
set -euo pipefail

BRIDGER_INSTALL_DIR="${BRIDGER_INSTALL_DIR:-/opt/bridger}"
BRIDGER_TUNNEL_DIR="${BRIDGER_TUNNEL_DIR:-/opt/bridger-tunnel}"
BRIDGER_ENV_DIR="${BRIDGER_ENV_DIR:-/etc/bridger}"
BRIDGER_HOME="${BRIDGER_HOME:-/home/bridger}"
BRIDGER_USER="${BRIDGER_USER:-bridger}"
BRIDGER_GROUP="${BRIDGER_GROUP:-bridger}"
BRIDGER_TUNNEL_NONINTERACTIVE="${BRIDGER_TUNNEL_NONINTERACTIVE:-0}"
BRIDGER_TUNNEL_SKIP_DOCTOR="${BRIDGER_TUNNEL_SKIP_DOCTOR:-0}"
BRIDGER_TUNNEL_SKIP_START="${BRIDGER_TUNNEL_SKIP_START:-0}"

log() { printf '\n[%s] %s\n' "Bridger Tunnel" "$*"; }
ok() { printf '  ✓ %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*" >&2; }
die() { printf '  ✗ %s\n' "$*" >&2; exit 1; }

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    command -v sudo >/dev/null 2>&1 || die "Run as root or with sudo."
    exec sudo --preserve-env=BRIDGER_INSTALL_DIR,BRIDGER_TUNNEL_DIR,BRIDGER_ENV_DIR,BRIDGER_HOME,BRIDGER_USER,BRIDGER_GROUP,BRIDGER_TUNNEL_NONINTERACTIVE,BRIDGER_TUNNEL_SKIP_DOCTOR,BRIDGER_TUNNEL_SKIP_START,BRIDGER_TUNNEL_ID,BRIDGER_TUNNEL_API_KEY bash "$0" "$@"
  fi
}

require_bridger() {
  [[ -x "$BRIDGER_INSTALL_DIR/scripts/quick-status.sh" ]] || die "Bridger quick install is not present at $BRIDGER_INSTALL_DIR."
  systemctl is-active --quiet bridge-interactive-facade.service || die "Bridger compact facade is not running."
  [[ -r "$BRIDGER_ENV_DIR/bridger.env" ]] || die "Missing $BRIDGER_ENV_DIR/bridger.env."
  id "$BRIDGER_USER" >/dev/null 2>&1 || die "Missing service user: $BRIDGER_USER"
}

detect_arch() {
  case "$(uname -m)" in
    aarch64|arm64) TUNNEL_ARCH=arm64 ;;
    x86_64|amd64) TUNNEL_ARCH=amd64 ;;
    *) die "OpenAI tunnel helper does not support architecture: $(uname -m)" ;;
  esac
}

install_dependencies() {
  local missing=0
  for cmd in curl unzip python3 sha256sum; do
    command -v "$cmd" >/dev/null 2>&1 || missing=1
  done
  if [[ "$missing" == "1" ]]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl unzip python3 coreutils >/dev/null
  fi
}

install_tunnel_client() {
  log "Installing OpenAI's official tunnel-client"
  local tmp sums asset tag
  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp:-}"' RETURN

  sums="$tmp/SHA256SUMS.txt"
  curl -fsSL https://github.com/openai/tunnel-client/releases/latest/download/SHA256SUMS.txt -o "$sums"
  asset="$(awk -v suffix="-linux-$TUNNEL_ARCH.zip" '$2 ~ /^tunnel-client-v/ && $2 ~ suffix"$" {print $2; exit}' "$sums")"
  [[ -n "$asset" ]] || die "Could not locate the current OpenAI tunnel-client asset for linux-$TUNNEL_ARCH."
  tag="$(sed -E 's/^tunnel-client-(v[^-]+)-linux-.*/\1/' <<<"$asset")"

  curl -fsSL "https://github.com/openai/tunnel-client/releases/latest/download/$asset" -o "$tmp/$asset"
  (cd "$tmp" && grep "  $asset$" SHA256SUMS.txt | sha256sum -c - >/dev/null)
  unzip -q "$tmp/$asset" -d "$tmp/unpacked"

  install -d -o root -g root -m 0755 "$BRIDGER_TUNNEL_DIR"
  install -o root -g root -m 0755 "$tmp/unpacked/tunnel-client" "$BRIDGER_TUNNEL_DIR/tunnel-client"
  [[ -f "$tmp/unpacked/LICENSE" ]] && install -o root -g root -m 0644 "$tmp/unpacked/LICENSE" "$BRIDGER_TUNNEL_DIR/LICENSE"
  [[ -f "$tmp/unpacked/NOTICE" ]] && install -o root -g root -m 0644 "$tmp/unpacked/NOTICE" "$BRIDGER_TUNNEL_DIR/NOTICE"

  "$BRIDGER_TUNNEL_DIR/tunnel-client" --version >/dev/null 2>&1 || true
  ok "Installed OpenAI tunnel-client $tag with checksum verification"
}

read_mcp_key_to_file() {
  local envfile="$BRIDGER_ENV_DIR/bridger.env"
  local keyfile="$BRIDGER_ENV_DIR/mcp-api-key"
  local value

  value="$(python3 - "$envfile" <<'PY'
from pathlib import Path
import sys
for line in Path(sys.argv[1]).read_text().splitlines():
    if line.startswith("MCP_PROXY_API_KEY="):
        print(line.split("=",1)[1], end="")
        raise SystemExit
raise SystemExit(1)
PY
)" || die "Could not read MCP_PROXY_API_KEY from $envfile."

  [[ -n "$value" ]] || die "MCP_PROXY_API_KEY is empty."
  (
    umask 0027
    printf '%s' "$value" >"$keyfile"
  )
  chown root:"$BRIDGER_GROUP" "$keyfile"
  chmod 0640 "$keyfile"
  unset value
  ok "Prepared local MCP credential file for tunnel-only use"
}

collect_openai_values() {
  log "OpenAI account step"
  cat <<'EOF'

ACTION REQUIRED IN YOUR BROWSER

1. Open:
   https://platform.openai.com/settings/organization/tunnels

2. Create a tunnel for this Bridger server.
   Associate it with the ChatGPT workspace you intend to use.

3. Create a runtime API key that has Tunnels Read + Use.
   Keep Tunnels Manage/Admin authority separate unless you actually need it.

You will paste the tunnel ID normally.
The runtime API key is entered silently and stored in a protected local file.
EOF

  local tunnel_id api_key
  if [[ -n "${BRIDGER_TUNNEL_ID:-}" ]]; then
    tunnel_id="$BRIDGER_TUNNEL_ID"
  elif [[ "$BRIDGER_TUNNEL_NONINTERACTIVE" == "1" ]]; then
    die "BRIDGER_TUNNEL_ID is required in noninteractive mode."
  else
    read -r -p "Tunnel ID (tunnel_...): " tunnel_id
  fi

  [[ "$tunnel_id" =~ ^tunnel_[0-9a-f]{32}$ ]] || die "Tunnel ID must be tunnel_ followed by 32 lowercase hexadecimal characters."

  if [[ -n "${BRIDGER_TUNNEL_API_KEY:-}" ]]; then
    api_key="$BRIDGER_TUNNEL_API_KEY"
  elif [[ "$BRIDGER_TUNNEL_NONINTERACTIVE" == "1" ]]; then
    die "BRIDGER_TUNNEL_API_KEY is required in noninteractive mode."
  else
    read -r -s -p "Tunnel runtime API key: " api_key
    printf '\n'
  fi

  [[ -n "$api_key" ]] || die "Tunnel runtime API key cannot be empty."

  install -d -o root -g "$BRIDGER_GROUP" -m 0750 "$BRIDGER_ENV_DIR"
  (
    umask 0027
    printf '%s' "$api_key" >"$BRIDGER_ENV_DIR/openai-tunnel-api-key"
  )
  chown root:"$BRIDGER_GROUP" "$BRIDGER_ENV_DIR/openai-tunnel-api-key"
  chmod 0640 "$BRIDGER_ENV_DIR/openai-tunnel-api-key"
  unset api_key BRIDGER_TUNNEL_API_KEY

  (
    umask 0027
    cat >"$BRIDGER_ENV_DIR/openai-tunnel.env" <<EOF
CONTROL_PLANE_TUNNEL_ID=$tunnel_id
CONTROL_PLANE_API_KEY=file:$BRIDGER_ENV_DIR/openai-tunnel-api-key
MCP_SERVER_URL=http://127.0.0.1:18879/mcp
MCP_EXTRA_HEADERS="X-API-Key: file:$BRIDGER_ENV_DIR/mcp-api-key"
MCP_DISCOVERY_EXTRA_HEADERS="X-API-Key: file:$BRIDGER_ENV_DIR/mcp-api-key"
HEALTH_LISTEN_ADDR=127.0.0.1:0
HEALTH_URL_FILE=/run/bridger-tunnel/health.url
EOF
  )
  chown root:"$BRIDGER_GROUP" "$BRIDGER_ENV_DIR/openai-tunnel.env"
  chmod 0640 "$BRIDGER_ENV_DIR/openai-tunnel.env"

  TUNNEL_ID="$tunnel_id"
  ok "Tunnel identity and runtime credential stored locally"
}

doctor() {
  [[ "$BRIDGER_TUNNEL_SKIP_DOCTOR" == "1" ]] && { warn "Skipping OpenAI tunnel doctor by request."; return; }

  log "Running OpenAI tunnel diagnostics"
  local envfile="$BRIDGER_ENV_DIR/openai-tunnel.env"
  local tunnel_id
  tunnel_id="$(sed -n 's/^CONTROL_PLANE_TUNNEL_ID=//p' "$envfile" | head -1)"

  if ! runuser -u "$BRIDGER_USER" -- env       HOME="$BRIDGER_HOME"       CONTROL_PLANE_TUNNEL_ID="$tunnel_id"       CONTROL_PLANE_API_KEY="file:$BRIDGER_ENV_DIR/openai-tunnel-api-key"       MCP_SERVER_URL="http://127.0.0.1:18879/mcp"       MCP_EXTRA_HEADERS="X-API-Key: file:$BRIDGER_ENV_DIR/mcp-api-key"       MCP_DISCOVERY_EXTRA_HEADERS="X-API-Key: file:$BRIDGER_ENV_DIR/mcp-api-key"       "$BRIDGER_TUNNEL_DIR/tunnel-client" doctor --explain; then
    die "OpenAI tunnel doctor failed. Fix the reported account/workspace/permission issue before continuing."
  fi
  ok "OpenAI tunnel doctor passed"
}

install_service() {
  log "Installing the tunnel service"
  install -d -o "$BRIDGER_USER" -g "$BRIDGER_GROUP" -m 0750 "$BRIDGER_HOME/.config"
  install -d -o "$BRIDGER_USER" -g "$BRIDGER_GROUP" -m 0750 "$BRIDGER_HOME/.config/bridger-tunnel"
  install -m 0644 "$BRIDGER_INSTALL_DIR/deploy/bridger-openai-tunnel.service" /etc/systemd/system/bridger-openai-tunnel.service
  systemctl daemon-reload
  systemctl enable --now bridger-openai-tunnel.service >/dev/null

  local ready=0 health_url=""
  for _ in {1..30}; do
    if [[ -s /run/bridger-tunnel/health.url ]]; then
      health_url="$(cat /run/bridger-tunnel/health.url)"
      if curl -fsS --max-time 2 "$health_url/readyz" >/dev/null 2>&1; then
        ready=1
        break
      fi
    fi
    sleep 1
  done

  if [[ "$ready" != "1" ]]; then
    systemctl status --no-pager bridger-openai-tunnel.service || true
    die "Tunnel service did not become ready within 30 seconds."
  fi

  ok "OpenAI Secure MCP Tunnel is running and ready"
}

finish() {
  cat <<EOF

============================================================
BRIDGER + OPENAI TUNNEL READY
============================================================

Bridger MCP:       private on 127.0.0.1:18879
OpenAI tunnel:     connected
Tunnel ID:         $TUNNEL_ID
Public MCP port:   NONE
Credential output: NONE

FINAL CHATGPT STEP

1. Open:
   https://chatgpt.com/plugins

2. Create a developer-mode plugin/app.
3. Choose "Tunnel" for Connection.
4. Select this tunnel, or paste:
   $TUNNEL_ID
5. Review the discovered Bridger tools before enabling them.

If the tunnel is not listed, verify that the tunnel is associated with the
ChatGPT workspace you are using and that your account has Tunnels Read + Use.

Status:
  sudo systemctl status bridger-openai-tunnel.service
  sudo /opt/bridger/scripts/quick-status.sh

OpenAI tunnel diagnostics:
  sudo /opt/bridger/scripts/tunnel-status.sh

Do not open ports 18877 or 18879 to the public Internet.
EOF
}

main() {
  need_root "$@"
  require_bridger
  detect_arch
  install_dependencies

  printf '\nBridger OpenAI Tunnel Setup\n'
  printf '%s\n' '---------------------------'
  printf 'This keeps Bridger private and creates only an outbound connection to OpenAI.\n'
  printf 'It does not make your MCP listener public.\n\n'

  install_tunnel_client
  read_mcp_key_to_file
  collect_openai_values
  doctor
  if [[ "$BRIDGER_TUNNEL_SKIP_START" == "1" ]]; then
    warn "Tunnel service start skipped by request."
    exit 0
  fi
  install_service
  finish
}

main "$@"
