# Instructions for Monitoring the JBL Quantum910 Battery

## Current Status

Device detected: JBL Quantum910 (Bus 001 Device 007)  
Identified HID interface: `/dev/hidraw5`  
Required permissions: Requires root access or udev configuration

## Available Scripts

1. **`jbl_battery_hidraw.py`** **RECOMMENDED**
   - Reads directly from the hidraw device
   - More efficient and direct
   - File: `/tmp/jbl_battery_hidraw.py`

2. **`jbl_battery_monitor.py`**
   - Uses pyusb for direct USB communication
   - File: `/tmp/jbl_battery_monitor.py`

3. **`jbl_battery_hidapi.py`**
   - Alternative version using hidapi
   - File: `/tmp/jbl_battery_hidapi.py`

## How to Use (Option 1: With Sudo)

Run directly with root permissions:

```bash
sudo python3 /tmp/jbl_battery_hidraw.py
```

## How to Use (Option 2: Set Up Permanent Permissions)

### Step 1: Set up the udev rules

```bash
sudo /tmp/setup_udev_rules.sh
```

Or manually:

```bash
sudo nano /etc/udev/rules.d/99-jbl-quantum910.rules
```

Add:
```
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="0ecb", ATTRS{idProduct}=="2088", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0ecb", ATTR{idProduct}=="2088", MODE="0666", GROUP="plugdev"
```

### Step 2: Reload the rules and reconnect

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
# Disconnect and reconnect the headset
```

### Step 3: Add the user to the plugdev group (if needed)

```bash
sudo usermod -a -G plugdev $USER
# Log out and log back in
```

### Step 4: Run the script

```bash
python3 /tmp/jbl_battery_hidraw.py
```

## How It Works

The script:
1. Opens the `/dev/hidraw5` device (matching the JBL Quantum910)
2. Reads data in real time from the HID communication
3. Analyzes the received data looking for values that represent the battery
4. Displays the raw data in hexadecimal and decimal
5. Tries to automatically identify the battery level

## Data Interpretation

The script tries several interpretations:
- **Method 1**: Looks for values between 0-100 that could be percentages
- **Method 2**: Interprets them as 16-bit values (little-endian)
- **Method 3**: Looks for common HID report patterns

## Tips

- The device may not send data continuously
- Try using the headset actively (play audio, adjust the volume) to trigger communication
- The raw data is always displayed for manual analysis
- The exact format depends on the manufacturer's implementation

## Troubleshooting

### "Permission denied"
- Run with `sudo` or set up udev rules

### "Device not found"
- Check that the headset is connected: `lsusb | grep JBL`
- Check which hidraw matches: `ls -la /sys/bus/hid/devices/0003:0ECB:2088.0006/hidraw`

### "No data received"
- The device may not be sending data automatically
- Try using the headset (play audio, press buttons)
- Some devices require specific commands to report the battery

### hidraw change
If the hidraw number changes (no longer hidraw5), edit the script and change:
```python
HIDRAW_DEVICE = "/dev/hidraw5"  # Change to the correct number
```

To find out which hidraw matches the device:
```bash
ls -la /sys/bus/hid/devices/0003:0ECB:2088.0006/hidraw
```