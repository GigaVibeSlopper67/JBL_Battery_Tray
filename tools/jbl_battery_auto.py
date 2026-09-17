#!/usr/bin/env python3
"""
Script that automatically detects the JBL Quantum910 hidraw device
and monitors the battery - works even if the hidraw number changes
"""

import os
import sys
import time
import glob

VENDOR_ID = "0ecb"
PRODUCT_IDS = ("2088", "2069")  # Quantum 910, Quantum 810


def find_hidraw_device():
    """Automatically finds which hidraw corresponds to the JBL Quantum 910/810"""
    # Method 1: scan /sys/class/hidraw/*/device/uevent for HID_ID
    for hidraw_path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(hidraw_path, "device", "uevent")) as f:
                uevent = f.read()
        except OSError:
            continue
        vendor = product = None
        for line in uevent.splitlines():
            if line.startswith("HID_ID="):
                parts = line.split("=", 1)[1].split(":")
                if len(parts) == 3:
                    try:
                        vendor = f"{int(parts[1], 16):04x}"
                        product = f"{int(parts[2], 16):04x}"
                    except ValueError:
                        vendor = product = None
                break
        if vendor == VENDOR_ID and product in PRODUCT_IDS:
            return f"/dev/{os.path.basename(hidraw_path)}"

    # Method 2: Try all available hidraw devices
    print("⚠ Not found in /sys, trying all available hidraw devices...")
    for hidraw in sorted(glob.glob("/dev/hidraw*")):
        try:
            # Try reading bytes to see if it's the right device
            with open(hidraw, 'rb') as f:
                import select
                ready, _, _ = select.select([f], [], [], 0.1)
                if ready:
                    data = f.read(64)
                    if data and len(data) >= 2:
                        data_bytes = list(data)
                        # Check for the known battery pattern
                        if data_bytes[0] == 0x08 and 0 <= data_bytes[1] <= 100:
                            print(f"✓ Found battery pattern on {hidraw}")
                            return hidraw
        except Exception:
            pass

    return None


def check_permissions(hidraw_device):
    """Checks whether we have permission to access the hidraw"""
    if not os.path.exists(hidraw_device):
        print(f"Error: {hidraw_device} not found")
        return False

    if not os.access(hidraw_device, os.R_OK):
        print(f"Error: No permission to read {hidraw_device}")
        print(f"Current permissions: {oct(os.stat(hidraw_device).st_mode)[-3:]}")
        print("\nSolutions:")
        print(f"1. Run as root: sudo python3 {sys.argv[0]}")
        print(f"2. Or fix permissions: sudo chmod 666 {hidraw_device}")
        return False

    return True


def read_battery():
    """Reads and displays the battery level"""
    print("JBL Quantum 910/810 - Battery Monitor (Automatic Detection)")
    print("=" * 60)

    # Detect the device
    print("Searching for the device...")
    hidraw_device = find_hidraw_device()

    if not hidraw_device:
        print("\n✗ JBL Quantum 910/810 device not found")
        print("\nPossible causes:")
        print("1. The headset is not connected via USB")
        print("2. The device is not being recognized as HID")
        print("3. Check with: lsusb | grep JBL")
        print("\n💡 Tip: Try disconnecting and reconnecting the headset")
        sys.exit(1)

    print(f"✓ Device found: {hidraw_device}")
    print("Identified pattern: [Report ID=0x08, Battery%]")
    print("Example: 08 1e = [8, 30] = 30% battery")
    print()

    if not check_permissions(hidraw_device):
        sys.exit(1)

    print("Monitoring battery level...")
    print("Press Ctrl+C to stop\n")

    last_battery = None
    last_report_id = None
    last_update_time = None
    update_count = 0

    try:
        with open(hidraw_device, 'rb') as f:
            print("Waiting for data... (The device sends periodically)\n")
            print("=" * 60)

            while True:
                try:
                    # Read data (max 64 bytes)
                    data = f.read(64)

                    if data and len(data) >= 2:
                        data_bytes = list(data)
                        report_id = data_bytes[0]
                        battery = data_bytes[1]

                        # Check if it's a valid battery packet
                        if report_id == 0x08 and 0 <= battery <= 100:
                            update_count += 1
                            current_time = time.time()

                            # Only show if it changed or it's the first time
                            if battery != last_battery or last_battery is None:
                                timestamp = time.strftime('%H:%M:%S')

                                # Calculate the interval since the last update
                                interval_str = ""
                                if last_update_time:
                                    interval = current_time - last_update_time
                                    if interval > 1:
                                        interval_str = f" (after {interval:.1f}s)"

                                print(f"\n[{timestamp}] ⚡ BATTERY: {battery}%{interval_str}")

                                # Visual battery bar
                                bar_length = 20
                                filled = int((battery / 100) * bar_length)
                                bar = "█" * filled + "░" * (bar_length - filled)
                                print(f"  [{bar}] {battery}%")

                                # Battery status
                                if battery >= 80:
                                    status = "🔋 Full"
                                elif battery >= 50:
                                    status = "🔋 Good"
                                elif battery >= 20:
                                    status = "🔋 Medium"
                                else:
                                    status = "🔋 Low"

                                print(f"  Status: {status}")

                                # Show raw data
                                hex_data = ' '.join([f'{b:02x}' for b in data_bytes[:min(8, len(data_bytes))]])
                                print(f"  Data: {hex_data} = [Report ID: {report_id}, Battery: {battery}%]")
                                print()

                                last_battery = battery
                                last_report_id = report_id
                                last_update_time = current_time

                    time.sleep(0.1)

                except BlockingIOError:
                    # No data available - normal
                    time.sleep(0.5)
                except OSError as e:
                    # I/O errors (device disconnected, in use, etc.)
                    if e.errno == 5:  # Input/output error
                        print(f"\n⚠ I/O error: Device may be in use or disconnected")
                        print(f"   Make sure the headset is connected and not in use by another program")
                        print(f"   Waiting 2 seconds before trying again...\n")
                        time.sleep(2)
                        # Try to detect again
                        new_hidraw = find_hidraw_device()
                        if new_hidraw and new_hidraw != hidraw_device:
                            print(f"⚠ Device changed from {hidraw_device} to {new_hidraw}")
                            print("   Reconnecting...")
                            hidraw_device = new_hidraw
                            f.close()
                            f = open(hidraw_device, 'rb')
                    else:
                        print(f"⚠ System error: {e} (errno: {e.errno})")
                        time.sleep(1)
                except Exception as e:
                    print(f"⚠ Unexpected error: {e}")
                    time.sleep(1)

    except PermissionError:
        print(f"Error: Permission denied for {hidraw_device}")
        print("Run as root or fix permissions")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        if last_battery is not None:
            print(f"⚡ Last battery level: {last_battery}%")
            print(f"📦 Report ID: {last_report_id} (0x{last_report_id:02x})")
            print(f"📈 Total updates received: {update_count}")
            if last_update_time:
                time_since_update = time.time() - last_update_time
                print(f"⏱️  Last update {time_since_update:.1f} seconds ago")
        else:
            print("⚠ No battery data received")
        print("=" * 60)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    read_battery()

