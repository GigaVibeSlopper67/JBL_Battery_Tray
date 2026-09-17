# Script Updates

## Updated Scripts

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

## How to Use

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

## Requirements

All the scripts now need **pyusb**:

```bash
# For a normal user
pip3 install pyusb --user

# For root (if using sudo)
sudo pip3 install pyusb
```

## Improvements

1. **Compatibility**: All use pyusb (more reliable)
2. **Automatic fallback**: hidraw.py tries pyusb if hidraw fails
3. **Automatic detection**: The scripts detect the device automatically
4. **Error handling**: Better handling of I/O errors

## Result

Now **all the main scripts work** like `jbl_battery_monitor.py`!