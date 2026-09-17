# How to Use the JBL Quantum910 Data Monitor

## Main Script

**`/tmp/jbl_battery_hidraw.py`** - Full version with detailed analysis

## Basic Execution

```bash
sudo python3 /tmp/jbl_battery_hidraw.py
```

## With Logging to a File

```bash
sudo python3 /tmp/jbl_battery_hidraw.py --log
```

The log is saved to `/tmp/jbl_battery_log_YYYYMMDD_HHMMSS.txt`

## What the Script Shows

For each received packet, the script displays:

1. **Packet Information**
   - Packet number
   - Timestamp
   - Size in bytes

2. **Hexadecimal Data**
   - Simple format (all bytes)
   - Grouped format (8 bytes per line with offset)

3. **Decimal Data**
   - All values in decimal format

4. **Detailed Table**
   - Each byte shown with:
     - Position (index)
     - Hexadecimal
     - Decimal
     - Binary (8 bits)
     - ASCII (if applicable)

5. **Detailed Analysis**
   - Interpretation of each individual byte
   - Multi-byte pattern analysis (16-bit, 32-bit)
   - Comparison with the previous packet
   - Common HID interpretations
   - Battery candidates
   - Detected sequences

6. **Automatic Battery Detection**
   - Identifies values between 0-100 that could be percentages
   - Highlights possible battery values when found

## Analysis Tips

1. **When you press buttons**, watch which bytes change
2. **Compare different packets** to identify patterns
3. **Values between 0-100** are battery candidates
4. **The first byte** is usually the Report ID on HID devices
5. **Sequences** may indicate related values (e.g. volume, battery, etc.)

## Output Example

```
============================================================
PACKET #1 - 14:30:25.123
============================================================
Size: 8 bytes

HEXADECIMAL DATA:
  01 00 00 4f 00 00 00 00

FORMATTED HEXADECIMAL (8 bytes/line):
  [00] 01 00 00 4f 00 00 00 00

DECIMAL DATA:
    1   0   0  79   0   0   0   0

DETAILED TABLE (Byte | Hex | Dec | Bin | ASCII):
  --------------------------------------------------------
  [ 0] 0x01 |   1 | 00000001 | '.'
  [ 1] 0x00 |   0 | 00000000 | '.'
  [ 2] 0x00 |   0 | 00000000 | '.'
  [ 3] 0x4f |  79 | 01001111 | 'O'
  ...

  BATTERY LEVEL DETECTED: 79% (byte 3)
```

## Manual Analysis

If automatic detection doesn't find the battery, analyze manually:

1. **Look for values that change slowly** (the battery doesn't change every second)
2. **Compare packets when you know the battery changed** (e.g. after charging)
3. **Watch for patterns** - the battery is usually in a fixed position
4. **Values may be on a different scale** (e.g. 0-255 for 0-100%)

## Troubleshooting

- **No data received**: Try using the headset (buttons, volume, etc.)
- **Permission denied**: Run with `sudo`
- **Lots of duplicate data**: Normal, the script ignores consecutive duplicates