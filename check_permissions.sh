#!/bin/bash
# Script to verify permissions and configuration of the JBL Quantum 910/810

echo "=== JBL Quantum 910/810 Permission Check ==="
echo

# Check if the device is connected (when lsusb is available)
echo "1. Checking if the device is connected..."
if command -v lsusb >/dev/null 2>&1; then
    if lsusb | grep -Eq "0ecb:(2088|2069)"; then
        echo "   ✓ Device found"
        lsusb | grep -E "0ecb:(2088|2069)"
    else
        echo "   ✗ Device not found"
        echo "   Connect the JBL Quantum 910/810 headset via USB"
        exit 1
    fi
else
    echo "   (lsusb not installed - checking /sys/class/hidraw instead)"
fi
echo

# Find the headset's hidraw node and check user access
echo "2. Checking hidraw device and user access..."
found=0
for hid in /sys/class/hidraw/hidraw*; do
    [ -e "$hid/device/uevent" ] || continue
    if grep -qiE "HID_ID=0003:0*ECB:0*(2069|2088)" "$hid/device/uevent" 2>/dev/null; then
        found=1
        dev="/dev/$(basename "$hid")"
        echo "   ✓ Found JBL headset on $dev"
        perms=$(stat -c "%a" "$dev" 2>/dev/null)
        echo "   Permissions: $perms"
        if [ -r "$dev" ] && [ -w "$dev" ]; then
            echo "   ✓ Read/write access OK for user $USER"
        else
            echo "   ⚠ No read/write access for user $USER"
            echo "   Fix: install the udev rules and replug the dongle:"
            echo "     sudo ./setup_udev_rules.sh"
            echo "     (then unplug and replug the USB dongle)"
        fi
    fi
done
if [ "$found" -eq 0 ]; then
    echo "   ✗ JBL headset not found in /sys/class/hidraw"
    echo "   Connect the headset (USB dongle) and try again"
fi
echo

# Check udev rules
echo "3. Checking udev rules..."
rule_file="/etc/udev/rules.d/99-jbl-quantum910.rules"
if [ -f "$rule_file" ]; then
    echo "   ✓ udev rule file found:"
    cat "$rule_file"
else
    echo "   ⚠ udev rule file not found ($rule_file)"
    echo "   Fix: run  sudo ./setup_udev_rules.sh  and replug the dongle"
    echo "   The rules use MODE 0666 + uaccess - no plugdev group is needed"
fi
echo

# Check Python libraries
echo "4. Checking Python libraries..."
if python3 -c "import usb.core" 2>/dev/null; then
    echo "   ✓ pyusb installed"
else
    echo "   ⚠ pyusb not installed (only needed by the pyusb-based scripts)"
    echo "   Run: pip3 install pyusb --user"
fi

if python3 -c "import hid" 2>/dev/null; then
    echo "   ✓ hidapi installed"
else
    echo "   ⚠ hidapi not installed"
    echo "   Run: pip3 install hidapi --user"
fi

echo
echo "=== End of Check ==="
