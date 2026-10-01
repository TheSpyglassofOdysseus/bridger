#!/usr/bin/env bash
set -euo pipefail

printf '== Bridger starter preflight ==\n'
printf 'date: '; date -Is
printf 'host: '; hostname
printf 'kernel: '; uname -sr
printf 'arch: '; uname -m
printf 'user: '; id -un
printf 'uid: '; id -u
printf 'systemd: '
if command -v systemctl >/dev/null 2>&1; then
  systemctl --version | head -1
else
  printf 'NOT FOUND\n'
fi

check_cmd() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    printf '%-12s %s\n' "$name" "$(command -v "$name")"
  else
    printf '%-12s MISSING\n' "$name"
  fi
}

printf '\n== Commands ==\n'
for cmd in python3 node npm git curl ssh ss tailscale nginx jq oci; do
  check_cmd "$cmd"
done

printf '\n== Versions ==\n'
python3 --version 2>/dev/null || true
node --version 2>/dev/null || true
npm --version 2>/dev/null || true
git --version 2>/dev/null || true
tailscale version 2>/dev/null | head -1 || true
oci --version 2>/dev/null || true

printf '\n== Bridger core requirements ==\n'
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)'; then
  echo 'python>=3.11 PASS'
else
  echo 'python>=3.11 FAIL'
fi

if command -v node >/dev/null 2>&1; then
  node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  if [[ "$node_major" =~ ^[0-9]+$ ]] && (( node_major >= 22 )); then
    echo 'node>=22 PASS'
  else
    echo "node>=22 FAIL (found $(node --version 2>/dev/null || echo unknown))"
  fi
else
  echo 'node>=22 FAIL (node not found)'
fi

if command -v systemctl >/dev/null 2>&1; then
  echo 'systemd PASS'
else
  echo 'systemd FAIL'
fi

printf '\n== Storage / memory ==\n'
df -h /
free -h 2>/dev/null || true

printf '\n== Listening sockets ==\n'
if command -v ss >/dev/null 2>&1; then
  ss -H -lntup 2>/dev/null || ss -H -lnt 2>/dev/null || true
fi

printf '\nPreflight is read-only. Missing optional commands are not automatically installed.\n'
