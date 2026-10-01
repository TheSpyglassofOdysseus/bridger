#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Starter publication checks =="

echo "-- shell syntax --"
while IFS= read -r -d '' file; do
  bash -n "$file"
  echo "OK $file"
done < <(find scripts -type f -name '*.sh' -print0)

echo
echo "-- candidate-tree secret/private-key filename scan --"
bad_names="$(
  find .     -path './.git' -prune -o     -path './node_modules' -prune -o     -path './selfhosted/node_modules' -prune -o     -path './.venv' -prune -o     -type f -print   | sed 's#^\./##'   | grep -Ei '(^|/)(id_rsa|id_ed25519|.*\.pem|.*\.key|\.env|bridge\.env)$' || true
)"
if [[ -n "$bad_names" ]]; then
  echo "$bad_names"
  echo "FAIL: suspicious secret/key filename(s)." >&2
  exit 1
fi

echo
echo "-- candidate-tree private-key/token marker scan --"
scan_file="$(mktemp)"
trap 'rm -f "$scan_file"' EXIT
if grep -RIlE   --exclude-dir=.git   --exclude-dir=node_modules   --exclude-dir=.venv   --exclude=package-lock.json   'BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}'   . >"$scan_file" 2>/dev/null; then
  cat "$scan_file"
  echo "FAIL: possible secret material detected. Review files above." >&2
  exit 1
fi

echo
echo "-- required starter files --"
for file in   START_HERE.md   AI_HANDOFF.md   docs/STARTER-ARCHITECTURE.md   docs/STARTER-COUNTER-REVIEW.md   docs/EASY-SETUP.md   scripts/quick-install.sh   scripts/quick-status.sh   scripts/quick-uninstall.sh   scripts/setup-openai-tunnel.sh   scripts/tunnel-status.sh   deploy/bridge-mcp.service   deploy/bridge-interactive-facade.service   deploy/bridger-openai-tunnel.service; do
  test -s "$file"
  echo "OK $file"
done

echo
echo "STARTER_CHECK=PASS"
