#!/usr/bin/env bash
set -euo pipefail

APP_NAME="jbl-quantum910-tray"

SHARE_DIR="${HOME}/.local/share/${APP_NAME}"
WRAPPER_PATH="${HOME}/.local/bin/${APP_NAME}"
SERVICE_PATH="${HOME}/.config/systemd/user/jbl-quantum910-tray.service"

echo "==> Removing ${APP_NAME} (user-level)"

if systemctl --user list-unit-files | grep -q '^jbl-quantum910-tray\.service'; then
  systemctl --user disable --now jbl-quantum910-tray.service || true
fi

rm -f "${SERVICE_PATH}" || true
systemctl --user daemon-reload || true

rm -f "${WRAPPER_PATH}" || true
rm -rf "${SHARE_DIR}" || true

echo "OK. Removed."

