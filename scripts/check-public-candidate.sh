#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "PUBLIC_EXPORT_CHECK=FAIL reason=$1" >&2
  exit 1
}

[[ -d .git ]] || fail not_a_git_repository
[[ "$(git rev-list --all --count)" -eq 1 ]] || fail history_not_single_commit
[[ "$(git branch --format='%(refname:short)' | wc -l)" -eq 1 ]] || fail multiple_branches

for forbidden in   docs/duo   docs/research   docs/PUBLICATION-READINESS.md   docs/PUBLIC-REPO-METADATA.md   docs/PLUGIN-MIGRATION-OPERATIONS.md   scripts/finalize-direct-cutover.sh   scripts/check-direct-only-runtime.sh; do
  [[ ! -e "$forbidden" ]] || fail "private_or_migration_material_present:$forbidden"
done

private_pattern='/home/ubuntu|factory-dealer-inventory|mdf-trading|duckdns\.org|davefeichko|arm-freetier|tailf71ef2|100\.110\.80\.11|10\.0\.0\.59|plugins_[0-9a-f]{16,}|asdk_app_[0-9a-f]{16,}|ocid1\.'
hits="$(
  git grep -n -E "$private_pattern"     -- ':!scripts/check-public-candidate.sh' 2>/dev/null || true
)"
if [[ -n "$hits" ]]; then
  echo "$hits" >&2
  fail private_coordinate_candidate
fi

for required in   README.md   START_HERE.md   AI_HANDOFF.md   SECURITY.md   LICENSE   SUPPORT.md   docs/beginner/05-install-bridger.md   docs/beginner/06-connect-your-ai.md   docs/beginner/12-credential-rotation.md   deploy/bridge-mcp.service   deploy/bridge-actions.service   deploy/bridge-interactive-facade.service   PUBLICATION-MANIFEST.sha256; do
  [[ -s "$required" ]] || fail "required_file_missing:$required"
done

scripts/check-starter-publication.sh

echo "PUBLIC_EXPORT_CHECK=PASS"
