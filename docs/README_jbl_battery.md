# JBL Quantum910 Wireless Battery Monitor

Scripts to intercept the USB communication of the JBL Quantum910 headset and extract battery information.

## Available Scripts

### 1. `jbl_battery_monitor.py` (using pyusb)
Main script that uses the `pyusb` library for direct communication with the USB device.

### 2. `jbl_battery_hidapi.py` (using hidapi)
Alternative script using `hidapi`, which can be easier to use on some systems.

## Requirements

```bash
pip3 install pyusb --user
# or
pip3 install hidapi --user
```

## Permissions

To access USB devices, you may need special permissions:

### Option 1: Run as root (not recommended)
```bash
sudo python3 /tmp/jbl_battery_monitor.py
```

### Option 2: Set up udev rules (recommended)
Create the file `/etc/udev/rules.d/99-jbl-quantum910.rules`:

```
SUBSYSTEM=="usb", ATTR{idVendor}=="0ecb", ATTR{idProduct}=="2088", MODE="0666"
```

Then reload the rules:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### Option 3: Add the user to the plugdev group
```bash
sudo usermod -a -G plugdev $USER
# Log out and log back in
```

## How to Use

1. Connect the JBL Quantum910 headset via USB
2. Run one of the scripts:
   ```bash
   python3 /tmp/jbl_battery_monitor.py
   # or
   python3 /tmp/jbl_battery_hidapi.py
   ```
3. The script will:
   - Show device information
   - Continuously monitor the USB communication
   - Try to identify the battery level in the received data
   - Display raw data in hexadecimal and decimal

## Data Interpretation

The script tries several interpretations of the received data:
- Looks for values between 0-100 that could represent a percentage
- Interprets data as 8-bit or 16-bit
- Looks for common HID report patterns

## Notes

- The battery level may not be sent continuously by the device
- You may need to use the headset actively for it to send data
- The exact data format depends on the manufacturer's implementation
- Some devices only send battery information when requested

## Troubleshooting

If the script doesn't find the device:
- Check that the headset is connected: `lsusb | grep JBL`
- Check permissions: `ls -la /dev/bus/usb/001/007`
- Try running as root to test

If no data is received:
- The device may not be sending data continuously
- Try using the headset (play audio, adjust the volume) to trigger communication
- Some devices require specific commands to report the battery