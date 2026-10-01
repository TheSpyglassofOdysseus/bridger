#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 https://hostname.example.com/" >&2
  exit 2
fi

URL="$1"
case "$URL" in
  https://*) ;;
  *)
    echo "Refusing non-HTTPS URL: $URL" >&2
    exit 2
    ;;
esac

curl --fail --silent --show-error \
  --location \
  --max-time 15 \
  --connect-timeout 5 \
  --output /dev/null \
  --write-out 'url=%{url_effective}\nhttp_code=%{http_code}\nremote_ip=%{remote_ip}\nssl_verify=%{ssl_verify_result}\n' \
  "$URL"

echo "HTTPS reachability is not a security audit."
