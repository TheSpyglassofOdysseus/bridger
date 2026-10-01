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
oci compute shape list \
  --compartment-id "$COMPARTMENT" \
  --all \
  --query 'data[?shape==`VM.Standard.A1.Flex`].{Shape:shape,OCPUs:ocpus,MemoryGB:"memory-in-gbs"}' \
  --output table

printf '\n== Existing compute instances ==\n'
oci compute instance list \
  --compartment-id "$COMPARTMENT" \
  --all \
  --query 'data[].{Name:"display-name",State:"lifecycle-state",Shape:shape,AD:"availability-domain",Created:"time-created"}' \
  --output table

cat <<'EOF'

This script does not create, resize, terminate, or upgrade anything.
Before launching a VM, verify current Oracle Free Tier documentation and the
exact requested CPU, memory, storage, architecture, and expected cost.
EOF
