#!/usr/bin/env python3
"""
Script to capture what happens during connect/disconnect
and try to force the headset to send battery information
"""

import os
import sys
import time
import struct
import fcntl

HIDRAW_DEVICE = "/dev/hidraw5"

# IOCTLs para HID
HIDIOCSFEATURE = lambda len: 0xC0094806 | (len << 16)  # Send feature report
HIDIOCGFEATURE = lambda len: 0xC0094807 | (len << 16)  # Receive feature report


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


def send_feature_report(fd, report_id, data=None):
    """Sends a feature report using ioctl"""
    if data is None:
        payload = bytes([report_id] + [0] * 63)
    else:
        payload = bytes([report_id] + list(data[:63]))

    try:
        fcntl.ioctl(fd, HIDIOCSFEATURE(len(payload)), payload)
        return True
    except Exception:
        return False


def get_feature_report(fd, report_id, length=64):
    """Receives a feature report using ioctl"""
    payload = bytes([report_id] + [0] * (length - 1))
    try:
        fcntl.ioctl(fd, HIDIOCGFEATURE(length), payload)
        return list(payload)
    except Exception:
        return None


def monitor_connection():
    """Monitors during connection to capture what happens"""
    print("JBL Quantum910 - Data Capture During Connection")
    print("=" * 60)
    print(f"Device: {HIDRAW_DEVICE}")
    print()

    if not check_permissions():
        sys.exit(1)

    print("📋 INSTRUCTIONS:")
    print("1. The script will monitor continuously")
    print("2. DISCONNECT the headset USB")
    print("3. CONNECT the headset USB again")
    print("4. The script will capture everything that happens")
    print()
    print("Press Ctrl+C to stop\n")
    print("=" * 60)

    last_seen = os.path.exists(HIDRAW_DEVICE)
    packets_during_connection = []

    try:
        while True:
            # Check if the device is connected
            if os.path.exists(HIDRAW_DEVICE):
                if not last_seen:
                    # Device was just connected!
                    print(f"\n{'='*60}")
                    print(f"🔌 DEVICE CONNECTED - {time.strftime('%H:%M:%S')}")
                    print(f"{'='*60}\n")

                    time.sleep(0.5)  # Wait for it to settle

                    # Open and monitor intensively
                    with open(HIDRAW_DEVICE, 'rb') as f:
                        print("📡 Capturing data during initialization...")
                        print("-" * 60)

                        # Read everything that arrives in the first seconds
                        start_time = time.time()
                        import select
                        while time.time() - start_time < 3:  # 3 seconds
                            try:
                                # Use select to avoid blocking
                                ready, _, _ = select.select([f], [], [], 0.1)
                                if not ready:
                                    continue
                                data = f.read(64)
                                if data:
                                    data_bytes = list(data)
                                    hex_data = ' '.join([f'{b:02x}' for b in data_bytes])
                                    timestamp = time.strftime('%H:%M:%S.%f')[:-3]

                                    print(f"[{timestamp}] 📥 Received ({len(data_bytes)} bytes)")
                                    print(f"  Hex: {hex_data}")
                                    print(f"  Dec: {data_bytes}")

                                    # Check if it's battery
                                    if len(data_bytes) >= 2:
                                        if data_bytes[0] == 0x08 and 0 <= data_bytes[1] <= 100:
                                            print(f"  ⚡⚡⚡ BATTERY: {data_bytes[1]}% ⚡⚡⚡")

                                        # Packet analysis
                                        print(f"  📊 Analysis:")
                                        print(f"    - Byte[0] (Report ID): 0x{data_bytes[0]:02x} ({data_bytes[0]})")
                                        if len(data_bytes) > 1:
                                            print(f"    - Byte[1] (Battery?): 0x{data_bytes[1]:02x} ({data_bytes[1]})")

                                    packets_during_connection.append(data_bytes)
                                    print()

                            except Exception:
                                pass

                        print(f"✓ Captured {len(packets_during_connection)} packets during connection")
                        print("-" * 60)

                        # Now try to force with feature reports
                        print("\n🔧 Trying to force battery data...")
                        print("-" * 60)

                        # Try different feature reports
                        for report_id in [0x08, 0x01, 0x02, 0x03, 0x04, 0x05]:
                            print(f"\n📤 Trying Feature Report 0x{report_id:02x}...")

                            # Try to receive a feature report
                            try:
                                with open(HIDRAW_DEVICE, 'rb+') as f2:
                                    result = get_feature_report(f2.fileno(), report_id)
                                    if result:
                                        hex_resp = ' '.join([f'{b:02x}' for b in result[:8]])
                                        print(f"  📥 Response: {hex_resp}")

                                        if len(result) >= 2 and result[0] == 0x08 and 0 <= result[1] <= 100:
                                            print(f"  ⚡⚡⚡ BATTERY: {result[1]}% ⚡⚡⚡")
                                    else:
                                        print(f"  (No response)")

                                    # Try to send a feature report
                                    if send_feature_report(f2.fileno(), report_id):
                                        print(f"  ✓ Command sent")
                                        time.sleep(0.2)

                                    # Try to read the response
                                    try:
                                        import select
                                        ready, _, _ = select.select([f2], [], [], 0.3)
                                        if ready:
                                            resp = f2.read(64)
                                            if resp:
                                                resp_bytes = list(resp)
                                                hex_resp = ' '.join([f'{b:02x}' for b in resp_bytes[:8]])
                                                print(f"  📥 Response: {hex_resp}")

                                                if len(resp_bytes) >= 2 and resp_bytes[0] == 0x08 and 0 <= resp_bytes[1] <= 100:
                                                    print(f"  ⚡⚡⚡ BATTERY: {resp_bytes[1]}% ⚡⚡⚡")
                                    except Exception:
                                        pass
                            except Exception as e:
                                print(f"  ✗ Error: {e}")

                            time.sleep(0.2)

                last_seen = True

                # Monitora continuamente
                try:
                    with open(HIDRAW_DEVICE, 'rb') as f:
                        import select
                        ready, _, _ = select.select([f], [], [], 0.5)
                        if ready:
                            data = f.read(64)
                            if data:
                                data_bytes = list(data)
                                hex_data = ' '.join([f'{b:02x}' for b in data_bytes])

                                if len(data_bytes) >= 2 and data_bytes[0] == 0x08 and 0 <= data_bytes[1] <= 100:
                                    timestamp = time.strftime('%H:%M:%S')
                                    print(f"[{timestamp}] ⚡ BATTERY: {data_bytes[1]}%")
                except Exception:
                    pass
            else:
                if last_seen:
                    print(f"\n🔌 Device disconnected - {time.strftime('%H:%M:%S')}")
                    packets_during_connection = []
                last_seen = False

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        if packets_during_connection:
            print(f"Packets captured during connection: {len(packets_during_connection)}")
            print("\nUnique packets:")
            seen = set()
            for pkt in packets_during_connection:
                pkt_str = ' '.join([f'{b:02x}' for b in pkt])
                if pkt_str not in seen:
                    print(f"  {pkt_str}")
                    seen.add(pkt_str)
        print("=" * 60)


if __name__ == "__main__":
    monitor_connection()

