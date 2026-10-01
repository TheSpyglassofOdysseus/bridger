#!/usr/bin/env bash
set -euo pipefail

BRIDGER_REF="${BRIDGER_REF:-v0.2.0}"
BRIDGER_REPO="${BRIDGER_REPO:-https://github.com/TheSpyglassofOdysseus/bridger.git}"
BRIDGER_SOURCE_DIR="${BRIDGER_SOURCE_DIR:-}"
BRIDGER_INSTALL_DIR="${BRIDGER_INSTALL_DIR:-/opt/bridger}"
BRIDGER_RUNTIME_DIR="${BRIDGER_RUNTIME_DIR:-/opt/bridger-runtime}"
BRIDGER_ENV_DIR="${BRIDGER_ENV_DIR:-/etc/bridger}"
BRIDGER_HOME="${BRIDGER_HOME:-/home/bridger}"
BRIDGER_USER="${BRIDGER_USER:-bridger}"
BRIDGER_GROUP="${BRIDGER_GROUP:-bridger}"
BRIDGER_SKIP_TAILSCALE="${BRIDGER_SKIP_TAILSCALE:-0}"
BRIDGER_REINSTALL="${BRIDGER_REINSTALL:-0}"
BRIDGER_NONINTERACTIVE="${BRIDGER_NONINTERACTIVE:-0}"

log() { printf '\n[%s] %s\n' "Bridger" "$*"; }
ok() { printf '  ✓ %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*" >&2; }
die() { printf '  ✗ %s\n' "$*" >&2; exit 1; }

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    command -v sudo >/dev/null 2>&1 || die "Run as root or install sudo."
    exec sudo --preserve-env=BRIDGER_REF,BRIDGER_REPO,BRIDGER_SOURCE_DIR,BRIDGER_INSTALL_DIR,BRIDGER_RUNTIME_DIR,BRIDGER_ENV_DIR,BRIDGER_HOME,BRIDGER_USER,BRIDGER_GROUP,BRIDGER_SKIP_TAILSCALE,BRIDGER_REINSTALL,BRIDGER_NONINTERACTIVE bash "$0" "$@"
  fi
}

confirm() {
  local prompt="$1"
  if [[ "$BRIDGER_NONINTERACTIVE" == "1" ]]; then
    return 0
  fi
  read -r -p "$prompt [Y/n] " answer
  [[ -z "$answer" || "$answer" =~ ^[Yy]$ ]]
}

detect_platform() {
  [[ -r /etc/os-release ]] || die "Cannot identify Linux distribution."
  # shellcheck disable=SC1091
  source /etc/os-release
  DISTRO_ID="${ID:-}"
  DISTRO_CODENAME="${VERSION_CODENAME:-}"
  case "$DISTRO_ID" in
    ubuntu|debian) ;;
    *) die "Quick install currently supports Ubuntu/Debian. Manual setup is available in docs/QUICKSTART.md." ;;
  esac
  [[ -n "$DISTRO_CODENAME" ]] || die "Distribution codename is missing from /etc/os-release."
  ARCH="$(uname -m)"
  case "$ARCH" in
    aarch64|arm64) NODE_ARCH=arm64 ;;
    x86_64|amd64)
      [[ "${BRIDGER_ALLOW_EXPERIMENTAL_ARCH:-0}" == "1" ]] || die "v0.2 quick install is release-certified on ARM64 only. Set BRIDGER_ALLOW_EXPERIMENTAL_ARCH=1 to test x86_64 at your own risk."
      NODE_ARCH=x64
      warn "x86_64 is experimental / not release-certified."
      ;;
    *) die "Unsupported architecture: $ARCH" ;;
  esac
  command -v systemctl >/dev/null 2>&1 || die "systemd is required."
  local systemd_state
  systemd_state="$(systemctl is-system-running 2>/dev/null || true)"
  case "$systemd_state" in
    running|degraded|starting|maintenance) ;;
    *) die "systemd is not operational (state: ${systemd_state:-unknown}). Use the manual/container guide instead." ;;
  esac
}

install_base_packages() {
  log "Installing base packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl git python3 xz-utils iproute2 util-linux passwd >/dev/null
  ok "Base packages ready"
}

create_service_user() {
  log "Preparing service account"
  if ! getent group "$BRIDGER_GROUP" >/dev/null 2>&1; then
    groupadd --system "$BRIDGER_GROUP"
  fi
  if ! id "$BRIDGER_USER" >/dev/null 2>&1; then
    useradd --system --create-home --home-dir "$BRIDGER_HOME" --gid "$BRIDGER_GROUP" --shell /usr/sbin/nologin "$BRIDGER_USER"
  fi
  install -d -o "$BRIDGER_USER" -g "$BRIDGER_GROUP" -m 0750 "$BRIDGER_HOME"
  install -d -o "$BRIDGER_USER" -g "$BRIDGER_GROUP" -m 0750 "$BRIDGER_HOME/projects"
  install -d -o "$BRIDGER_USER" -g "$BRIDGER_GROUP" -m 0750 "$BRIDGER_HOME/.local"
  install -d -o "$BRIDGER_USER" -g "$BRIDGER_GROUP" -m 0750 "$BRIDGER_HOME/.local/state"
  install -d -o "$BRIDGER_USER" -g "$BRIDGER_GROUP" -m 0750 "$BRIDGER_HOME/.local/state/bridger-interactive"
  install -d -o "$BRIDGER_USER" -g "$BRIDGER_GROUP" -m 0700 "$BRIDGER_HOME/.local/state/bridger-interactive/artifacts"
  ok "Service account: $BRIDGER_USER"
}

install_node22() {
  log "Installing private Node.js 22 runtime"
  local current=""
  if [[ -x "$BRIDGER_RUNTIME_DIR/node/bin/node" ]]; then
    current="$("$BRIDGER_RUNTIME_DIR/node/bin/node" --version 2>/dev/null || true)"
    if [[ "$current" =~ ^v22\. ]]; then
      ok "Node $current already installed"
      return
    fi
  fi

  local tmp archive node_version target
  tmp="$(mktemp -d)"
  trap 'rm -rf "${tmp:-}"' RETURN
  curl -fsSL https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt -o "$tmp/SHASUMS256.txt"
  archive="$(awk -v a="linux-$NODE_ARCH.tar.xz" '$2 ~ a"$" {print $2; exit}' "$tmp/SHASUMS256.txt")"
  [[ -n "$archive" ]] || die "Could not locate a Node 22 build for $NODE_ARCH."
  curl -fsSL "https://nodejs.org/dist/latest-v22.x/$archive" -o "$tmp/$archive"
  (cd "$tmp" && grep "  $archive$" SHASUMS256.txt | sha256sum -c - >/dev/null)
  node_version="${archive#node-}"
  node_version="${node_version%-linux-*}"
  target="$BRIDGER_RUNTIME_DIR/node-$node_version"

  install -d -m 0755 "$BRIDGER_RUNTIME_DIR"
  rm -rf "$target"
  mkdir -p "$target"
  tar -xJf "$tmp/$archive" --strip-components=1 -C "$target"
  chown -R root:root "$target"
  ln -sfn "$target" "$BRIDGER_RUNTIME_DIR/node"
  ok "Node $("$BRIDGER_RUNTIME_DIR/node/bin/node" --version) installed without changing system Node"
}

stage_source() {
  log "Fetching Bridger source"
  local stage_root="$1"
  local app="$stage_root/app"
  if [[ -n "$BRIDGER_SOURCE_DIR" ]]; then
    [[ -d "$BRIDGER_SOURCE_DIR/selfhosted" ]] || die "BRIDGER_SOURCE_DIR is not a Bridger checkout."
    mkdir -p "$app"
    tar -C "$BRIDGER_SOURCE_DIR" --exclude=.git --exclude=node_modules --exclude=selfhosted/node_modules -cf - . | tar -C "$app" -xf -
    ok "Using local source: $BRIDGER_SOURCE_DIR"
  else
    git clone --quiet --depth 1 --branch "$BRIDGER_REF" "$BRIDGER_REPO" "$app"
    rm -rf "$app/.git"
    ok "Fetched $BRIDGER_REF from public repository"
  fi
  chown -R "$BRIDGER_USER:$BRIDGER_GROUP" "$app"
}

install_dependencies() {
  local app="$1"
  local npm_log selftest_log
  npm_log="$(mktemp)"
  selftest_log="$(mktemp)"
  log "Installing pinned Bridger dependencies"

  if ! runuser -u "$BRIDGER_USER" -- env HOME="$BRIDGER_HOME" PATH="$BRIDGER_RUNTIME_DIR/node/bin:/usr/bin:/bin"       "$BRIDGER_RUNTIME_DIR/node/bin/npm" --prefix "$app/selfhosted" ci --no-audit --no-fund >"$npm_log" 2>&1; then
    tail -n 80 "$npm_log" >&2
    rm -f "$npm_log" "$selftest_log"
    die "Pinned dependency installation failed."
  fi

  if ! runuser -u "$BRIDGER_USER" -- env HOME="$BRIDGER_HOME" PATH="$BRIDGER_RUNTIME_DIR/node/bin:/usr/bin:/bin"       BRIDGER_INTERACTIVE_ARTIFACT_DIR="$BRIDGER_HOME/.local/state/bridger-self-test"       "$BRIDGER_RUNTIME_DIR/node/bin/node" "$app/selfhosted/bridger-interactive-facade.mjs" --self-test >"$selftest_log" 2>&1; then
    cat "$selftest_log" >&2
    rm -f "$npm_log" "$selftest_log"
    die "Bridger compact-facade self-test failed."
  fi

  rm -f "$npm_log" "$selftest_log"
  ok "Pinned dependencies installed"
  ok "Compact-facade self-test passed"
}

write_environment() {
  log "Creating protected local configuration"
  install -d -o root -g "$BRIDGER_GROUP" -m 0750 "$BRIDGER_ENV_DIR"
  local envfile="$BRIDGER_ENV_DIR/bridger.env"
  if [[ -s "$envfile" ]]; then
    ok "Preserving existing $envfile"
  else
    local key
    key="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
    (
      umask 0027
      cat >"$envfile" <<EOF
BRIDGE_DC_PORT=18877
MCP_PROXY_API_KEY=$key
EOF
    )
    chown root:"$BRIDGER_GROUP" "$envfile"
    chmod 0640 "$envfile"
    ok "Generated MCP credential (not printed)"
  fi
}

install_app_tree() {
  local app="$1"
  log "Installing Bridger application"
  if [[ -e "$BRIDGER_INSTALL_DIR" ]]; then
    if [[ "$BRIDGER_REINSTALL" != "1" ]]; then
      die "$BRIDGER_INSTALL_DIR already exists. Set BRIDGER_REINSTALL=1 to replace it after backup."
    fi
    local backup
    backup="$BRIDGER_INSTALL_DIR.backup.$(date -u +%Y%m%dT%H%M%SZ)"
    mv "$BRIDGER_INSTALL_DIR" "$backup"
    warn "Existing install moved to $backup"
  fi
  mv "$app" "$BRIDGER_INSTALL_DIR"
  printf '%s\n' "${BRIDGER_SOURCE_DIR:+local-source:}$BRIDGER_REF" >"$BRIDGER_INSTALL_DIR/.bridger-install-ref"
  chown -R root:"$BRIDGER_GROUP" "$BRIDGER_INSTALL_DIR"
  chmod -R u=rwX,g=rX,o= "$BRIDGER_INSTALL_DIR"
  ok "Installed to $BRIDGER_INSTALL_DIR (readable by the Bridger service account)"
}

install_services() {
  log "Installing interactive Bridger services"
  install -m 0644 "$BRIDGER_INSTALL_DIR/deploy/bridge-mcp.service" /etc/systemd/system/bridge-mcp.service
  install -m 0644 "$BRIDGER_INSTALL_DIR/deploy/bridge-interactive-facade.service" /etc/systemd/system/bridge-interactive-facade.service
  systemctl daemon-reload
  systemctl enable --now bridge-mcp.service bridge-interactive-facade.service >/dev/null
  sleep 2
  systemctl is-active --quiet bridge-mcp.service || { systemctl status --no-pager bridge-mcp.service; die "bridge-mcp.service did not start."; }
  systemctl is-active --quiet bridge-interactive-facade.service || { systemctl status --no-pager bridge-interactive-facade.service; die "bridge-interactive-facade.service did not start."; }
  ok "MCP backend and compact facade running"
}

verify_loopback() {
  log "Checking network boundary"
  local listeners="" raw_code="" facade_code="" ready=0

  for _ in {1..30}; do
    listeners="$(ss -lntH 2>/dev/null || true)"
    raw_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 1 http://127.0.0.1:18877/mcp || true)"
    facade_code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 1 http://127.0.0.1:18879/mcp || true)"

    if grep -Eq '127\.0\.0\.1:18877|\[::1\]:18877' <<<"$listeners"       && grep -Eq '127\.0\.0\.1:18879|\[::1\]:18879' <<<"$listeners"       && [[ "$raw_code" == "401" ]]       && [[ "$facade_code" == "401" ]]; then
      ready=1
      break
    fi
    sleep 0.5
  done

  [[ "$ready" == "1" ]] || die "Bridger MCP did not become ready within 15 seconds (raw=${raw_code:-unreachable}, facade=${facade_code:-unreachable})."

  if grep -Eq '(0\.0\.0\.0|\[::\]|\*):(18877|18879)([[:space:]]|$)' <<<"$listeners"; then
    die "A Bridger MCP listener is wildcard-bound. Refusing to continue."
  fi

  ok "Both MCP listeners are loopback-only and reject unauthenticated requests"
}

tailscale_running() {
  command -v tailscale >/dev/null 2>&1 || return 1
  tailscale status --json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("BackendState") == "Running" else 1)'
}

install_tailscale() {
  [[ "$BRIDGER_SKIP_TAILSCALE" == "1" ]] && { warn "Skipping Tailscale by request."; return; }

  log "Preparing private Tailscale access"
  if ! command -v tailscale >/dev/null 2>&1; then
    confirm "Install Tailscale from its official package repository?" || { warn "Tailscale skipped."; return; }
    install -d -m 0755 /usr/share/keyrings
    curl -fsSL "https://pkgs.tailscale.com/stable/$DISTRO_ID/$DISTRO_CODENAME.noarmor.gpg"       -o /usr/share/keyrings/tailscale-archive-keyring.gpg
    curl -fsSL "https://pkgs.tailscale.com/stable/$DISTRO_ID/$DISTRO_CODENAME.tailscale-keyring.list"       -o /etc/apt/sources.list.d/tailscale.list
    apt-get update -qq
    apt-get install -y -qq tailscale >/dev/null
  fi
  systemctl enable --now tailscaled >/dev/null

  if ! tailscale_running; then
    if [[ "$BRIDGER_NONINTERACTIVE" == "1" ]]; then
      warn "Tailscale installed but not authenticated. Run: sudo tailscale up"
    else
      printf '\nACTION REQUIRED: authenticate this server with Tailscale.\n'
      tailscale up
    fi
  fi

  if tailscale_running; then
    ok "Tailscale connected"
  else
    warn "Tailscale is not connected yet. Bridger itself is installed; finish with: sudo tailscale up"
  fi
}

write_handoff() {
  log "Writing safe AI handoff"
  local handoff="$BRIDGER_HOME/BRIDGER-HANDOFF.txt"
  local ts_dns=""
  if command -v tailscale >/dev/null 2>&1; then
    ts_dns="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("Self",{}).get("DNSName",""))' 2>/dev/null || true)"
  fi

  cat >"$handoff" <<EOF
BRIDGER INSTALL COMPLETE

This machine has the interactive Bridger core installed.

Server layer:
- Hostname: $(hostname)
- Architecture: $(uname -m)
- Bridger path: $BRIDGER_INSTALL_DIR
- Service account: $BRIDGER_USER
- Raw MCP: http://127.0.0.1:18877/mcp (loopback only)
- Compact MCP facade: http://127.0.0.1:18879/mcp (loopback only)
- Tailscale DNS name: ${ts_dns:-not connected yet}
- Public MCP exposure: NONE

The MCP credential is intentionally NOT included in this handoff.
It is stored in: $BRIDGER_ENV_DIR/bridger.env

Next goal:
Connect my AI client to this private Bridger MCP service.

If I use ChatGPT, the recommended private path is:
  sudo /opt/bridger/scripts/setup-openai-tunnel.sh

That helper installs OpenAI's official Secure MCP Tunnel client, keeps the MCP
listener private, and stops for my own OpenAI tunnel/account authorization.

Use the public Bridger repository as the source of truth:
https://github.com/TheSpyglassofOdysseus/bridger

For ChatGPT:
- Read current OpenAI Plugin / Secure MCP Tunnel documentation.
- Prefer Secure MCP Tunnel for a private server when my account/workspace supports it.
- Do not expose ports 18877 or 18879 directly to the public Internet.
- Do not paste Bridger credentials into chat messages or Git.

Read:
- AI_HANDOFF.md
- docs/EASY-SETUP.md
- docs/beginner/06-connect-your-ai.md
- SECURITY.md

Before making changes, inspect current state and tell me the safest next action.
EOF
  chown "$BRIDGER_USER:$BRIDGER_GROUP" "$handoff"
  chmod 0644 "$handoff"
  ok "Handoff written to $handoff"
}

finish() {
  printf '\n============================================================\n'
  printf 'BRIDGER READY\n'
  printf '============================================================\n'
  printf 'Server core:       installed\n'
  printf 'MCP backend:       loopback only\n'
  printf 'Compact facade:    loopback only\n'
  if tailscale_running; then
    printf 'Tailscale:          connected\n'
  else
    printf 'Tailscale:          needs authentication\n'
  fi
  printf 'Public exposure:   none\n'
  printf '\nNext:\n'
  printf '  1. Read: %s/BRIDGER-HANDOFF.txt\n' "$BRIDGER_HOME"
  printf '  2. If you use ChatGPT, run: sudo %s/scripts/setup-openai-tunnel.sh\n' "$BRIDGER_INSTALL_DIR"
  printf '  3. Connect/select your tunnel in ChatGPT Plugins.\n'
  printf '  4. Give the handoff to your AI and start building.\n'
  printf '\nStatus anytime:\n'
  printf '  sudo %s/scripts/quick-status.sh\n' "$BRIDGER_INSTALL_DIR"
  printf '\nSecrets were not printed. Do not paste %s/bridger.env into chat.\n' "$BRIDGER_ENV_DIR"
}

main() {
  need_root "$@"
  detect_platform

  printf '\nBridger Quick Install\n'
  printf '%s\n' '---------------------'
  printf 'This installs the interactive Bridger core only.\n'
  printf 'It does NOT create paid cloud resources, buy domains, expose MCP ports publicly,\n'
  printf 'or configure Passrail/advanced unattended execution.\n\n'
  printf 'Distribution: %s (%s)\nArchitecture: %s\nSource: %s\n' "$DISTRO_ID" "$DISTRO_CODENAME" "$ARCH" "${BRIDGER_SOURCE_DIR:-$BRIDGER_REF}"
  confirm "Continue?" || exit 0

  install_base_packages
  create_service_user
  install_node22

  local stage_root
  stage_root="$(mktemp -d /var/tmp/bridger-install.XXXXXX)"
  chmod 0755 "$stage_root"
  trap 'rm -rf "${stage_root:-}"' EXIT
  stage_source "$stage_root"
  install_dependencies "$stage_root/app"
  write_environment
  install_app_tree "$stage_root/app"
  install_services
  verify_loopback
  install_tailscale
  write_handoff
  finish
}

main "$@"
