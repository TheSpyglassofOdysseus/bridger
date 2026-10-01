#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 hostname.example.com" >&2
  exit 2
fi

HOST="$1"

echo "== DNS for $HOST =="

if command -v dig >/dev/null 2>&1; then
  for type in A AAAA CNAME; do
    echo "-- $type --"
    dig +short "$HOST" "$type" || true
  done
else
  echo "dig not installed; using getent for address resolution."
  getent ahosts "$HOST" || true
fi

echo
echo "DNS resolution alone does not prove the service is authenticated or safe."
