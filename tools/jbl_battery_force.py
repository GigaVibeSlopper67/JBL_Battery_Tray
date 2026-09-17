#!/usr/bin/env python3
"""
Script to force the JBL Quantum910 to send battery information
Analyzes what is sent during connection and tries to replicate commands
"""

import os
import sys
import time
import struct

HIDRAW_DEVICE = "/dev/hidraw5"


def check_permissions():
    """Checks whether we have permission to access the hidraw"""
    if not os.path.exists(HIDRAW_DEVICE):
        print(f"Error: {HIDRAW_DEVICE} not found")
        return False

    if not os.access(HIDRAW_DEVICE, os.R_OK | os.W_OK):
        print(f"Error: No permission to read/write {HIDRAW_DEVICE}")
        print(f"Current permissions: {oct(os.stat(HIDRAW_DEVICE).st_mode)[-3:]}")
        print("\nSolutions:")
        print(f"1. Run as root: sudo python3 {sys.argv[0]}")
        print(f"2. Or fix permissions: sudo chmod 666 {HIDRAW_DEVICE}")
        return False

    return True


def send_feature_report(device, report_id, data=None):
    """Sends a HID feature report (command to the device)"""
    # Feature reports usually start with the Report ID
    if data is None:
        payload = bytes([report_id] + [0] * 63)  # 64 bytes total
    else:
        payload = bytes([report_id] + list(data[:63]))  # Report ID + data

    try:
        # IOCTL to send a feature report
        # Linux uses the HIDIOCSFEATURE ioctl
        import fcntl
        import termios

        # HIDIOCSFEATURE(len) - sends a feature report
        # HIDIOCGFEATURE(len) - receives a feature report
        HIDIOCSFEATURE = 0xC0094806  # _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x06, len)
        HIDIOCGFEATURE = 0xC0094807  # _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x07, len)

        # Try to send the feature report
        result = fcntl.ioctl(device.fileno(), HIDIOCSFEATURE, payload)
        return True
    except Exception as e:
        print(f"  Error sending feature report: {e}")
        return False


def try_commands(device):
    """Tries different commands to request the battery"""
    print("\n🔧 Trying to send commands to request the battery...")
    print("=" * 60)

    # Common commands to request battery on HID devices
    commands_to_try = [
        # Simple command with Report ID 0x08 (what we receive)
        (0x08, [0x08]),

        # Feature report with Report ID 0x08
        (0x08, None),

        # Other common Report IDs
        (0x01, [0x01]),
        (0x02, [0x02]),
        (0x03, [0x03]),
        (0x04, [0x04]),
        (0x05, [0x05]),
        (0x06, [0x06]),
        (0x07, [0x07]),
        (0x09, [0x09]),

        # Status request commands
        (0x01, [0x01, 0x00]),  # Request status
        (0x08, [0x08, 0x00]),  # Request battery specifically

        # Common pattern: [Report ID, Command, ...]
        (0x08, [0x08, 0x01]),  # Command 0x01 = request
        (0x08, [0x08, 0x02]),  # Command 0x02 = status
    ]

    for report_id, data in commands_to_try:
        hex_cmd = ' '.join([f'{b:02x}' for b in ([report_id] + (data or []))[:8]])
        print(f"\n📤 Trying: Report ID 0x{report_id:02x}, Data: {hex_cmd}")

        # Try writing directly to the hidraw
        try:
            if data:
                cmd_bytes = bytes([report_id] + list(data))
            else:
                cmd_bytes = bytes([report_id] + [0] * 63)

            device.write(cmd_bytes)
            print(f"  ✓ Command sent: {hex_cmd}")

            # Wait for a response
            time.sleep(0.3)

            # Try to read the response (no settimeout; uses select or polling)
            import select
            ready, _, _ = select.select([device], [], [], 0.5)
            if ready:
                try:
                    response = device.read(64)
                    if response:
                        resp_bytes = list(response)
                        hex_resp = ' '.join([f'{b:02x}' for b in resp_bytes[:8]])
                        print(f"  📥 Response received: {hex_resp}")

                        # Check if it's battery
                        if len(resp_bytes) >= 2 and resp_bytes[0] == 0x08 and 0 <= resp_bytes[1] <= 100:
                            print(f"  ⚡⚡⚡ BATTERY FOUND: {resp_bytes[1]}% ⚡⚡⚡")
                            return resp_bytes[1]
                except Exception:
                    pass
            else:
                # Try reading even without select (may block, but we try)
                try:
                    # Set non-blocking mode if possible
                    import fcntl
                    flags = fcntl.fcntl(device.fileno(), fcntl.F_GETFL)
                    fcntl.fcntl(device.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)

                    response = device.read(64)
                    if response:
                        resp_bytes = list(response)
                        hex_resp = ' '.join([f'{b:02x}' for b in resp_bytes[:8]])
                        print(f"  📥 Response received: {hex_resp}")

                        if len(resp_bytes) >= 2 and resp_bytes[0] == 0x08 and 0 <= resp_bytes[1] <= 100:
                            print(f"  ⚡⚡⚡ BATTERY FOUND: {resp_bytes[1]}% ⚡⚡⚡")
                            return resp_bytes[1]

                    # Restore flags
                    fcntl.fcntl(device.fileno(), fcntl.F_SETFL, flags)
                except Exception:
                    pass

        except Exception as e:
            print(f"  ✗ Error: {e}")

        time.sleep(0.1)

    return None


def monitor_connection():
    """Monitors during connection/disconnection to capture commands"""
    print("JBL Quantum910 - Connection Analysis and Battery Forcing")
    print("=" * 60)
    print(f"Device: {HIDRAW_DEVICE}")
    print()

    if not check_permissions():
        sys.exit(1)

    print("📋 INSTRUCTIONS:")
    print("1. This script will monitor the device")
    print("2. DISCONNECT the headset USB now")
    print("3. Wait 2 seconds")
    print("4. CONNECT the headset USB again")
    print("5. The script will capture everything that happens")
    print()
    print("Press Enter when you are ready to start...")
    input()

    print("\n⏳ Waiting for disconnection...")
    print("(Disconnect the headset USB now)")

    # Monitor until the device disappears
    while os.path.exists(HIDRAW_DEVICE):
        time.sleep(0.1)

    print("✓ Device disconnected")
    time.sleep(2)

    print("\n⏳ Waiting for reconnection...")
    print("(Connect the headset USB now)")

    # Wait for reconnection
    timeout = 10
    start_time = time.time()
    while not os.path.exists(HIDRAW_DEVICE):
        if time.time() - start_time > timeout:
            print("✗ Timeout: Device did not reconnect")
            sys.exit(1)
        time.sleep(0.1)

    print("✓ Device reconnected!")
    time.sleep(0.5)  # Wait for it to settle

    # Now monitor everything that happens
    print("\n📡 Monitoring communication during initialization...")
    print("=" * 60)

    try:
        with open(HIDRAW_DEVICE, 'rb+') as f:  # rb+ for reading and writing
            # First, try to read everything the device sends
            print("\n📥 Reading data received from the device...")
            packets_received = []

            for i in range(20):  # Try to read up to 20 packets
                try:
                    f.settimeout(0.5)
                    data = f.read(64)
                    if data:
                        data_bytes = list(data)
                        hex_data = ' '.join([f'{b:02x}' for b in data_bytes])
                        timestamp = time.strftime('%H:%M:%S.%f')[:-3]
                        print(f"[{timestamp}] 📥 Received ({len(data_bytes)} bytes): {hex_data}")

                        # Check if it's battery
                        if len(data_bytes) >= 2 and data_bytes[0] == 0x08 and 0 <= data_bytes[1] <= 100:
                            print(f"  ⚡⚡⚡ BATTERY: {data_bytes[1]}% ⚡⚡⚡")

                        packets_received.append(data_bytes)
                    else:
                        break
                except Exception:
                    break
                time.sleep(0.1)

            # Now try sending commands
            if packets_received:
                print(f"\n✓ Received {len(packets_received)} packets during initialization")
                print("\nNow trying to force battery data with commands...")
            else:
                print("\n⚠ No packet received automatically")
                print("Trying to force with commands...")

            battery = try_commands(f)

            if battery is not None:
                print(f"\n✅ SUCCESS! Battery obtained: {battery}%")
            else:
                print("\n⚠ Could not force battery data")
                print("The attempted commands did not work.")
                print("\n💡 Tip: The device may send battery data only:")
                print("  - During initialization (connection)")
                print("  - When you press buttons")
                print("  - At specific intervals")

            # Keep monitoring
            print("\n📡 Continuing monitoring... (Ctrl+C to stop)")
            print("=" * 60)

            last_battery = None
            while True:
                try:
                    f.settimeout(1.0)
                    data = f.read(64)
                    if data:
                        data_bytes = list(data)
                        hex_data = ' '.join([f'{b:02x}' for b in data_bytes])
                        timestamp = time.strftime('%H:%M:%S')

                        if len(data_bytes) >= 2 and data_bytes[0] == 0x08 and 0 <= data_bytes[1] <= 100:
                            battery = data_bytes[1]
                            if battery != last_battery:
                                print(f"[{timestamp}] ⚡ BATTERY: {battery}%")
                                last_battery = battery
                        else:
                            print(f"[{timestamp}] Dados: {hex_data}")

                except Exception:
                    time.sleep(0.5)

    except PermissionError:
        print(f"Error: Permission denied for {HIDRAW_DEVICE}")
        print("Run as root or fix permissions")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    monitor_connection()

