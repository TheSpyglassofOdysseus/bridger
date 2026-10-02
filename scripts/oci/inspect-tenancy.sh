#!/usr/bin/env bash
set -euo pipefail

PROFILE="${OCI_CLI_PROFILE:-DEFAULT}"
CONFIG="${OCI_CLI_CONFIG_FILE:-$HOME/.oci/config}"

if ! command -v oci >/dev/null 2>&1; then
  echo "OCI CLI not found. Follow Oracle's current OCI CLI installation documentation." >&2
  exit 2
fi

if [[ ! -f "$CONFIG" ]]; then
  echo "OCI config not found at $CONFIG. Run Oracle's supported OCI CLI setup first." >&2
  exit 2
fi

profile_value() {
  local key="$1"
  awk -v profile="$PROFILE" -v key="$key" '
    $0 == "[" profile "]" {in_profile=1; next}
    /^\[/ {if (in_profile) exit}
    in_profile && $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
      sub("^[[:space:]]*" key "[[:space:]]*=[[:space:]]*", "", $0)
      print
      exit
    }
  ' "$CONFIG"
}

TENANCY="$(profile_value tenancy)"
REGION="$(profile_value region)"
COMPARTMENT="${OCI_COMPARTMENT_ID:-$TENANCY}"

if [[ -z "$TENANCY" || -z "$REGION" ]]; then
  echo "Could not read tenancy and region from profile [$PROFILE] in $CONFIG." >&2
  exit 2
fi

printf '== OCI starter inspection (read-only) ==\n'
printf 'profile: %s\n' "$PROFILE"
printf 'region: %s\n' "$REGION"
printf 'compartment: %s\n' "$COMPARTMENT"

printf '\n== Region subscriptions ==\n'
oci iam region-subscription list --all --output table

printf '\n== Availability domains ==\n'
oci iam availability-domain list --compartment-id "$TENANCY" --output table

printf '\n== A1 shape visibility ==\n'
# The JMESPath expression is intentionally single-quoted so its backticks reach OCI unchanged.
# shellcheck disable=SC2016
oci compute shape list \
  --compartment-id "$COMPARTMENT" \
  --all \
  --query 'data[?shape==`VM.Standard.A1.Flex`].{Shape:shape,OCPUs:ocpus,MemoryGB:"memory-in-gbs"}' \
  --output table

printf '\n== A1 compute service limits (read-only) ==\n'
limits_tmp="$(mktemp)"
trap 'rm -f "$limits_tmp"' EXIT
if oci limits value list \
  --compartment-id "$TENANCY" \
  --service-name compute \
  --all \
  --output json >"$limits_tmp" 2>/dev/null; then
  python3 - "$limits_tmp" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8")).get("data", [])
rows = []
for item in data:
    name = str(item.get("name", ""))
    if "a1" not in name.lower():
        continue
    rows.append(
        (
            name,
            item.get("value"),
            item.get("scope-type"),
            item.get("availability-domain") or "",
        )
    )

if not rows:
    print("No A1-specific compute limit rows were returned for this tenancy.")
else:
    print(f"{'Limit':48} {'Value':>10} {'Scope':>10}  Availability domain")
    print("-" * 96)
    for name, value, scope, ad in sorted(rows):
        print(f"{name:48} {str(value):>10} {str(scope or ''):>10}  {ad}")
PY
else
  echo "Could not read Compute service limits with the current OCI identity/policy."
  echo "This does not authorize guessing: inspect Limits, Quotas and Usage in the Oracle Console before provisioning."
fi

printf '\n== Existing compute instances ==\n'
oci compute instance list \
  --compartment-id "$COMPARTMENT" \
  --all \
  --query 'data[].{Name:"display-name",State:"lifecycle-state",Shape:shape,AD:"availability-domain",Created:"time-created"}' \
  --output table

cat <<'EOF'

This script does not create, resize, terminate, or upgrade anything.

Published Oracle Always Free baseline checked 2026-10-01:
  A1 compute: 2 OCPUs / 12 GB RAM
  Block storage: 200 GB total combined boot + block volumes

Your tenancy limits, home region, existing usage, quotas, capacity, and billing
view are still authoritative. Before launching a VM, verify the exact requested
CPU, memory, storage, architecture, and expected free/paid status.
EOF
