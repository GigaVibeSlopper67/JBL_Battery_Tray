#!/usr/bin/env python3
"""
Script to automatically find which hidraw device corresponds to the JBL Quantum910
"""

import os
import sys

VENDOR_ID = "0ecb"
PRODUCT_IDS = ("2088", "2069")  # Quantum 910, Quantum 810


def find_jbl_hidraw():
    """Finds the hidraw corresponding to the JBL Quantum 910/810"""
    import glob
    print("Searching for the JBL Quantum 910/810 device...")
    print(f"Vendor ID: 0x{VENDOR_ID}, Product IDs: 0x{' / 0x'.join(PRODUCT_IDS)}")
    print()

    found_devices = []

    # Scan /sys/class/hidraw/*/device/uevent for HID_ID
    for hidraw_path in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(os.path.join(hidraw_path, "device", "uevent"), "r") as f:
                uevent = f.read()
        except OSError:
            continue

        vendor = product = None
        hid_name = "?"
        for line in uevent.splitlines():
            if line.startswith("HID_ID="):
                parts = line.split("=", 1)[1].split(":")
                if len(parts) == 3:
                    try:
                        vendor = f"{int(parts[1], 16):04x}"
                        product = f"{int(parts[2], 16):04x}"
                    except ValueError:
                        vendor = product = None
            elif line.startswith("HID_NAME="):
                hid_name = line.split("=", 1)[1].strip()

        if vendor != VENDOR_ID or product not in PRODUCT_IDS:
            continue

        hidraw_device = f"/dev/{os.path.basename(hidraw_path)}"
        print(f"✓ Device found: {hid_name}")
        print(f"✓ Hidraw found: {hidraw_device}")

        # Check permissions
        if os.access(hidraw_device, os.R_OK):
            print("✓ Read permission: OK")
        else:
            print("⚠ Read permission: DENIED")
            print(f"  Run: sudo chmod 666 {hidraw_device}")

        found_devices.append({
            "hidraw": hidraw_device,
            "hidraw_name": os.path.basename(hidraw_path),
        })

    if not found_devices:
        print("\n⚠ Device not found in /sys/class/hidraw")
        print("\nChecking lsusb...")
        import subprocess
        try:
            result = subprocess.run(["lsusb"], capture_output=True, text=True)
            if "0ecb" in result.stdout.lower() or "jbl" in result.stdout.lower() or "quantum" in result.stdout.lower():
                print("✓ Device found in lsusb:")
                for line in result.stdout.split("\n"):
                    if "0ecb" in line.lower() or "jbl" in line.lower() or "quantum" in line.lower():
                        print(f"  {line}")
                print("\n⚠ But it was not found in /sys/class/hidraw")
                print("  This may mean that:")
                print("  - The device is still being initialized")
                print("  - The HID driver is not loaded")
                print("  - Wait a few seconds and try again")
            else:
                print("✗ Device not found in lsusb")
                print("\nPossible causes:")
                print("1. The headset is not connected via USB")
                print("2. The USB cable is faulty")
                print("3. Try disconnecting and reconnecting the headset")
        except Exception:
            pass

        return None

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Devices found: {len(found_devices)}")

    for i, dev in enumerate(found_devices, 1):
        print(f"\nDevice {i}:")
        print(f"  Hidraw: {dev['hidraw']}")
        print(f"  Name: {dev['hidraw_name']}")

    # Return the first (or only) one
    return found_devices[0]['hidraw'] if found_devices else None


if __name__ == "__main__":
    hidraw = find_jbl_hidraw()

    if hidraw:
        print(f"\n{'='*60}")
        print(f"✅ USE THIS HIDRAW:")
        print(f"   {hidraw}")
        print(f"{'='*60}")
        print(f"\nTo use it in the scripts, edit the HIDRAW_DEVICE variable:")
        print(f"  HIDRAW_DEVICE = \"{hidraw}\"")
        print(f"\nOr run the scripts that detect it automatically.")
    else:
        print("\n❌ Could not find the device")
        sys.exit(1)

