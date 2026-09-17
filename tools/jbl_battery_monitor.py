#!/usr/bin/env python3
"""
Script to intercept USB communication from the JBL Quantum910 Wireless
and extract battery information
"""

import usb.core
import usb.util
import sys
import time
import struct

# Supported JBL Quantum dongles: 910 Wireless (0x2088), 810 Wireless (0x2069)
VENDOR_ID = 0x0ecb
PRODUCT_IDS = (0x2088, 0x2069)


def find_device():
    """Finds the USB device (Quantum 910 or 810)"""
    device = None
    for product_id in PRODUCT_IDS:
        device = usb.core.find(idVendor=VENDOR_ID, idProduct=product_id)
        if device is not None:
            break
    if device is None:
        raise ValueError("Device not found. Make sure the headset is connected.")
    return device


def setup_device(device):
    """Sets up the device for communication"""
    # Vendor HID interface: 3 on the Quantum 910, 5 on the Quantum 810.
    interface = 3 if device.idProduct == 0x2088 else 5
    # Try to detach the kernel driver if necessary
    try:
        if device.is_kernel_driver_active(interface):
            device.detach_kernel_driver(interface)
    except (ValueError, usb.core.USBError) as e:
        print(f"Warning: Could not detach the kernel driver: {e}")

    # Set up the HID interface
    try:
        usb.util.claim_interface(device, interface)
    except usb.core.USBError as e:
        print(f"Error claiming interface: {e}")
        print("Try running as root or configure udev rules")
        sys.exit(1)

    return device


def read_hid_reports(device, timeout=1000):
    """Reads HID reports from the device"""
    # Vendor HID interface: 3 on the Quantum 910, 5 on the Quantum 810.
    interface = 3 if device.idProduct == 0x2088 else 5
    endpoint = device[0][(interface, 0)][0]

    print("Monitoring USB communication...")
    print("Identified pattern: [Report ID=0x08, Battery%]")
    print("Press Ctrl+C to stop\n")

    battery_level = None
    last_battery = None
    last_report_id = None
    last_update_time = None
    update_count = 0
    silent_mode = False  # Silent mode - only show when it changes

    try:
        while True:
            try:
                # Read data from the endpoint (max 64 bytes per wMaxPacketSize)
                data = device.read(endpoint.bEndpointAddress, endpoint.wMaxPacketSize, timeout)

                # Convert to a list of bytes
                data_bytes = list(data)

                # Identified pattern: [Report ID=0x08, Battery%]
                if len(data_bytes) >= 2:
                    report_id = data_bytes[0]
                    battery = data_bytes[1]

                    # Check if it's the known battery pattern
                    if report_id == 0x08 and 0 <= battery <= 100:
                        update_count += 1
                        current_time = time.time()

                        # Only show if it changed or it's the first time
                        if battery != last_battery or last_battery is None:
                            battery_level = battery
                            timestamp = time.strftime('%H:%M:%S')

                            # Calculate the interval since the last update
                            interval_str = ""
                            if last_update_time:
                                interval = current_time - last_update_time
                                if interval > 1:
                                    interval_str = f" (after {interval:.1f}s)"

                            print(f"\n[{timestamp}] ⚡⚡⚡ BATTERY: {battery_level}% ⚡⚡⚡{interval_str}")

                            # Visual bar
                            bar_length = 20
                            filled = int((battery / 100) * bar_length)
                            bar = "█" * filled + "░" * (bar_length - filled)
                            print(f"  [{bar}] {battery}%")

                            # Status
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
                            hex_data = ' '.join([f'{b:02x}' for b in data_bytes])
                            print(f"  Data: {hex_data} = [Report ID: {report_id}, Battery: {battery}%]")

                            last_battery = battery
                            last_report_id = report_id
                            last_update_time = current_time
                        elif not silent_mode:
                            # Verbose mode - show all updates
                            timestamp = time.strftime('%H:%M:%S')
                            print(f"[{timestamp}] Battery: {battery}% (no change) - Total updates: {update_count}")
                    else:
                        # Other packets - show only if not silent
                        if not silent_mode:
                            hex_data = ' '.join([f'{b:02x}' for b in data_bytes])
                            timestamp = time.strftime('%H:%M:%S')
                            print(f"[{timestamp}] Other packet: {hex_data}")

                            # Try other methods for other packets
                            for i, byte in enumerate(data_bytes):
                                if 0 <= byte <= 100:
                                    if battery_level != byte:
                                        battery_level = byte
                                        print(f"  → Possible battery level found: {battery_level}% (byte {i})")

                time.sleep(0.1)  # Small delay to avoid overloading

                time.sleep(0.1)  # Small delay to avoid overloading

            except usb.core.USBError as e:
                if e.errno == 110:  # ETIMEDOUT
                    # Timeout is normal when there is no data
                    continue
                elif e.errno == 5:  # Input/output error
                    print(f"\n⚠ USB I/O error: Device may be in use or disconnected")
                    print(f"   Make sure the headset is connected and not in use by another program")
                    print(f"   Waiting 2 seconds...\n")
                    time.sleep(2)
                else:
                    print(f"⚠ USB error: {e} (errno: {e.errno})")
                    time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        if battery_level is not None:
            print(f"⚡ Last battery level: {battery_level}%")
            if last_report_id is not None:
                print(f"📦 Report ID: {last_report_id} (0x{last_report_id:02x})")
            print(f"📈 Total updates received: {update_count}")
            if last_update_time:
                time_since_update = time.time() - last_update_time
                print(f"⏱️  Last update {time_since_update:.1f} seconds ago")
        else:
            print("⚠ No battery data received")
        print("=" * 60)
    finally:
        # Release the interface
        try:
            usb.util.release_interface(device, interface)
        except Exception:
            pass


def get_device_info(device):
    """Gets device information"""
    print("=" * 60)
    print("Device Information")
    print("=" * 60)
    print(f"Vendor ID: 0x{device.idVendor:04x}")
    print(f"Product ID: 0x{device.idProduct:04x}")
    try:
        print(f"Manufacturer: {usb.util.get_string(device, device.iManufacturer)}")
    except Exception:
        print(f"Manufacturer: (not available)")
    try:
        print(f"Product: {usb.util.get_string(device, device.iProduct)}")
    except Exception:
        print(f"Product: (not available)")
    try:
        print(f"Serial: {usb.util.get_string(device, device.iSerialNumber)}")
    except Exception:
        print(f"Serial: (not available)")
    print()

    # HID interface information
    try:
        cfg = device.get_active_configuration()
        interface = 3 if device.idProduct == 0x2088 else 5
        intf = cfg[(interface, 0)]
        print(f"Interface HID: {intf.bInterfaceNumber}")
        print(f"Endpoints: {len(intf)}")
        for ep in intf:
            print(
                f"  - Endpoint 0x{ep.bEndpointAddress:02x}: "
                f"{'IN' if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_IN else 'OUT'}, "
                f"Max packet size: {ep.wMaxPacketSize} bytes"
            )
    except Exception:
        pass
    print("=" * 60)
    print()


def main():
    print("JBL Quantum 910/810 - Battery Monitor via USB")
    print("=" * 60)
    print()

    try:
        # Find the device
        device = find_device()

        # Get information
        get_device_info(device)

        # Set up the device
        device = setup_device(device)

        # Start monitoring
        read_hid_reports(device)

    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except PermissionError:
        print("Error: Permission denied. Run as root or configure udev rules:")
        print("  sudo chmod 666 /dev/bus/usb/001/007")
        print("  or create a udev rule for permanent access")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

