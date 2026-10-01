#!/usr/bin/env bash
set -euo pipefail

PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1

if [[ "${EUID}" -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 || { echo "Run as root or with sudo." >&2; exit 1; }
  exec sudo bash "$0" "$@"
fi

echo "Bridger uninstall"
echo "================="
echo "This will stop and remove the Bridger systemd units."
if [[ "$PURGE" == "1" ]]; then
  echo "PURGE requested: code, private Node runtime, configuration, and service-user state will also be deleted."
  read -r -p "Type PURGE to continue: " answer
  [[ "$answer" == "PURGE" ]] || exit 0
else
  echo "Configuration, credentials, runtime, and /home/bridger will be preserved."
  read -r -p "Continue? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || exit 0
fi

systemctl disable --now bridger-openai-tunnel.service bridge-interactive-facade.service bridge-mcp.service 2>/dev/null || true
rm -f   /etc/systemd/system/bridger-openai-tunnel.service   /etc/systemd/system/bridge-interactive-facade.service   /etc/systemd/system/bridge-mcp.service
systemctl daemon-reload
systemctl reset-failed >/dev/null 2>&1 || true

if [[ "$PURGE" == "1" ]]; then
  rm -rf /opt/bridger /opt/bridger-runtime /opt/bridger-tunnel /etc/bridger
  if id bridger >/dev/null 2>&1; then
    userdel -r bridger >/dev/null 2>&1 || true
  fi
  echo "Bridger purged. Tailscale was not removed because it may be used by other services."
else
  echo "Bridger services removed. Preserved:"
  echo "  /opt/bridger"
  echo "  /opt/bridger-runtime"
  echo "  /opt/bridger-tunnel"
  echo "  /etc/bridger"
  echo "  /home/bridger"
  echo "Tailscale was not changed."
fi
