#!/bin/bash
# Script to set up udev rules for JBL Quantum 910/810 access without root
# (uses uaccess + 0666 - no plugdev group is needed)

echo "=== UDEV Rules Setup for JBL Quantum 910/810 ==="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "This script must be run as root"
    echo "Run: sudo $0"
    exit 1
fi

# Create the udev rule
UDEV_RULE="/etc/udev/rules.d/99-jbl-quantum910.rules"

echo "Creating udev rule at $UDEV_RULE..."

cat > "$UDEV_RULE" << 'EOF'
# JBL Quantum 910 Wireless (0ecb:2088) - grants the logged-in desktop user access
KERNEL=="hidraw*", ATTRS{idVendor}=="0ecb", ATTRS{idProduct}=="2088", MODE="0666", TAG+="uaccess"

# JBL Quantum 810 Wireless (0ecb:2069) - grants the logged-in desktop user access
KERNEL=="hidraw*", ATTRS{idVendor}=="0ecb", ATTRS{idProduct}=="2069", MODE="0666", TAG+="uaccess"

# Direct USB device access (only needed by the pyusb-based scripts)
SUBSYSTEM=="usb", ATTR{idVendor}=="0ecb", ATTR{idProduct}=="2088", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="0ecb", ATTR{idProduct}=="2069", MODE="0666", TAG+="uaccess"
EOF

echo "✓ Rule created"
echo
echo "Rule content:"
cat "$UDEV_RULE"
echo

# Reload udev rules
echo "Reloading udev rules..."
udevadm control --reload-rules
udevadm trigger

echo
echo "✓ Rules reloaded"
echo
echo "Next steps:"
echo "1. Disconnect and reconnect the headset USB dongle"
echo "2. Then check: ./check_permissions.sh"
echo
echo "After that, you can run the scripts without sudo! (No plugdev group is needed)"
