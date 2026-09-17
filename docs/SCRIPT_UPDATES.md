# Script Updates

## Latest updates (2026-09-17)

### Tray (`jbl_quantum910_tray.py`)
- **Notifications** (`Notifier` class): desktop alerts on **low battery**
  (20/10/5 %, re-armed once the level climbs back above a threshold) and on
  **dongle connect/disconnect**. Uses libnotify (GObject) with a
  `notify-send` CLI fallback; silently skipped when neither is available.
  Mute-change alerts are opt-in via `--notify-mute`, everything can be
  disabled with `--no-notifications`.
- **Sidetone level display + radio menu**: the level read back via `0x5c`
  is shown in the menu/tooltip; the `Sidetone` submenu is a radio group
  (off/low/mid/high) marking the active level. Bug fixed: GTK3
  `RadioMenuItem` also emits `activate` on programmatic `set_active`, so the
  radio sync is now guarded - previously the startup sync re-sent the
  current sidetone value once per app start.
- **Lights state display**: read back via `0x4a`, shown as "Lights on/off".
- **Battery history + runtime estimate** (`BatteryHistory`): every percentage
  change is appended to `~/.local/share/jbl-quantum-tray/history.csv`; a
  least-squares fit over recent samples yields a drain rate shown as an
  "estimated runtime left" line in the menu/tooltip (needs ~5 minutes of
  data). Delete the CSV to reset the estimate.
- **Lighting submenu** (behind `--enable-controls`): "Pick color…" (GTK
  color chooser) plus presets Red/Green/Blue/White/Teal (factory). Applies
  the color to both elements (logo + ring): arm GET round -> lights off ->
  `0x4c`/`0x4d` table -> lights on (the table applies on the off->on
  transition).

### New tool: `tools/jbl_rgb.py` (RGB lighting CLI)
Writes the lighting table via feature reports `0x4c`/`0x4d`/`0x4b` with
automatic arming: `--status` (read-only probe), `--solid RRGGBB
[--element logo|ring|both]`, `--default` (factory teal table), `--raw`
(raw hex sequences), plus `--speed`/`--mode` (0x4c tempo / 0x4d M-byte
overrides for experiments), `--lights on|off|keep` and `--listen SEC`.

### Installers
- `install.sh`: tray flags passed as arguments are baked into the
  `~/.local/bin/jbl-quantum910-tray` wrapper (systemd, autostart and manual
  runs all inherit them); detects systemd and installs the `systemd --user`
  unit, otherwise falls back to an XDG autostart entry; each path removes
  the other's stale entry so the tray never starts twice.
- `uninstall.sh`: removes both install paths, tolerates a missing
  `systemctl` and stops a running tray instance.

### Documentation
- `docs/HID_REPORTS.md`: full "Lighting (RGB)" protocol section - arming
  round, `0x4c`/`0x4d` payload layout, element mapping (0 = logo, 1 = ring),
  apply-on-off->on cycle, ACK behavior, no read-back, open questions.

## Historical (early project): pyusb migration

All the main scripts have been updated to use **pyusb** (like `jbl_battery_monitor.py`), ensuring compatibility and correct operation.

### Updated Scripts

1. **`jbl_battery_simple.py`**
   - Now uses **pyusb** (same as monitor.py)
   - Works reliably
   - Simplified interface focused on the battery

2. **`jbl_battery_hidraw.py`**
   - Tries hidraw first
   - **Automatic fallback to pyusb** if hidraw doesn't work
   - Keeps full data analysis

3. **`jbl_battery_monitor.py`**
   - Was already working
   - Kept as is

### How to Use

### Simplified Script (Recommended)

```bash
cd /tmp/jbl_quantum910_monitor
sudo python3 jbl_battery_simple.py
```

### Full Script (Detailed Analysis)

```bash
sudo python3 jbl_battery_hidraw.py
```

If hidraw doesn't work, it automatically uses pyusb.

### Original Script

```bash
sudo python3 jbl_battery_monitor.py
```

### Requirements

All the scripts now need **pyusb**:

```bash
# For a normal user
pip3 install pyusb --user

# For root (if using sudo)
sudo pip3 install pyusb
```

### Improvements

1. **Compatibility**: All use pyusb (more reliable)
2. **Automatic fallback**: hidraw.py tries pyusb if hidraw fails
3. **Automatic detection**: The scripts detect the device automatically
4. **Error handling**: Better handling of I/O errors

### Result

Now **all the main scripts work** like `jbl_battery_monitor.py`!