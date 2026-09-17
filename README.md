# JBL Quantum 910/810 Battery Tray (Linux)

Attention Attention! This is AI Chudslop, use at own risk xD

**Real** battery monitor for the JBL Quantum910 and Quantum810: shows the **battery % in the tray** and can start automatically at login via **`systemd --user`**.

Experimental Features:
- RGB control (has some bugs)
- Control Sidetone
- Cycle ANC

The confirmed battery pattern for this headset is:

```
[Report ID, Battery%]
08 1e => 30%
```

## What this project does

- **Tray/AppIndicator**: shows the battery % in the tray and updates automatically.
- **Reading**: hidraw first (works for both models), pyusb as fallback. On the Quantum 810 the battery is actively polled via HID feature report `0x49`, so it stays fresh even when the headset is quiet.
- **Extra headset status (810)**: the tray and CLI also show **ANC state**, **mic mute**, the **game/chat dial position** and the device **part/serial number** - see `docs/HID_REPORTS.md`.
- **Controls (opt-in)**: with `jbl_quantum910_tray.py --enable-controls` the tray menu can **cycle ANC**, **toggle the lights**, **set the sidetone** and **set the lighting color** (logo + ring elements, breathing effect) via HID feature reports (`0x46`/`0x4b`/`0x5d`/`0x4c`+`0x4d`) - see `docs/HID_REPORTS.md`.
- **Lights/sidetone state**: the tray reads back and shows the current **lights state** (`0x4a`) and **sidetone level** (`0x5c`) in the menu/tooltip; the sidetone submenu marks the active level.
- **Notifications**: desktop notifications on **low battery** (20/10/5%) and **dongle connect/disconnect**; mute notifications opt-in via `--notify-mute`; everything off with `--no-notifications`.
- **Battery history & estimate**: every percentage change is appended to `~/.local/share/jbl-quantum-tray/history.csv`; the tray computes the drain rate and shows an **estimated runtime left** in the menu/tooltip (needs ~5 minutes of data).
- **Permission helper**: `check_permissions.sh` verifies your hidraw access; `setup_udev_rules.sh` installs the udev rules (`uaccess` + `0666` — no plugdev group or usermod needed).
- **Login service**: installs as `systemd --user` (no need for root to run the app).
- **Tools and docs**: analysis scripts and documentation were organized into folders.

## Project structure

- **`jbl_quantum910_tray.py`**: tray app (main; supports the 910 and 810)
- **`jbl_battery_simple.py`**: CLI battery monitor (pyusb)
- **`check_permissions.sh`**: verifies device access, udev rules and Python libraries
- **`setup_udev_rules.sh`**: installs the udev rules (no plugdev group needed)
- **`install.sh` / `uninstall.sh`**: installs/removes as a login service Use --enable-controls flag to enable experimental control features.
- **`systemd/`**: `systemd --user` unit file
- **`autostart/`**: alternative via `.desktop`
- **`tools/`**: auxiliary/experimental capture/analysis scripts
- **`docs/`**: detailed documentation (permissions, troubleshooting, etc.)

## Battery Pattern (confirmed)

- **Byte 0**: Report ID = `0x08`
- **Byte 1**: battery in % (0–100)
- Works for **both dongles**: Quantum 910 (`0ecb:2088`) and Quantum 810 (`0ecb:2069`). On the 810 the tray also polls the battery directly via HID feature report `0x49`, so fresh data arrives even when the headset is quiet.
- **Mute indicator**: works on the Quantum 910 (`0x2f` mute events) **and on the Quantum 810** (`0x06` mic on/off events - previously believed to be 910-only).

Details: `docs/BATTERY_PATTERN.md` and the full protocol map in `docs/HID_REPORTS.md`.

## Quick Start

### 1) Check permissions

```bash
./check_permissions.sh
```

### 2) Set up permissions (recommended)

```bash
sudo ./setup_udev_rules.sh
# Then disconnect and reconnect the USB dongle
```

### 3) Run the tray

```bash
python3 ./jbl_quantum910_tray.py
```

If you just want to test the reading (CLI), use:

```bash
python3 ./tools/jbl_battery_auto.py
# or the pyusb-based script (needs `pip3 install pyusb`):
sudo python3 ./jbl_battery_simple.py
```

## Requirements

### Python dependencies (CLI only)

The tray itself needs no pip packages on the Quantum 810 — it reads via hidraw.
pyusb/hidapi are only needed by the CLI scripts:

```bash
pip3 install pyusb --user
# or
pip3 install hidapi --user
```

### Requirements (Tray / AppIndicator)

For the tray, installation is via system packages (not via pip):

```bash
# Debian/Ubuntu:
sudo apt install -y python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1
# (on some distros it may be: gir1.2-appindicator3-0.1)

# Fedora:
sudo dnf install -y python3-gobject gtk3 libayatana-appindicator-gtk3

# RHEL / CentOS Stream / Rocky / AlmaLinux (the last via EPEL):
sudo dnf install -y epel-release
sudo dnf install -y python3-gobject gtk3 libayatana-appindicator-gtk3
```

## Tray (AppIndicator) - How to use

### Run manually

The tray icon itself shows the battery % (drawn into the icon, since some
desktops like GNOME hide indicator labels), and the tray menu shows
`Battery: 45%`. On KDE Plasma, hovering the icon also shows the percentage in
the tooltip:

```bash
python3 ./jbl_quantum910_tray.py
# The tray shows native themed battery icons (crisp at any size/DPI); the
# percentage is in the tooltip and the menu. To draw the percentage into
# the icon as a badge instead:
python3 ./jbl_quantum910_tray.py --numeric-icon
```

Useful options:

```bash
python3 ./jbl_quantum910_tray.py --refresh 1.0
python3 ./jbl_quantum910_tray.py --prefer-hidraw  # recommended for the Quantum 810
python3 ./jbl_quantum910_tray.py --no-notifications  # disable desktop notifications
python3 ./jbl_quantum910_tray.py --notify-mute      # also notify on mute changes
```

## Installation (recommended) — starts with the system (login)

Installs as a **`systemd --user` service** when systemd is available; on systems **without systemd** it automatically falls back to an **XDG autostart entry** (`~/.config/autostart`). Any arguments are baked into the launcher and apply to every launch (service, autostart and manual runs):

```bash
chmod +x ./install.sh
./install.sh --enable-controls   # controls: ANC, lights, sidetone, RGB lighting
# add more tray flags if you want, e.g. --notify-mute
```

To change the flags later, re-run the installer. To remove:

```bash
chmod +x ./uninstall.sh
./uninstall.sh
```

## Tools (helper scripts)

The scripts below live in `tools/` and are useful for analysis/debugging:

- `tools/jbl_status.py`: **full status reader** (battery, ANC, mic, game/chat mix, serial) with `--json`, `--watch` and control flags (`--set-anc`, `--set-lights`, `--set-sidetone`)
- `tools/jbl_rgb.py`: **RGB lighting CLI** - `--status` (read-only probe), `--solid RRGGBB [--element logo|ring|both]`, `--default` (factory table), `--raw` hex sequences; performs the arming GET round automatically
- `tools/jbl_status_probe.py`: **live protocol probe** (`--monitor` decodes event packets, `--features` watches feature reports, `--scan` sweeps all report IDs, `--correlate` guides you through verifying each action)
- `tools/jbl_battery_auto.py`: auto-detects the dongle (910/810) and monitors the battery
- `tools/jbl_battery_hidraw.py`: full dump/analysis (has `--log`)
- `tools/jbl_battery_monitor.py`: alternative via pyusb
- `tools/jbl_battery_hidapi.py`: alternative via hidapi
- `tools/jbl_battery_capture.py`: capture on connect/disconnect
- `tools/jbl_battery_force.py`: brute force/experimental
- `tools/find_hidraw.py`: finds the `/dev/hidrawX`

## Notes

- **IDs**: Quantum 910 `0ecb:2088` / Quantum 810 `0ecb:2069`
- **HID**: interface 3 (Quantum 910) / interface 5 (Quantum 810), IN endpoint (used by the `pyusb` method)
- **Updates**: on the Quantum 910 the headset can go "quiet" — use the volume/buttons to generate traffic. On the Quantum 810 the tray polls the battery directly, so it always stays fresh.
- **Mute**: works on both models — Quantum 910 via `0x2f` events, Quantum 810 via `0x06` mic on/off events.
- **Controls**: ANC/lights/sidetone commands change device state; in the tray they are only active with `--enable-controls`, in the CLI only via the explicit `--set-*` flags.
- **Notifications**: need libnotify (`gir1.2-notify-0.7` on Debian/Ubuntu, `libnotify` on Fedora) or the `notify-send` CLI; without either, the tray silently skips notifications.
- **History**: the battery log lives in `~/.local/share/jbl-quantum-tray/history.csv` (one row per percentage change); delete it to reset the drain-rate estimate.
- **hidraw safety**: never run a pyusb session against the vendor interface while the hidraw node exists — claiming the interface removes the hidraw node until the dongle is replugged (the tray now avoids this, but the older CLI tools can still trigger it).
- **Permissions**: run `sudo ./setup_udev_rules.sh` once — it installs rules with `uaccess` + `0666`, so no plugdev group or usermod is needed. Then replug the dongle.

## Troubleshooting

See:

- `docs/TROUBLESHOOTING.md`
- `docs/INSTRUCTIONS.md`

## License

Scripts created for personal/educational use.

