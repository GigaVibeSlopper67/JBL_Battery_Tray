#!/usr/bin/env python3
"""
Alternative script using hidapi to intercept USB communication
from the JBL Quantum910 Wireless and extract battery information
"""

import sys

try:
    import hid
except ImportError:
    print("Installing hidapi...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "hidapi", "--user"])
    import hid

VENDOR_ID = 0x0ecb
PRODUCT_IDS = (0x2088, 0x2069)


def find_and_monitor():
    """Finds the device and monitors communication"""
    print("JBL Quantum 910/810 - Battery Monitor via HID")
    print("=" * 60)
    print()

    # List all HID devices
    print("Searching for HID devices...")
    devices = hid.enumerate()

    jbl_device = None
    for device_info in devices:
        if device_info['vendor_id'] == VENDOR_ID and device_info['product_id'] in PRODUCT_IDS:
            jbl_device = device_info
            print(f"Device found!")
            print(f"  Path: {device_info['path']}")
            print(f"  Manufacturer: {device_info['manufacturer_string']}")
            print(f"  Product: {device_info['product_string']}")
            print(f"  Serial: {device_info['serial_number']}")
            print(f"  Interface: {device_info['interface_number']}")
            break

    if jbl_device is None:
        print("Device not found!")
        return

    print()
    print("=" * 60)
    print("Monitoring communication...")
    print("Press Ctrl+C to stop\n")

    try:
        # Open the device
        device = hid.device()
        device.open_path(jbl_device['path'])

        # Set non-blocking mode if possible
        device.set_nonblocking(True)

        print("Reading data from the device...\n")

        battery_level = None

        while True:
            try:
                # Read data (max 64 bytes)
                data = device.read(64)

                if data:
                    hex_data = ' '.join([f'{b:02x}' for b in data])
                    print(f"[{__import__('time').strftime('%H:%M:%S')}] Data ({len(data)} bytes): {hex_data}")
                    print(f"  Bytes: {list(data)}")

                    # Try to interpret the battery level
                    for i, byte in enumerate(data):
                        if 0 <= byte <= 100:
                            if battery_level != byte:
                                battery_level = byte
                                print(f"  ⚡ Battery level: {battery_level}% (position {i})")

                    # Check for a 16-bit pattern
                    if len(data) >= 2:
                        val_16 = int.from_bytes(data[:2], 'little')
                        if 0 <= val_16 <= 100 and battery_level != val_16:
                            battery_level = val_16
                            print(f"  ⚡ Battery level (16-bit): {battery_level}%")

                    print()

                # Small delay
                __import__('time').sleep(0.1)

            except Exception as e:
                if "would block" not in str(e).lower():
                    print(f"Error reading: {e}")
                __import__('time').sleep(0.1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            device.close()
        except Exception:
            pass


if __name__ == "__main__":
    find_and_monitor()

