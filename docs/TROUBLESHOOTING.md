# Troubleshooting - Common Errors

## Error: `[Errno 5] Input/output error`

### Cause
This error usually occurs when:
1. The device is being used by another program
2. The device was disconnected during reading
3. A kernel driver is controlling the device
4. There is an access conflict with the device

### Solutions

#### 1. Check if another program is using the device

```bash
# See processes using the device
lsof /dev/hidraw5
# or
fuser /dev/hidraw5
```

If there are processes, terminate them:
```bash
sudo kill <PID>
```

#### 2. Check if the device is connected

```bash
lsusb | grep JBL
ls -la /dev/hidraw5
```

If it doesn't appear, the device was disconnected.

#### 3. Detach the kernel driver (if using pyusb)

```bash
# Check which driver is being used
lsmod | grep usbhid

# Detach (may be necessary)
sudo modprobe -r usbhid
sudo modprobe usbhid
```

**Careful:** This may affect other USB HID devices.

#### 4. Restart the device

1. Disconnect the headset's USB cable
2. Wait 2 seconds
3. Reconnect the headset's USB cable
4. Run the script again

#### 5. Check permissions

```bash
ls -la /dev/hidraw5
# It should show: crw-rw-rw- or crw-rw----

# If you don't have permission:
sudo chmod 666 /dev/hidraw5
```

#### 6. Use a script that doesn't need pyusb

If the error occurs with `jbl_battery_monitor.py` (pyusb), use:

```bash
sudo python3 jbl_battery_simple.py
# or
sudo python3 jbl_battery_hidraw.py
```

These scripts use hidraw directly and are more stable.

## Error: `Permission denied`

### Solution
```bash
sudo python3 jbl_battery_simple.py
```

Or set up the udev rules (see `setup_udev_rules.sh`).

## Error: `ModuleNotFoundError: No module named 'usb'`

### Solution
```bash
# For a normal user
pip3 install pyusb --user

# For root (if using sudo)
sudo pip3 install pyusb
```

Or use scripts that don't need pyusb:
```bash
sudo python3 jbl_battery_simple.py
```

## Device doesn't send data

### Possible causes:
1. The device isn't sending data periodically
2. Buttons need to be pressed to trigger it
3. The device is in power-saving mode

### Solutions:
1. **Wait** - The device sends data every 7-11 seconds
2. **Press buttons** on the headset to trigger communication
3. **Use the headset** - Play audio, adjust the volume
4. **Reconnect** the device

## Script hangs or doesn't respond

### Solution:
1. Press `Ctrl+C` to stop it
2. Check that the device is connected
3. Restart the script

## Multiple I/O errors

If you get many I/O errors:

1. **Disconnect and reconnect** the headset
2. **Restart the script**
3. **Check** whether other programs are using the device:
   ```bash
   ps aux | grep -i jbl
   ps aux | grep -i quantum
   ```

## General Tips

1. **Use `jbl_battery_simple.py`** - It's the most stable
2. **Run with sudo** - Avoids permission problems
3. **Wait a few seconds** - The device sends data periodically
4. **Don't run multiple scripts at the same time** - It can cause conflicts

## If Nothing Works

1. Disconnect the headset
2. Wait 5 seconds
3. Reconnect the headset
4. Wait 2 seconds
5. Run:
   ```bash
   sudo python3 jbl_battery_simple.py
   ```

If it still doesn't work, check:
- Whether the device appears in `lsusb`
- Whether the hidraw exists: `ls -la /dev/hidraw*`
- Whether there are errors in dmesg: `dmesg | tail -20`