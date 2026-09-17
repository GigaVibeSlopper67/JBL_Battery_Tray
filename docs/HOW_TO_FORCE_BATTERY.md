# How to Force Battery Information Reporting

## Problem

The JBL Quantum910 only sends battery information when:
- The USB cable is connected/disconnected
- Buttons are pressed
- At specific intervals (not continuous)

## Solutions

### 1. Capture Script During Connection

Use `jbl_battery_capture.py` to:
- Capture everything that happens during connection
- Analyze the received packets
- Try to force a response with feature reports

```bash
sudo python3 jbl_battery_capture.py
```

**How to use:**
1. Run the script
2. Disconnect the headset's USB cable
3. Reconnect the headset's USB cable
4. The script will capture and analyze everything

### 2. Brute-Force Script

Use `jbl_battery_force.py` to:
- Try several different commands
- Use HID feature reports
- Force the device to respond

```bash
sudo python3 jbl_battery_force.py
```

### 3. Continuous Monitoring with Buttons

The `jbl_battery_simple.py` script works when you:
- Press the headset buttons
- Adjust the volume
- Use the headset controls

```bash
sudo python3 jbl_battery_simple.py
```

## Data Analysis

### Identified Pattern

When the device sends the battery info:
```
08 1e = [8, 30] = 30% battery
```

- **Byte 0**: Report ID = `0x08` (fixed)
- **Byte 1**: Battery level = `0x1e` (30) = **30%**

### What to Try

1. **HID Feature Reports**
   - Report ID 0x08 (the one we receive)
   - Other common Report IDs (0x01-0x09)

2. **Request Commands**
   - Some devices respond to GET feature reports
   - It may be necessary to send a specific command

3. **Timing**
   - The device may send the battery only at specific moments
   - During startup is the most reliable

## Limitations

- The device may not respond to external commands
- Physical buttons may be required
- Some devices only send data when there is a state change

## Next Steps

1. Run `jbl_battery_capture.py` and analyze the packets
2. Try to identify any pattern in the commands
3. Use the headset buttons to trigger the reporting when needed