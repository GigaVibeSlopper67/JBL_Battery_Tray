#!/usr/bin/env python3
"""
Finds which /dev/hidrawX devices belong to the JBL Quantum910 (VID:PID 0ecb:2088).

Usage:
  python3 tools/find_jbl_hidraw.py
  sudo python3 tools/find_jbl_hidraw.py --bind-usbhid

Output:
  Lists all hidraw devices and highlights the ones matching the VID:PID.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


TARGET_VENDOR = 0x0ECB
TARGET_PRODUCTS = {0x2088: "JBL Quantum910", 0x2069: "JBL Quantum810"}


def parse_hid_id(uevent_text: str) -> tuple[int, int] | None:
    """
    HID_ID usually comes like this:
      HID_ID=0003:00000ECB:00002088
    """
    m = re.search(r"^HID_ID=([0-9A-Fa-f]{4}):([0-9A-Fa-f]{8}):([0-9A-Fa-f]{8})$", uevent_text, re.M)
    if not m:
        return None
    # bus = int(m.group(1), 16)  # not used
    vendor = int(m.group(2), 16)
    product = int(m.group(3), 16)
    return vendor, product


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return None


def _find_unbound_usb_hid_interfaces_for_target() -> list[str]:
    """
    Finds USB HID interfaces (bInterfaceClass=03) of the target device that
    have no driver bound (no symlink in .../driver). Returns names like:
      ['1-3:1.3', ...]
    """
    usb_root = Path("/sys/bus/usb/devices")
    out: list[str] = []

    # Find USB devices whose idVendor/idProduct match
    for dev in usb_root.iterdir():
        idv = dev / "idVendor"
        idp = dev / "idProduct"
        if not (idv.exists() and idp.exists()):
            continue
        try:
            v = int(idv.read_text().strip(), 16)
            p = int(idp.read_text().strip(), 16)
        except Exception:
            continue
        if v != TARGET_VENDOR or p not in TARGET_PRODUCTS:
            continue

        # Interfaces appear as "<devname>:1.<n>"
        parent = dev.parent
        for iface in sorted(parent.glob(dev.name + ":1.*")):
            cls = iface / "bInterfaceClass"
            if not cls.exists():
                continue
            try:
                icls = int(cls.read_text().strip(), 16)
            except Exception:
                continue
            if icls != 0x03:
                continue
            drv = iface / "driver"
            if not (drv.exists() and drv.is_symlink()):
                out.append(iface.name)

    return out


def _bind_to_usbhid(iface_names: list[str]) -> None:
    bind_path = Path("/sys/bus/usb/drivers/usbhid/bind")
    if not bind_path.exists():
        raise RuntimeError("Path /sys/bus/usb/drivers/usbhid/bind does not exist (usbhid driver unavailable).")

    # Root is required to write
    for name in iface_names:
        try:
            bind_path.write_text(name)
            print(f"✓ bind usbhid: {name}")
        except PermissionError as e:
            raise RuntimeError("Permission denied while trying to bind (run with sudo).") from e
        except OSError as e:
            raise RuntimeError(f"Failed to bind {name} to usbhid: {e}") from e


def main() -> int:
    parser = argparse.ArgumentParser(description="Find the JBL Quantum 910/810 hidraw device (0ecb:2088 / 0ecb:2069)")
    parser.add_argument(
        "--bind-usbhid",
        action="store_true",
        help="If the JBL HID interface has no driver, try binding it to usbhid (requires sudo).",
    )
    args = parser.parse_args()

    # Diagnosis: the typical case is the USB HID having no driver, so no hidraw node is created.
    unbound_hid_ifaces = _find_unbound_usb_hid_interfaces_for_target()
    if unbound_hid_ifaces:
        print("⚠ JBL USB HID interface(s) detected but WITHOUT a driver (that's why no /dev/hidrawX appears):")
        for n in unbound_hid_ifaces:
            print(f"  - {n}")
        if args.bind_usbhid:
            print("\nTrying to bind to the usbhid driver...")
            _bind_to_usbhid(unbound_hid_ifaces)
            print("\nRescanning hidraw...\n")
        else:
            print("\nTip: run with:")
            print("  sudo python3 tools/find_jbl_hidraw.py --bind-usbhid")
            print("or re-plug the headset dongle (disconnect/reconnect).")
            print()

    hidraw_root = Path("/sys/class/hidraw")
    if not hidraw_root.exists():
        print("Error: /sys/class/hidraw does not exist (hidraw unavailable on this system).")
        return 1

    hidraws = sorted([p for p in hidraw_root.glob("hidraw*") if p.is_dir()], key=lambda p: p.name)
    if not hidraws:
        print("No hidraw found in /sys/class/hidraw.")
        return 1

    matches: list[str] = []

    for entry in hidraws:
        devnode = f"/dev/{entry.name}"
        uevent_path = entry / "device" / "uevent"
        uevent = read_text(uevent_path) or ""

        vid_pid = parse_hid_id(uevent)
        hid_name = None
        mname = re.search(r"^HID_NAME=(.*)$", uevent, re.M)
        if mname:
            hid_name = mname.group(1).strip()

        if vid_pid is None:
            print(f"{devnode}: (no HID_ID) name={hid_name or '?'}")
            continue

        vendor, product = vid_pid
        ok = (vendor == TARGET_VENDOR and product in TARGET_PRODUCTS)
        tag = f"  <-- {TARGET_PRODUCTS[product]}" if ok else ""

        print(f"{devnode}: vid:pid={vendor:04x}:{product:04x} name={hid_name or '?'}{tag}")
        if ok:
            matches.append(devnode)

    if matches:
        print("\nSuggestion: start by testing these hidraw devices (in this order):")
        for d in matches:
            print(f"  - {d}")
    else:
        print("\nNo /dev/hidrawX matched vid:pid 0ecb:2088 / 0ecb:2069.")
        print("If the headset is connected, check with: lsusb | grep -i 0ecb")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

