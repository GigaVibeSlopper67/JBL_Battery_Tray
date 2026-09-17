# Requirements and Installation

## Tray / AppIndicator (system packages, not pip)

The tray needs PyGObject + GTK3 + an AppIndicator implementation, and
libnotify for the desktop notifications. Install via the package manager:

```bash
# Debian/Ubuntu:
sudo apt install -y python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 \
    gir1.2-notify-0.7
# (on some distros the AppIndicator package is: gir1.2-appindicator3-0.1)

# Fedora:
sudo dnf install -y python3-gobject gtk3 libayatana-appindicator-gtk3 libnotify

# RHEL / CentOS Stream / Rocky / AlmaLinux (EPEL):
sudo dnf install -y epel-release
sudo dnf install -y python3-gobject gtk3 libayatana-appindicator-gtk3 libnotify
```

Without libnotify the tray still runs - it just skips the desktop
notifications (low battery, dongle connect/disconnect).

`requirements.txt` (`pyusb`, `hidapi`) is only needed by the CLI analysis
scripts; the tray itself reads via hidraw and needs **no pip packages**.

## Required Python Libraries

### For `jbl_battery_monitor.py` (pyusb)
```bash
# Install for a normal user
pip3 install pyusb --user

# Install for root (needed if using sudo)
sudo pip3 install pyusb
```

### For `jbl_battery_hidapi.py` (hidapi)
```bash
# Install for a normal user
pip3 install hidapi --user

# Install for root (needed if using sudo)
sudo pip3 install hidapi
```

### For `jbl_battery_hidraw.py` and `jbl_battery_simple.py`
**No external libraries needed!** Uses only Python standard libraries.

## Verification

### Check if pyusb is installed
```bash
python3 -c "import usb.core; print('OK')"
sudo python3 -c "import usb.core; print('OK')"  # For root
```

### Check if hidapi is installed
```bash
python3 -c "import hid; print('OK')"
sudo python3 -c "import hid; print('OK')"  # For root
```

## Recommendation

**Use the scripts that don't need external libraries:**
- `jbl_battery_simple.py` (recommended)
- `jbl_battery_hidraw.py` (full analysis)

These scripts use only Python standard libraries and work with `sudo` without installing anything extra.

## Quick Fix

If you get a module-not-found error when using `sudo`:

```bash
# Option 1: Install for root
sudo pip3 install pyusb

# Option 2: Use a script that doesn't need libraries
sudo python3 jbl_battery_simple.py
# or
sudo python3 jbl_battery_hidraw.py
```