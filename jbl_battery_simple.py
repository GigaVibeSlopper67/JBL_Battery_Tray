#!/usr/bin/env python3
"""
Simplified script to monitor only the battery level of the JBL Quantum910
Uses pyusb (like jbl_battery_monitor.py) to ensure compatibility
"""

import sys
import time
import os
from datetime import datetime

try:
    import usb.core
    import usb.util
except ImportError:
    print("Error: pyusb not installed")
    print("Run: pip3 install pyusb --user")
    print("Or for root: sudo pip3 install pyusb")
    sys.exit(1)

# Supported JBL Quantum dongles: 910 Wireless (0x2088), 810 Wireless (0x2069)
VENDOR_ID = 0x0ecb
PRODUCT_IDS = (0x2088, 0x2069)

# Log file path
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

def log_print(*args, **kwargs):
    """Prints to the terminal and writes to the log file"""
    # Print to the terminal
    print(*args, **kwargs)
    
    # Write to the log file
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            # Strip the print line break and add a timestamp
            if args:
                message = ' '.join(str(arg) for arg in args)
            else:
                message = ''  # Empty line
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] {message}\n")
            f.flush()  # Ensure data is written immediately
    except Exception as e:
        # If writing to the log fails, just continue
        pass

def log_raw_data(data_bytes, description=""):
    """Writes received raw data to the log file"""
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            hex_data = ' '.join([f'{b:02x}' for b in data_bytes])
            if description:
                f.write(f"[{timestamp}] RAW DATA [{description}]: {hex_data} (len={len(data_bytes)})\n")
            else:
                f.write(f"[{timestamp}] RAW DATA: {hex_data} (len={len(data_bytes)})\n")
            f.flush()
    except Exception as e:
        pass

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
        pass  # Ignore if it fails
    
    # Set up the HID interface
    try:
        usb.util.claim_interface(device, interface)
    except usb.core.USBError as e:
        log_print(f"Error claiming interface: {e}")
        log_print("Try running as root or configure udev rules")
        sys.exit(1)
    
    return device

def read_battery():
    """Reads and displays the battery level"""
    log_print("JBL Quantum 910/810 - Simplified Battery Monitor")
    interface = 3  # vendor HID interface (3 on the Quantum 910, 5 on the 810)
    log_print("=" * 60)
    log_print("Identified pattern: [Report ID=0x08, Battery%]")
    log_print("Example: 08 1e = [8, 30] = 30% battery")
    log_print()
    
    try:
        # Find the device
        device = find_device()
        log_print(f"✓ Device found: 0x{device.idVendor:04x}:0x{device.idProduct:04x}")
        
        # Set up the device
        device = setup_device(device)
        
        # Vendor HID interface: 3 on the Quantum 910, 5 on the Quantum 810.
        interface = 3 if device.idProduct == 0x2088 else 5
        endpoint = device[0][(interface, 0)][0]
        
        log_print("Monitoring battery level...")
        log_print("Press Ctrl+C to stop\n")
        log_print("=" * 60)
        
        last_battery = None
        last_report_id = None
        last_update_time = None
        update_count = 0
        timeout_count = 0
        last_timeout_log = 0
        is_muted = False  # Mute state
        
        try:
            while True:
                try:
                    # Read data from the endpoint (max 64 bytes per wMaxPacketSize)
                    data = device.read(endpoint.bEndpointAddress, endpoint.wMaxPacketSize, 1000)
                    
                    # Convert to a list of bytes
                    data_bytes = list(data)
                    
                    # Identified pattern: [Report ID=0x08, Battery%]
                    if len(data_bytes) >= 2:
                        report_id = data_bytes[0]
                        battery = data_bytes[1]
                        
                        # Check if it's the mute pattern (Report ID 0x2f)
                        if report_id == 0x2f:
                            timestamp = time.strftime('%H:%M:%S')
                            if battery == 0x02:
                                # Mute button pressed - toggles the state
                                is_muted = not is_muted
                                status_text = "MUTED" if is_muted else "UNMUTED"
                                emoji = "🔇" if is_muted else "🎤"
                                log_print(f"\n[{timestamp}] {emoji} MICROPHONE {status_text} (button pressed)")
                                log_raw_data(data_bytes, f"MUTE TOGGLE -> {status_text}")
                                log_print()
                            elif battery == 0x00:
                                # Unmuted state (button release or initial state)
                                if is_muted:
                                    # If it was muted, this may be the button release
                                    log_raw_data(data_bytes, "MUTE RELEASE (0x2f 0x00)")
                                else:
                                    log_raw_data(data_bytes, "MUTE STATE: UNMUTED (0x2f 0x00)")
                            else:
                                # Other 0x2f value - log as unknown
                                log_raw_data(data_bytes, f"UNKNOWN MUTE PATTERN (Report ID: 0x2f, Value: 0x{battery:02x})")
                            continue
                        
                        # Check if it's the known battery pattern
                        if report_id == 0x08 and 0 <= battery <= 100:
                            # LOG ALL RECEIVED DATA (battery pattern)
                            log_raw_data(data_bytes, f"BATTERY: {battery}%")
                            
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
                                
                                log_print(f"\n[{timestamp}] ⚡ BATTERY: {battery}%{interval_str}")
                                
                                # Visual battery bar
                                bar_length = 20
                                filled = int((battery / 100) * bar_length)
                                bar = "█" * filled + "░" * (bar_length - filled)
                                log_print(f"  [{bar}] {battery}%")
                                
                                # Battery status
                                if battery >= 80:
                                    status = "🔋 Full"
                                elif battery >= 50:
                                    status = "🔋 Good"
                                elif battery >= 20:
                                    status = "🔋 Medium"
                                else:
                                    status = "🔋 Low"
                                
                                log_print(f"  Status: {status}")
                                
                                # Show raw data
                                hex_data = ' '.join([f'{b:02x}' for b in data_bytes[:min(8, len(data_bytes))]])
                                log_print(f"  Data: {hex_data} = [Report ID: {report_id}, Battery: {battery}%]")
                                log_print()
                                
                                last_battery = battery
                                last_report_id = report_id
                                last_update_time = current_time
                        else:
                            # Data received but not the expected pattern - log it
                            log_raw_data(data_bytes, f"UNKNOWN PATTERN (Report ID: 0x{report_id:02x}, Battery: {battery})")
                    else:
                        # Data received but too short - log it
                        log_raw_data(data_bytes, f"INSUFFICIENT DATA (len={len(data_bytes)})")
                
                except usb.core.USBError as e:
                    if e.errno == 110:  # ETIMEDOUT
                        # Timeout is normal when there is no data - log it periodically
                        timeout_count += 1
                        current_time = time.time()
                        # Log the timeout every 10 occurrences or every 30 seconds
                        if timeout_count % 10 == 0 or (current_time - last_timeout_log) > 30:
                            try:
                                with open(LOG_FILE, 'a', encoding='utf-8') as f:
                                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                    f.write(f"[{timestamp}] TIMEOUT: No data received (ETIMEDOUT) - Total: {timeout_count}\n")
                                    f.flush()
                                last_timeout_log = current_time
                            except:
                                pass
                        continue
                    elif e.errno == 5:  # Input/output error
                        log_print(f"\n⚠ USB I/O error: Device may be in use")
                        log_print(f"   Waiting 2 seconds...\n")
                        time.sleep(2)
                    else:
                        log_print(f"⚠ USB error: {e} (errno: {e.errno})")
                        # Log the detailed error
                        try:
                            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                f.write(f"[{timestamp}] USB ERROR: {e} (errno: {e.errno})\n")
                                f.flush()
                        except:
                            pass
                        time.sleep(1)
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            log_print("\n" + "=" * 60)
            log_print("📊 SUMMARY")
            log_print("=" * 60)
            if last_battery is not None:
                log_print(f"⚡ Last battery level: {last_battery}%")
                log_print(f"📦 Report ID: {last_report_id} (0x{last_report_id:02x})")
                log_print(f"📈 Total updates received: {update_count}")
                if last_update_time:
                    time_since_update = time.time() - last_update_time
                    log_print(f"⏱️  Last update {time_since_update:.1f} seconds ago")
            else:
                log_print("⚠ No battery data received")
            log_print("=" * 60)
        finally:
            # Release the interface
            try:
                usb.util.release_interface(device, interface)
            except:
                pass
        
    except ValueError as e:
        log_print(f"Error: {e}")
        sys.exit(1)
    except PermissionError:
        log_print("Error: Permission denied. Run as root or configure udev rules")
        sys.exit(1)
    except Exception as e:
        log_print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    read_battery()
