#!/usr/bin/env bash
set -euo pipefail

APP_NAME="jbl-quantum910-tray"

SHARE_DIR="${HOME}/.local/share/${APP_NAME}"
WRAPPER_PATH="${HOME}/.local/bin/${APP_NAME}"
SERVICE_PATH="${HOME}/.config/systemd/user/jbl-quantum910-tray.service"
DESKTOP_PATH="${HOME}/.config/autostart/jbl-quantum910-tray.desktop"

echo "==> Removing ${APP_NAME} (user-level)"

if command -v systemctl >/dev/null 2>&1; then
  if systemctl --user list-unit-files 2>/dev/null | grep -q '^jbl-quantum910-tray\.service'; then
    systemctl --user disable --now jbl-quantum910-tray.service || true
  fi
  rm -f "${SERVICE_PATH}" || true
  systemctl --user daemon-reload || true
fi

rm -f "${DESKTOP_PATH}" || true
rm -f "${WRAPPER_PATH}" || true
rm -rf "${SHARE_DIR}" || true

# On XDG-autostart systems there is no service to stop the running tray.
pkill -f jbl_quantum910_tray.py 2>/dev/null || true

echo "OK. Removed."

