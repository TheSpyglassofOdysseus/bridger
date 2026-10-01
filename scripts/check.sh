#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
node_major="$(node -p 'process.versions.node.split(".")[0]')"
if (( node_major < 22 )); then
  printf 'BRIDGE_CHECK=FAIL node=%s required=>=22\n' "$(node --version)" >&2
  exit 1
fi
python3 -m compileall -q selfhosted tests
python3 -m unittest discover -s tests -v
(
  cd selfhosted
  npm ci --ignore-scripts --no-audit --no-fund
  node --check bridger-interactive-facade.mjs
  facade_tmp="$(mktemp -d)"
  trap 'rm -rf "$facade_tmp"' EXIT
  BRIDGER_INTERACTIVE_ARTIFACT_DIR="$facade_tmp" node bridger-interactive-facade.mjs --self-test
  rm -rf "$facade_tmp"
  trap - EXIT
  npm audit --omit=dev --audit-level=moderate
)
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git diff --check
fi
printf 'BRIDGE_CHECK=PASS\n'
