#!/usr/bin/env bash
set -euo pipefail

APP_NAME="jbl-quantum910-tray"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SHARE_DIR="${HOME}/.local/share/${APP_NAME}"
BIN_DIR="${HOME}/.local/bin"
SYSTEMD_DIR="${HOME}/.config/systemd/user"
AUTOSTART_DIR="${HOME}/.config/autostart"

WRAPPER_PATH="${BIN_DIR}/${APP_NAME}"
APP_PATH="${SHARE_DIR}/jbl_quantum910_tray.py"
SERVICE_SRC="${ROOT_DIR}/systemd/jbl-quantum910-tray.service"
SERVICE_DST="${SYSTEMD_DIR}/jbl-quantum910-tray.service"
DESKTOP_SRC="${ROOT_DIR}/autostart/jbl-quantum910-tray.desktop"
DESKTOP_DST="${AUTOSTART_DIR}/jbl-quantum910-tray.desktop"

# Any arguments are forwarded to the tray on every launch (baked into the
# wrapper), e.g.: ./install.sh --enable-controls --notify-mute
TRAY_ARGS="$*"

echo "==> Installing ${APP_NAME} (user-level)"

if [[ ! -x /usr/bin/python3 ]]; then
  echo "ERROR: /usr/bin/python3 not found. Install the system Python." >&2
  exit 1
fi

mkdir -p "${SHARE_DIR}" "${BIN_DIR}" "${SYSTEMD_DIR}" "${AUTOSTART_DIR}"

echo "==> Copying app to ${APP_PATH}"
cp -f "${ROOT_DIR}/jbl_quantum910_tray.py" "${APP_PATH}"
chmod +x "${APP_PATH}"

echo "==> Creating wrapper at ${WRAPPER_PATH}"
cat > "${WRAPPER_PATH}" <<EOF
#!/usr/bin/env sh
exec /usr/bin/python3 "\$HOME/.local/share/jbl-quantum910-tray/jbl_quantum910_tray.py" ${TRAY_ARGS} "\$@"
EOF
chmod +x "${WRAPPER_PATH}"

if command -v systemctl >/dev/null 2>&1; then
  echo "==> Installing systemd --user service"
  cp -f "${SERVICE_SRC}" "${SERVICE_DST}"

  # Remove a previously installed XDG autostart entry so the tray does not
  # start twice at login (once via systemd, once via autostart).
  if [[ -f "${DESKTOP_DST}" ]]; then
    echo "==> Removing XDG autostart entry (superseded by the systemd service)"
    rm -f "${DESKTOP_DST}"
  fi

  echo "==> Reloading systemd (user) and enabling"
  systemctl --user daemon-reload
  systemctl --user enable --now jbl-quantum910-tray.service

  echo
  echo "OK. Installed and started (systemd --user)."
  echo
  echo "Useful commands:"
  echo "  - status:  systemctl --user status jbl-quantum910-tray.service"
  echo "  - logs:    journalctl --user -u jbl-quantum910-tray.service -f"
  echo "  - stop:    systemctl --user stop jbl-quantum910-tray.service"
else
  echo "==> systemctl not found - installing XDG autostart entry instead"
  cp -f "${DESKTOP_SRC}" "${DESKTOP_DST}"

  echo
  echo "OK. Installed via XDG autostart (${DESKTOP_DST})."
  echo
  echo "The tray starts automatically at your next login. To start it now:"
  echo "  ${WRAPPER_PATH} &"
  echo "To stop it:  pkill -f jbl_quantum910_tray.py"
fi

echo
if [[ -n "${TRAY_ARGS}" ]]; then
  echo "Tray launch flags: ${TRAY_ARGS}"
else
  echo "Tip: pass tray flags to bake them in, e.g.: ./install.sh --enable-controls"
fi
echo
echo "If the tray does not appear, install the AppIndicator dependencies:"
echo "  Debian/Ubuntu: sudo apt install -y python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1"
echo "  Fedora:        sudo dnf install -y python3-gobject gtk3 libayatana-appindicator-gtk3"
echo "  RHEL/Rocky/Alma (EPEL): sudo dnf install -y epel-release && sudo dnf install -y python3-gobject gtk3 libayatana-appindicator-gtk3"

