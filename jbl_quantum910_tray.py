#!/usr/bin/env python3
"""
JBL Quantum 910/810 - Tray Battery Monitor (Linux)

- Shows headset battery percentage in the system tray (AppIndicator).
- Reads battery primarily via hidraw (least intrusive).
- Falls back to pyusb if hidraw is unavailable.
- Supports both dongles: JBL Quantum 910 (0ecb:2088) and JBL Quantum 810
  (0ecb:2069). On the 810 the battery can also be polled directly via the
  HID feature report 0x49, so no traffic from the headset is needed.

Battery format confirmed in this repo (same for both models):
  [Report ID, Battery%] => 0x08 <0..100>
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


VENDOR_ID_HEX = "0ecb"
VENDOR_ID = int(VENDOR_ID_HEX, 16)
# Supported JBL Quantum dongles (USB product ID -> model name). Both push
# battery updates as input report 0x08 ([0x08, percentage 0-100]). The
# Quantum 810 (0x2069) can additionally be polled: GET_REPORT(0x49) returns
# the direct battery percentage.
KNOWN_PRODUCTS = {
    0x2088: "JBL Quantum910 Wireless",
    0x2069: "JBL Quantum810 Wireless",
}
KNOWN_PRODUCT_IDS = tuple(sorted(KNOWN_PRODUCTS))
KNOWN_PRODUCT_IDS_HEX = tuple(f"{pid:04x}" for pid in KNOWN_PRODUCT_IDS)
PRODUCT_ID = 0x2088  # Quantum 910 (kept for backwards compatibility)
# HID feature report holding the direct battery percentage (Quantum 810).
BATTERY_FEATURE_REPORT_ID = 0x49
# Directory for the generated numeric badge icons (percentage drawn into the tray icon).
ICON_DIR = os.path.expanduser("~/.cache/jbl-quantum-tray/icons")


def _import_appindicator():
    """
    AppIndicator naming varies by distro:
    - Ubuntu/Debian often provide AppIndicator3
    - Some distros provide AyatanaAppIndicator3
    """
    try:
        import gi  # type: ignore

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, GLib  # type: ignore

        try:
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3 as AppIndicator  # type: ignore
        except Exception:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AppIndicator  # type: ignore

        return Gtk, GLib, AppIndicator
    except Exception as e:
        print("Error: tray dependencies not found (PyGObject/AppIndicator).", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        print("\nPython in use:", file=sys.stderr)
        print(f"  Executable: {sys.executable}", file=sys.stderr)
        print(f"  Version: {sys.version.split()[0]}", file=sys.stderr)
        print("\nInstall (Debian/Ubuntu):", file=sys.stderr)
        print("  sudo apt install -y python3-gi gir1.2-ayatanaappindicator3-0.1", file=sys.stderr)
        print("  # or: gir1.2-appindicator3-0.1", file=sys.stderr)
        print("  Fedora:        sudo dnf install -y python3-gobject gtk3 libayatana-appindicator-gtk3", file=sys.stderr)
        print("  RHEL/Rocky/Alma (EPEL): sudo dnf install -y epel-release && sudo dnf install -y python3-gobject gtk3 libayatana-appindicator-gtk3", file=sys.stderr)
        print("\nTip:", file=sys.stderr)
        print("  If you use pyenv/conda/venv, run with the system Python:", file=sys.stderr)
        print("    /usr/bin/python3 ./jbl_quantum910_tray.py", file=sys.stderr)
        sys.exit(1)


def _parse_hid_id_hex(text: str) -> Optional[tuple[str, str]]:
    """Parse 'HID_ID=0003:00000ECB:00002069' into ('0ecb', '2069')."""
    for line in text.splitlines():
        if line.startswith("HID_ID="):
            parts = line.split("=", 1)[1].split(":")
            if len(parts) == 3:
                try:
                    return f"{int(parts[1], 16):04x}", f"{int(parts[2], 16):04x}"
                except ValueError:
                    return None
    return None


def find_hidraw_device() -> Optional[str]:
    """Find the first hidraw device matching a supported JBL Quantum dongle.

    Scans /sys/class/hidraw/*/device/uevent and matches HID_ID
    (e.g. 'HID_ID=0003:00000ECB:00002069' for the Quantum 810).
    """
    base = "/sys/class/hidraw"
    if not os.path.isdir(base):
        return None
    for entry in sorted(os.listdir(base)):
        uevent_path = os.path.join(base, entry, "device", "uevent")
        try:
            with open(uevent_path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        ids = _parse_hid_id_hex(text)
        if ids is None:
            continue
        vendor_hex, product_hex = ids
        if vendor_hex == VENDOR_ID_HEX and product_hex in KNOWN_PRODUCT_IDS_HEX:
            return os.path.join("/dev", entry)
    return None


def detect_model_name() -> Optional[str]:
    """HID name of a supported JBL Quantum device, e.g.
    'Harman International Inc JBL Quantum810 Wireless'."""
    base = "/sys/class/hidraw"
    if not os.path.isdir(base):
        return None
    for entry in sorted(os.listdir(base)):
        uevent_path = os.path.join(base, entry, "device", "uevent")
        try:
            with open(uevent_path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        ids = _parse_hid_id_hex(text)
        if ids is None:
            continue
        vendor_hex, product_hex = ids
        if vendor_hex != VENDOR_ID_HEX or product_hex not in KNOWN_PRODUCT_IDS_HEX:
            continue
        for line in text.splitlines():
            if line.startswith("HID_NAME="):
                name = line.split("=", 1)[1].strip()
                if name:
                    return name
    return None


def parse_battery_from_packet(packet: bytes) -> Optional[int]:
    """Parse battery percent from a single packet (strict known pattern)."""
    if len(packet) >= 2 and packet[0] == 0x08:
        b = packet[1]
        if 0 <= b <= 100:
            return int(b)
    return None


def parse_mute_from_packet(packet: bytes) -> Optional[tuple[bool, bool]]:
    """
    Parse mute status from a packet.
    - 0x2f 0x02 = toggle mute (button pressed, Quantum 910) -> returns (True, True) = toggle
    - 0x2f 0x00 = unmuted state -> returns (False, False) = unmuted
    - 0x06 0x00/0x01 = mic off/on events (Quantum 810; confirmed in the
      HeadsetControl #357 USB captures) -> state, not a toggle.
    Returns (is_toggle, is_muted) or None if not a mute packet.
    """
    if len(packet) >= 2 and packet[0] == 0x2f:
        if packet[1] == 0x02:
            return (True, True)  # Toggle - need to flip the state
        elif packet[1] == 0x00:
            return (False, False)  # Unmuted state
    if len(packet) >= 2 and packet[0] == 0x06:
        # Quantum 810 mic events: 0 = mic off (muted), 1 = mic on.
        if packet[1] in (0x00, 0x01):
            return (False, packet[1] == 0x00)
    return None


def parse_status_from_packet(packet: bytes) -> Optional[StatusSample]:
    """
    Parse extra vendor state (Quantum 810 event map, confirmed via the
    HeadsetControl #357 captures):
      0x02 <v>  ANC: 0=off, 1=on, 2=talk-through
      0x07 <v>  Lights: 0=off, 1=on
      0x10 <v>  Game/chat mix: 0x00=chat ... 0x10=game
      0x03/0x09 Power-on markers (followed by a full state burst)
    """
    if len(packet) < 2:
        return None
    rid, b1 = packet[0], packet[1]
    raw = " ".join(f"{b:02x}" for b in packet[:8])
    now = time.time()
    if rid == 0x02 and b1 in (0, 1, 2):
        return StatusSample(anc=int(b1), source="hidraw", raw_hex=raw, ts=now)
    if rid == 0x07 and b1 in (0, 1):
        return StatusSample(lights=bool(b1), source="hidraw", raw_hex=raw, ts=now)
    if rid == 0x10 and 0 <= b1 <= 16:
        return StatusSample(mix=int(b1), source="hidraw", raw_hex=raw, ts=now)
    if rid in (0x03, 0x09):
        return StatusSample(power_marker=True, source="hidraw", raw_hex=raw, ts=now)
    return None


def _log(msg: str) -> None:
    # Journald/systemd friendly: timestamp + flush
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# --- Numeric tray icon ------------------------------------------------------
# Some desktops (e.g. GNOME with the AppIndicator extension) hide the
# indicator label and tooltips, so the battery percentage is drawn directly
# into the tray icon: a Breeze-style battery outline with a charge bar and
# the percentage inside, on a transparent background.

ICON_DIR = os.path.expanduser("~/.cache/jbl-quantum-tray/icons")

_DIGIT_FONT = {
    "0": "111101101101111",
    "1": "010110010010111",
    "2": "111001111100111",
    "3": "111001111001111",
    "4": "101101111001001",
    "5": "111100111001111",
    "6": "111100111101111",
    "7": "111001010010010",
    "8": "111101111101111",
    "9": "111101111001111",
}


def _badge_pixels(
    percent: int, size: int = 64, supersample: int = 3, draw_digits: bool = True
) -> bytes:
    """Build RGBA pixels for a battery badge icon showing the percentage.

    Transparent background with a Breeze-style battery outline, a colored
    charge bar and the percentage centered inside the body, so the icon
    blends in with the monochrome system tray icons. Rendered large
    (64x64) and anti-aliased; the panel scales it down crisply.
    """
    big = size * supersample
    buf = bytearray(big * big * 4)

    def in_rrect(x, y, x0, y0, x1, y1, r):
        if x < x0 or x > x1 or y < y0 or y > y1:
            return False
        cx = min(max(x, x0 + r), x1 - r)
        cy = min(max(y, y0 + r), y1 - r)
        dx = x - cx
        dy = y - cy
        return dx * dx + dy * dy <= r * r

    if percent >= 60:
        fill_rgba = (46, 204, 113, 255)   # green
    elif percent >= 20:
        fill_rgba = (241, 196, 15, 255)   # amber
    else:
        fill_rgba = (231, 76, 60, 255)    # red
    stroke_rgba = (208, 213, 220, 240)    # light gray outline (Breeze-like)
    digit_rgba = (244, 247, 250, 255)     # near-white digits

    # Geometry in 64x64 final-pixel design coordinates.
    body = (3, 15, 54, 48)     # battery outline rounded rect
    rad = 5.0                  # corner radius
    stroke = 3                 # outline thickness
    nub = (54, 27, 60, 36)     # battery terminal on the right
    bar = (7, 39, 50, 44)      # charge bar inside the body

    bx0, by0 = body[0] * supersample, body[1] * supersample
    bx1, by1 = body[2] * supersample, body[3] * supersample
    ix0, iy0 = bx0 + stroke * supersample, by0 + stroke * supersample
    ix1, iy1 = bx1 - stroke * supersample, by1 - stroke * supersample
    inner_r = max(1.0, rad - stroke) * supersample
    nx0, ny0 = nub[0] * supersample, nub[1] * supersample
    nx1, ny1 = nub[2] * supersample, nub[3] * supersample
    fx0, fy0 = bar[0] * supersample, bar[1] * supersample
    fx1, fy1 = bar[2] * supersample, bar[3] * supersample

    bar_w = round((fx1 - fx0) * max(0, min(100, percent)) / 100)
    bar_w = max(supersample, bar_w) if percent > 0 else 0

    # Digits (pixel font), scaled up, centered inside the battery body.
    text = str(percent)
    dscale = 3  # 3x5 font at 3x; fits even for "100" inside the body
    blk = dscale * supersample           # one font mask cell, in big px
    cell = 3 * blk
    gap = blk
    row_h = 5 * blk
    total_w = len(text) * cell + (len(text) - 1) * gap
    digit_x0 = (bx0 + bx1) // 2 - total_w // 2
    band_top = by0 + stroke * supersample
    band_bot = fy0
    digit_y0 = (band_top + band_bot) // 2 - row_h // 2

    for y in range(big):
        fy = y + 0.5
        row = y * big
        for x in range(big):
            fx = x + 0.5
            rgba = None
            if in_rrect(fx, fy, nx0, ny0, nx1, ny1, 1.5 * supersample):
                rgba = stroke_rgba
            elif in_rrect(fx, fy, bx0, by0, bx1, by1, rad * supersample):
                if not in_rrect(fx, fy, ix0, iy0, ix1, iy1, inner_r):
                    rgba = stroke_rgba
                elif bar_w and fx0 <= fx < fx0 + bar_w and fy0 <= fy <= fy1:
                    rgba = fill_rgba
            if rgba is not None:
                i = (row + x) * 4
                buf[i : i + 4] = bytes(rgba)

    def put(x: int, y: int, rgba) -> None:
        if 0 <= x < big and 0 <= y < big:
            i = (y * big + x) * 4
            buf[i : i + 4] = bytes(rgba)

    for idx, char in enumerate(text if draw_digits else ""):
        rows = _DIGIT_FONT.get(char)
        if not rows:
            continue
        x_off = digit_x0 + idx * (cell + gap)
        for r in range(5):
            for c in range(3):
                if rows[r * 3 + c] == "1":
                    for yy in range(blk):
                        py = digit_y0 + r * blk + yy
                        for xx in range(blk):
                            put(x_off + c * blk + xx, py, digit_rgba)

    # Box-downscale to the final size.
    out = bytearray(size * size * 4)
    n = supersample * supersample
    for y in range(size):
        for x in range(size):
            r = g = b = a = 0
            for dy in range(supersample):
                for dx in range(supersample):
                    i = ((y * supersample + dy) * big + (x * supersample + dx)) * 4
                    r += buf[i]
                    g += buf[i + 1]
                    b += buf[i + 2]
                    a += buf[i + 3]
            j = (y * size + x) * 4
            out[j : j + 4] = bytes((r // n, g // n, b // n, a // n))
    return bytes(out)


_BADGE_FONT_CANDIDATES = (
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/ubuntu/Ubuntu-B.ttf",
)


def _load_badge_font(sz: int):
    """Load a bold TrueType font for the badge digits (None if unavailable)."""
    from PIL import ImageFont  # type: ignore

    for cand in _BADGE_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(cand, sz)
        except Exception:
            continue
    try:
        # Pillow >= 10.1 ships a scalable default font
        return ImageFont.load_default(size=sz)
    except TypeError:
        return None


def _draw_badge_digits(img, percent: int) -> None:
    """Draw the percentage into the badge with an anti-aliased font."""
    from PIL import ImageDraw  # type: ignore

    text = str(percent)
    draw = ImageDraw.Draw(img)
    sz = 24
    while sz > 12:
        font = _load_badge_font(sz)
        if font is None:
            return  # keep the blocky pixel-font digits from _badge_pixels
        if draw.textlength(text, font=font) <= 40:
            break
        sz -= 2
    # Centered inside the battery body, above the charge bar.
    try:
        draw.text((29, 28), text, font=font, fill=(244, 247, 250, 255), anchor="mm")
    except TypeError:  # Pillow < 8 without anchor support
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((29 - w // 2, 28 - h // 2), text, font=font, fill=(244, 247, 250, 255))


def _write_badge_png(percent: int, path: str) -> bool:
    """Write the numeric badge icon as a PNG file. Returns True on success."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    size = 64
    try:
        from PIL import Image  # type: ignore

        # Battery outline + charge bar; digits drawn with a real font below.
        rgba = _badge_pixels(percent, size, draw_digits=False)
        img = Image.frombytes("RGBA", (size, size), rgba)
        _draw_badge_digits(img, percent)
        img.save(path)
        return True
    except ImportError:
        pass

    # Fallback: blocky pixel-font digits + minimal PNG writer (zlib + struct).
    rgba = _badge_pixels(percent, size)
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    raw = b""
    for y in range(size):
        raw += b"\x00" + rgba[y * size * 4 : (y + 1) * size * 4]
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))
    return True


@dataclass
class BatterySample:
    percent: int
    source: str
    raw_hex: str
    ts: float


@dataclass
class MuteSample:
    is_toggle: bool  # True if it's a toggle (0x02), False if it's a state (0x00)
    muted: bool  # True if muted, False if unmuted
    source: str
    raw_hex: str
    ts: float


@dataclass
class StatusSample:
    """Extra headset state from vendor event reports (Quantum 810 map)."""

    anc: Optional[int] = None  # 0=off, 1=on, 2=talk-through
    mic_muted: Optional[bool] = None
    mix: Optional[int] = None  # 0..16, 0=full chat, 0x10=full game
    lights: Optional[bool] = None
    power_marker: bool = False  # 0x03/0x09 power-on markers
    source: str = ""
    raw_hex: str = ""
    ts: float = 0.0

    ANC_NAMES = {0: "off", 1: "on", 2: "talk-through"}

    def anc_label(self) -> Optional[str]:
        if self.anc is None:
            return None
        return self.ANC_NAMES.get(self.anc, f"0x{self.anc:02x}")

    def mix_label(self) -> Optional[str]:
        if self.mix is None:
            return None
        m = max(0, min(16, self.mix))
        if m <= 2:
            return f"chat ({m}/16)"
        if m >= 14:
            return f"game ({m}/16)"
        return f"balanced ({m}/16)"


class HidrawBatteryReader:
    # HIDIOCGFEATURE(len) = _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x07, len);
    # used to poll the Quantum 810 battery via feature report 0x49.
    _HIDIOCGFEATURE = (3 << 30) | (0x48 << 8) | 0x07
    # HIDIOCSFEATURE(len) = _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x06, len);
    # used to send commands (ANC 0x46, lights 0x4b, sidetone 0x5d).
    _HIDIOCSFEATURE = (3 << 30) | (0x48 << 8) | 0x06

    def __init__(self, path: str):
        self.path = path
        self._fd: Optional[int] = None
        self._can_feature_read = False  # set when the node is opened read/write
        self._feature_poll_ok: Optional[bool] = None  # None = not tried yet

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
        self._fd = None

    def _ensure_open(self) -> None:
        if self._fd is not None:
            return
        # Read/write access is required for the GET_FEATURE ioctl used to poll
        # the battery on the Quantum 810; fall back to read-only (then polling
        # stays disabled).
        try:
            self._fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
            self._can_feature_read = True
        except PermissionError:
            self._fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
            self._can_feature_read = False
            _log(f"No write access to {self.path}; battery polling disabled")
        except FileNotFoundError:
            # Node vanished (dongle replugged / kernel driver detached):
            # drop the stale path so the app re-scans for a new node.
            self.path = None
            raise

    def poll(self) -> Optional[BatterySample]:
        """Poll for battery updates. Also checks for mute in the same read."""
        try:
            self._ensure_open()
        except Exception:
            self.close()
            return None

        last_battery: Optional[BatterySample] = None
        # Drain available packets (non-blocking) to get the latest updates.
        for _ in range(32):
            try:
                data = os.read(self._fd, 64)  # type: ignore[arg-type]
                if not data:
                    break
                # Check for battery
                percent = parse_battery_from_packet(data)
                if percent is not None:
                    last_battery = BatterySample(
                        percent=percent,
                        source=f"hidraw:{self.path}",
                        raw_hex=" ".join(f"{b:02x}" for b in data[:8]),
                        ts=time.time(),
                    )
                # Also check for mute (but don't return it here, handled separately)
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    break
                # Device went away / permission error / etc. Reopen next time.
                self.close()
                return None
            except Exception:
                self.close()
                return None

        # Quantum 810: the battery can also be polled directly with feature
        # report 0x49, so fresh data arrives even when the headset is quiet.
        if last_battery is None:
            percent = self._poll_feature_battery()
            if percent is not None:
                last_battery = BatterySample(
                    percent=percent,
                    source=f"hidraw-feat:{self.path}",
                    raw_hex="feature 0x49",
                    ts=time.time(),
                )

        return last_battery

    def _poll_feature_battery(self) -> Optional[int]:
        """GET_REPORT(Feature 0x49): direct battery % (JBL Quantum 810).

        The node must echo the requested report ID. Some reports on this
        device do not answer GET_REPORT and the kernel then leaves stale data
        in the buffer, so a mismatching echo disables polling.
        """
        if not (self._can_feature_read and self._fd is not None):
            return None
        if self._feature_poll_ok is False:
            return None
        buf = bytearray(2)
        buf[0] = BATTERY_FEATURE_REPORT_ID
        request = self._HIDIOCGFEATURE | (len(buf) << 16)
        try:
            fcntl.ioctl(self._fd, request, buf, True)
        except OSError as e:
            if self._feature_poll_ok is not False:
                _log(f"Feature 0x49 poll failed on {self.path} ({e}); direct battery polling disabled")
            self._feature_poll_ok = False
            return None
        if buf[0] != BATTERY_FEATURE_REPORT_ID:
            if self._feature_poll_ok is not False:
                _log(f"Feature 0x49 echo mismatch on {self.path} (got 0x{buf[0]:02x}); direct battery polling disabled")
            self._feature_poll_ok = False
            return None
        if self._feature_poll_ok is not True:
            _log("Direct battery polling active (feature report 0x49)")
        self._feature_poll_ok = True
        percent = buf[1]
        if 0 <= percent <= 100:
            return int(percent)
        return None

    def poll_all(self) -> tuple[Optional[BatterySample], Optional[MuteSample], Optional[StatusSample]]:
        """Poll for battery, mute and extra status in a single read pass."""
        try:
            self._ensure_open()
        except Exception:
            self.close()
            return None, None, None

        last_battery: Optional[BatterySample] = None
        last_mute: Optional[MuteSample] = None
        last_status: Optional[StatusSample] = None
        # Drain available packets (non-blocking) to get the latest updates.
        for _ in range(32):
            try:
                data = os.read(self._fd, 64)  # type: ignore[arg-type]
                if not data:
                    break
                # Check for battery
                percent = parse_battery_from_packet(data)
                if percent is not None:
                    last_battery = BatterySample(
                        percent=percent,
                        source=f"hidraw:{self.path}",
                        raw_hex=" ".join(f"{b:02x}" for b in data[:8]),
                        ts=time.time(),
                    )
                # Check for mute
                mute_info = parse_mute_from_packet(data)
                if mute_info is not None:
                    is_toggle, is_muted = mute_info
                    last_mute = MuteSample(
                        is_toggle=is_toggle,
                        muted=is_muted,
                        source=f"hidraw:{self.path}",
                        raw_hex=" ".join(f"{b:02x}" for b in data[:8]),
                        ts=time.time(),
                    )
                # Extra state: ANC / lights / game-chat mix / power markers
                status_info = parse_status_from_packet(data)
                if status_info is not None:
                    last_status = status_info
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    break
                self.close()
                return None, None, None
            except Exception:
                self.close()
                return None, None, None

        return last_battery, last_mute, last_status

    # -- controls / extras -------------------------------------------------------

    def send_feature(self, rid: int, value: int) -> bool:
        """SET_REPORT(Feature, [rid, value]). CHANGES DEVICE STATE.

        Known commands (Quantum 810, confirmed in HeadsetControl #357
        captures): 0x46 ANC (0=off/1=on/2=talk-through), 0x4b lights,
        0x5d sidetone (0=off/1=low/2=mid/3=high).
        """
        if self._fd is None:
            try:
                self._ensure_open()
            except Exception:
                return False
        if not self._can_feature_read or self._fd is None:
            _log("hidraw not opened read/write; cannot send feature report")
            return False
        buf = bytes([rid, value])
        try:
            fcntl.ioctl(self._fd, self._HIDIOCSFEATURE | (len(buf) << 16), buf, True)
            return True
        except OSError as e:
            _log(f"SET feature 0x{rid:02x} failed on {self.path}: {e}")
            return False

    def read_feature(self, rid: int, length: int = 16) -> Optional[bytes]:
        """GET_REPORT(Feature, rid) - read-only."""
        if self._fd is None:
            try:
                self._ensure_open()
            except Exception:
                return None
        if self._fd is None or not self._can_feature_read:
            return None
        buf = bytearray(length)
        buf[0] = rid
        try:
            n = fcntl.ioctl(self._fd, self._HIDIOCGFEATURE | (length << 16), buf, True)
        except OSError:
            return None
        if n and n > 0:
            return bytes(buf[:n])
        return None

    def read_serial(self) -> Optional[str]:
        """ASCII part/serial string from feature 0x61 (Quantum 810)."""
        feat = self.read_feature(0x61, 32)
        if feat and len(feat) > 2:
            text = feat[1:].rstrip(b"\x00").decode("ascii", errors="replace").strip()
            if text and any(c.isalnum() for c in text):
                return text
        return None

    def read_state(self) -> Optional[StatusSample]:
        """Read the current headset state via feature reports.

        All mappings verified live (GET report id = SET id - 1):
          0x45 -> ANC      [0x45, 0=off/1=on/2=talk-through] (mirrors SET 0x46)
          0x4a -> lights   [0x4a, 0=off/1=on]                (mirrors SET 0x4b)
          0x62 -> mix      [0x62, 0..16]                     (mirrors event 0x10)
          0x67 -> mic      [0x67, 1=on, 0=muted]             (mirrors event 0x06)
        Returns a StatusSample; individual fields stay None when a read
        fails or the echoed report id does not match.
        """
        if self._fd is None:
            try:
                self._ensure_open()
            except Exception:
                return None
        if self._fd is None or not self._can_feature_read:
            return None

        sample = StatusSample(
            source=f"hidraw-feat:{self.path}",
            raw_hex="features 0x45/0x67/0x4a/0x62",
            ts=time.time(),
        )
        feat = self.read_feature(0x45, 2)
        if feat and feat[0] == 0x45 and feat[1] in (0, 1, 2):
            sample.anc = int(feat[1])
        feat = self.read_feature(0x67, 2)
        if feat and feat[0] == 0x67 and feat[1] in (0, 1):
            # 0x67 mirrors event 0x06 exactly: 1 = mic on, 0 = mic off (muted).
            sample.mic_muted = (feat[1] == 0)
        feat = self.read_feature(0x4A, 2)
        if feat and feat[0] == 0x4A and feat[1] in (0, 1):
            sample.lights = (feat[1] == 1)
        feat = self.read_feature(0x62, 2)
        if feat and feat[0] == 0x62 and 0 <= feat[1] <= 16:
            sample.mix = int(feat[1])
        return sample


class PyUsbBatteryReader:
    """
    PyUSB reader intentionally mirrors the known-good logic from `jbl_battery_simple.py`:
    - find device by VID/PID
    - (best-effort) detach kernel driver on interface 3
    - claim interface 3
    - read endpoint device[0][(3,0)][0] with timeout
    """

    def __init__(self, timeout_ms: int = 1000):
        self.timeout_ms = timeout_ms
        self._usb = None
        self._device = None
        self._endpoint = None
        self._claimed = False
        self._interface_num: int = 3  # 3 on the Quantum 910, 5 on the 810
        self.last_error: Optional[str] = None
        self._claim_logged = False

    def close(self) -> None:
        if self._usb is not None and self._device is not None and self._claimed:
            try:
                self._usb.util.release_interface(self._device, self._interface_num)
            except Exception:
                pass
        self._usb = None
        self._device = None
        self._endpoint = None
        self._claimed = False
        self.last_error = None

    def _ensure_ready(self) -> bool:
        if self._device is not None and self._endpoint is not None:
            return True
        try:
            import usb.core  # type: ignore
            import usb.util  # type: ignore

            self._usb = type("USB", (), {"core": usb.core, "util": usb.util})
            # Quantum 910 (0x2088) and Quantum 810 (0x2069) dongles.
            dev = None
            for pid in KNOWN_PRODUCT_IDS:
                dev = usb.core.find(idVendor=VENDOR_ID, idProduct=pid)
                if dev is not None:
                    break
            if dev is None:
                self.last_error = "Device not found"
                return False
            # Vendor HID interface: 3 on the Quantum 910, 5 on the Quantum 810.
            self._interface_num = 3 if dev.idProduct == 0x2088 else 5

            try:
                # Mirror `jbl_battery_simple.py`: best-effort detach if active.
                if dev.is_kernel_driver_active(self._interface_num):
                    dev.detach_kernel_driver(self._interface_num)
            except Exception:
                pass

            # Mirror `jbl_battery_simple.py`: claim the vendor HID interface.
            try:
                usb.util.claim_interface(dev, self._interface_num)
            except Exception as e:
                self.last_error = f"Error claiming interface {self._interface_num}: {e}"
                self._claimed = False
                return False

            self._claimed = True

            endpoint = dev[0][(self._interface_num, 0)][0]
            self._device = dev
            self._endpoint = endpoint
            self.last_error = None
            if not self._claim_logged:
                self._claim_logged = True
                _log(
                    f"pyusb: claimed interface {self._interface_num}; battery updates when the headset sends traffic"
                    " (tip: replug the dongle once so its hidraw node returns and direct polling activates)"
                )
            return True
        except Exception:
            self.last_error = "Failed to initialize pyusb"
            self.close()
            return False

    def poll(self) -> Optional[BatterySample]:
        if not self._ensure_ready():
            return None

        try:
            dev = self._device
            ep = self._endpoint
            if dev is None or ep is None:
                return None
            data = dev.read(ep.bEndpointAddress, ep.wMaxPacketSize, self.timeout_ms)
            data_bytes = bytes(data)
            percent = parse_battery_from_packet(data_bytes)
            if percent is None:
                return None
            return BatterySample(
                percent=percent,
                source="pyusb",
                raw_hex=" ".join(f"{b:02x}" for b in data_bytes[:8]),
                ts=time.time(),
            )
        except Exception as e:
            # Treat timeouts like "no new data yet", and reset on other errors.
            try:
                if hasattr(e, "errno") and e.errno == 110:  # ETIMEDOUT in PyUSB
                    return None
            except Exception:
                pass
            # Re-init next time.
            self.last_error = str(e)
            self.close()
            return None

    def poll_all(self) -> tuple[Optional[BatterySample], Optional[MuteSample]]:
        """Poll for both battery and mute updates, draining multiple packets like hidraw."""
        try:
            if not self._ensure_ready():
                return None, None

            last_battery: Optional[BatterySample] = None
            last_mute: Optional[MuteSample] = None
            
            # Drain multiple packets (non-blocking) to get the latest updates
            # Similar to hidraw implementation, but with reasonable timeout
            # Read a few packets with short timeout, then one with longer timeout
            for i in range(5):
                try:
                    dev = self._device
                    ep = self._endpoint
                    if dev is None or ep is None:
                        break
                    # Use shorter timeout for first few reads (non-blocking)
                    timeout_ms = 50 if i < 4 else self.timeout_ms
                    data = dev.read(ep.bEndpointAddress, ep.wMaxPacketSize, timeout_ms)
                    data_bytes = bytes(data)
                    
                    # Check for battery
                    percent = parse_battery_from_packet(data_bytes)
                    if percent is not None:
                        last_battery = BatterySample(
                            percent=percent,
                            source="pyusb",
                            raw_hex=" ".join(f"{b:02x}" for b in data_bytes[:8]),
                            ts=time.time(),
                        )
                    
                    # Check for mute
                    mute_info = parse_mute_from_packet(data_bytes)
                    if mute_info is not None:
                        is_toggle, is_muted = mute_info
                        last_mute = MuteSample(
                            is_toggle=is_toggle,
                            muted=is_muted,
                            source="pyusb",
                            raw_hex=" ".join(f"{b:02x}" for b in data_bytes[:8]),
                            ts=time.time(),
                        )
                except Exception as e:
                    # Timeout is expected when no more data
                    try:
                        if hasattr(e, "errno") and e.errno == 110:  # ETIMEDOUT
                            # On timeout, return what we have so far
                            if last_battery is not None or last_mute is not None:
                                return last_battery, last_mute
                            # If no data yet and it's the last read, break
                            if i >= 4:
                                break
                            # Otherwise continue to next read
                            continue
                    except Exception:
                        pass
                    # Other errors - stop reading and return what we have
                    break
            
            return last_battery, last_mute
        except Exception as e:
            try:
                if hasattr(e, "errno") and e.errno == 110:  # ETIMEDOUT
                    return None, None
            except Exception:
                pass
            self.last_error = str(e)
            self.close()
            return None, None


class BatteryTrayApp:
    def __init__(self, refresh_seconds: float, prefer_pyusb: bool, pyusb_detach: bool, numeric_icon: bool = False, enable_controls: bool = False):
        self.refresh_seconds = max(0.2, refresh_seconds)
        self.prefer_pyusb = prefer_pyusb

        self.Gtk, self.GLib, self.AppIndicator = _import_appindicator()

        self.last_sample: Optional[BatterySample] = None
        self.last_mute_sample: Optional[MuteSample] = None
        self.last_status_sample: Optional[StatusSample] = None
        self._last_label: Optional[str] = None
        self._last_logged_error: Optional[str] = None
        self._last_logged_percent: Optional[int] = None
        self._is_muted: bool = False

        # Extra headset state (Quantum 810 event map):
        self.enable_controls: bool = enable_controls
        self._anc: Optional[int] = None        # 0=off, 1=on, 2=talk-through
        self._mix: Optional[int] = None        # 0..16
        self._lights_on: Optional[bool] = None
        self._serial: Optional[str] = None
        self._serial_tried: bool = False
        self._last_logged_anc: Optional[int] = None
        self._last_logged_mix: Optional[int] = None

        self.hidraw_reader: Optional[HidrawBatteryReader] = None
        # Keep `pyusb_detach` for CLI compatibility, but the default behavior
        # now mirrors `jbl_battery_simple.py` (best-effort detach if active).
        self.pyusb_reader = PyUsbBatteryReader(timeout_ms=1000)

        # Model name for the tray label/title, e.g. "JBL Quantum810 Wireless".
        self._model_name = detect_model_name() or "JBL Quantum"
        hidraw = find_hidraw_device()
        if hidraw:
            self._attach_hidraw_reader(hidraw)

        # Numeric badge icon state: the percentage is drawn into the tray icon
        # (some desktops hide the AppIndicator label).
        self._icon_dir = ICON_DIR
        os.makedirs(self._icon_dir, exist_ok=True)
        self._last_badge_percent: Optional[int] = None
        self._last_icon: Optional[str] = None
        self._numeric_icons_ok = None if numeric_icon else False  # None = not tried yet

        self.indicator = self.AppIndicator.Indicator.new(
            "jbl-quantum910-battery",
            "battery-missing-symbolic",
            self.AppIndicator.IndicatorCategory.HARDWARE,
        )
        self.indicator.set_status(self.AppIndicator.IndicatorStatus.ACTIVE)

        self.menu = self._build_menu()
        self.indicator.set_menu(self.menu)

        # First render
        self._render()
        _log(f"Tray started. prefer_pyusb={self.prefer_pyusb} hidraw={hidraw!s}")

        # Periodic updates
        self.GLib.timeout_add(int(self.refresh_seconds * 1000), self._tick)

    def _attach_hidraw_reader(self, hidraw: str) -> None:
        """Attach a hidraw reader and adapt the reader priority.

        On the Quantum 810 hidraw is strictly better: it supports direct
        battery polling (feature 0x49), while the pyusb interface number is
        a guess. Prefer hidraw when it is available.
        """
        if self.hidraw_reader is not None:
            self.hidraw_reader.close()
        self.hidraw_reader = HidrawBatteryReader(hidraw)
        model = detect_model_name()
        if model:
            self._model_name = model
        if "810" in self._model_name:
            self.prefer_pyusb = False
        _log(f"hidraw reader attached: {hidraw} ({self._model_name})")

    def _rescan_hidraw(self) -> None:
        """Keep the hidraw reader pointed at the current matching node.

        - pyusb sessions detach the kernel driver from the dongle's vendor
          interface, which removes its hidraw node until the dongle is
          replugged: scan each tick until it shows up again.
        - hidraw node numbers can shift when other HID devices (docks,
          receivers) are unplugged: switch nodes whenever the match moves.
        """
        current = self.hidraw_reader.path if self.hidraw_reader else None
        hidraw = find_hidraw_device()
        if hidraw == current:
            return
        if hidraw:
            self._attach_hidraw_reader(hidraw)
        elif self.hidraw_reader is not None:
            _log(f"hidraw node {current} is gone; waiting for it to reappear")
            self.hidraw_reader = None

    def _build_menu(self):
        menu = self.Gtk.Menu()

        self._status_item = self.Gtk.MenuItem(label="Battery: --%")
        self._status_item.set_sensitive(False)
        menu.append(self._status_item)

        # Extra headset state (Quantum 810 event map):
        self._menu_anc_item = self.Gtk.MenuItem(label="ANC: --")
        self._menu_anc_item.set_sensitive(False)
        menu.append(self._menu_anc_item)

        self._menu_mic_item = self.Gtk.MenuItem(label="Microphone: --")
        self._menu_mic_item.set_sensitive(False)
        menu.append(self._menu_mic_item)

        self._menu_mix_item = self.Gtk.MenuItem(label="Game/Chat: --")
        self._menu_mix_item.set_sensitive(False)
        menu.append(self._menu_mix_item)

        self._menu_serial_item = self.Gtk.MenuItem(label="Serial: --")
        self._menu_serial_item.set_sensitive(False)
        menu.append(self._menu_serial_item)

        item_refresh = self.Gtk.MenuItem(label="Refresh now")
        item_refresh.connect("activate", lambda *_: self._force_refresh())
        menu.append(item_refresh)

        if self.enable_controls:
            # State-changing controls (opt-in via --enable-controls).
            ctrl_sep = self.Gtk.SeparatorMenuItem()
            menu.append(ctrl_sep)

            anc_item = self.Gtk.MenuItem(label="Cycle ANC (off -> on -> talk-through)")
            anc_item.connect("activate", lambda *_: self._cycle_anc())
            menu.append(anc_item)

            lights_item = self.Gtk.MenuItem(label="Toggle lights")
            lights_item.connect("activate", lambda *_: self._toggle_lights())
            menu.append(lights_item)

            sidetone_menu = self.Gtk.Menu()
            for level in ("off", "low", "mid", "high"):
                sub = self.Gtk.MenuItem(label=f"Sidetone: {level}")
                sub.connect("activate", lambda _w, lv=level: self._set_sidetone(lv))
                sidetone_menu.append(sub)
            sidetone_item = self.Gtk.MenuItem(label="Sidetone")
            sidetone_item.set_submenu(sidetone_menu)
            menu.append(sidetone_item)

        item_sep = self.Gtk.SeparatorMenuItem()
        menu.append(item_sep)

        item_quit = self.Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", lambda *_: self._quit())
        menu.append(item_quit)

        menu.show_all()
        return menu

    # -- controls (only wired up with --enable-controls) -------------------------

    def _cycle_anc(self) -> None:
        if self.hidraw_reader is None:
            return
        nxt = 1 if self._anc is None else (self._anc + 1) % 3
        if self.hidraw_reader.send_feature(0x46, nxt):
            self._anc = nxt
            _log(f"ANC set to {StatusSample.ANC_NAMES.get(nxt, nxt)} (feature 0x46)")
            self._render()

    def _toggle_lights(self) -> None:
        if self.hidraw_reader is None:
            return
        new_state = not (self._lights_on or False)
        if self.hidraw_reader.send_feature(0x4B, 1 if new_state else 0):
            self._lights_on = new_state
            _log(f"Lights {'on' if new_state else 'off'} (feature 0x4b)")
            self._render()

    def _set_sidetone(self, level: str) -> None:
        values = {"off": 0, "low": 1, "mid": 2, "high": 3}
        if self.hidraw_reader is None:
            return
        if self.hidraw_reader.send_feature(0x5D, values[level]):
            _log(f"Sidetone set to {level} (feature 0x5d)")

    def _quit(self):
        try:
            if self.hidraw_reader:
                self.hidraw_reader.close()
            self.pyusb_reader.close()
        finally:
            self.Gtk.main_quit()

    def _update_numeric_icon(self, percent: int) -> None:
        """Render the battery percentage into the tray icon.

        Writes a small PNG badge (cached per percentage) and points the
        AppIndicator at it, because some desktops hide the indicator label.
        """
        if self._last_badge_percent == percent:
            return
        os.makedirs(self._icon_dir, exist_ok=True)
        png_path = os.path.join(self._icon_dir, f"jbl-quantum-batt-{percent}.png")
        if not _write_badge_png(percent, png_path):
            self._numeric_icons_ok = False
            return
        # The absolute file path is supported by libappindicator: it loads
        # the PNG and passes it to the panel as a pixmap.
        self.indicator.set_icon_full(png_path, f"{self._model_name} Battery {percent}%")
        self._last_badge_percent = percent

    def _battery_icon_name(self, percent: Optional[int], is_muted: bool = False) -> str:
        """Icon name for the battery level (mute status respected).

        Prefers the theme's fine-grained numeric battery series
        (battery-050-symbolic etc., the same icons the desktop battery
        widget uses) and falls back to the freedesktop standard names
        (battery-full/good/low/caution) when those are unavailable.
        """
        if is_muted:
            return "microphone-sensitivity-muted-symbolic"
        if percent is None:
            return "battery-missing-symbolic"

        percent = max(0, min(100, int(percent)))
        step = min(100, (percent + 5) // 10 * 10)  # nearest 10% step
        if percent >= 95:
            classic = "battery-full-symbolic"
        elif percent >= 40:
            classic = "battery-good-symbolic"
        elif percent >= 15:
            classic = "battery-low-symbolic"
        else:
            classic = "battery-caution-symbolic"
        candidates = (
            f"battery-{step:03d}-symbolic",
            f"battery-{step:03d}",
            classic,
        )
        try:
            theme = self.Gtk.IconTheme.get_default()
            for name in candidates:
                if theme.has_icon(name):
                    return name
        except Exception:
            pass
        return classic

    def _read_once(self) -> Optional[BatterySample]:
        # Choose reading order.
        readers = []
        if self.prefer_pyusb:
            readers = [("pyusb", self.pyusb_reader.poll), ("hidraw", (self.hidraw_reader.poll if self.hidraw_reader else None))]
        else:
            readers = [("hidraw", (self.hidraw_reader.poll if self.hidraw_reader else None)), ("pyusb", self.pyusb_reader.poll)]

        for name, fn in readers:
            if fn is None:
                continue
            # Never fall back to pyusb while the hidraw reader is attached:
            # claiming the USB interface via pyusb detaches the kernel driver
            # and destroys the hidraw node until the dongle is replugged.
            if name == "pyusb" and self.hidraw_reader is not None:
                continue
            try:
                sample = fn()
                if sample is not None:
                    return sample
            except Exception:
                continue
        return None

    def _read_all_once(self) -> tuple[Optional[BatterySample], Optional[MuteSample], Optional[StatusSample]]:
        """Read battery, mute and extra status from device."""
        # Priority: read battery using poll (original method that worked)
        # Then try to read mute/status separately if needed
        readers = []
        if self.prefer_pyusb:
            readers = [("pyusb", self.pyusb_reader.poll), ("hidraw", (self.hidraw_reader.poll if self.hidraw_reader else None))]
        else:
            readers = [("hidraw", (self.hidraw_reader.poll if self.hidraw_reader else None)), ("pyusb", self.pyusb_reader.poll)]

        battery_sample = None
        for _, fn in readers:
            if fn is None:
                continue
            try:
                battery_sample = fn()
                if battery_sample is not None:
                    break
            except Exception:
                continue
        
        # Try to read mute + status using poll_all (non-blocking, won't interfere if no data)
        mute_sample = None
        status_sample = None
        try:
            # Only try hidraw for mute/status (less intrusive)
            if self.hidraw_reader:
                try:
                    _, mute, status = self.hidraw_reader.poll_all()
                    if mute is not None:
                        mute_sample = mute
                    if status is not None:
                        status_sample = status
                except Exception:
                    pass
            # Also try pyusb poll_all, but only without hidraw: claiming the
            # USB interface detaches the kernel driver, which destroys the
            # hidraw node that the (preferred) hidraw reader needs.
            # NOTE: never claim pyusb while a hidraw node exists - that is
            # what used to make the hidraw node disappear until replug.
            if mute_sample is None and self.hidraw_reader is None:
                try:
                    _, mute, _ = self.pyusb_reader.poll_all()
                    if mute is not None:
                        mute_sample = mute
                except Exception:
                    pass
        except Exception:
            pass
        
        return battery_sample, mute_sample, status_sample

    def _apply_status(self, status_sample: StatusSample) -> bool:
        """Fold a status sample (event or feature read-back) into app state.

        Returns True when something changed and a re-render is needed.
        """
        needs_render = False
        if status_sample.anc is not None and status_sample.anc != self._anc:
            self._anc = status_sample.anc
            if self._last_logged_anc != self._anc:
                _log(f"ANC: {StatusSample.ANC_NAMES.get(self._anc, self._anc)} (source={status_sample.source})")
                self._last_logged_anc = self._anc
            needs_render = True
        if status_sample.mix is not None and status_sample.mix != self._mix:
            self._mix = status_sample.mix
            if self._last_logged_mix != self._mix:
                _log(f"Game/Chat mix: {self._mix}/16 (source={status_sample.source})")
                self._last_logged_mix = self._mix
            needs_render = True
        if status_sample.lights is not None:
            self._lights_on = status_sample.lights
        if status_sample.mic_muted is not None:
            # Make the mic state visible in the menu as soon as we know it.
            if self.last_mute_sample is None:
                self.last_mute_sample = MuteSample(
                    is_toggle=False,
                    muted=status_sample.mic_muted,
                    source=status_sample.source,
                    raw_hex=status_sample.raw_hex,
                    ts=status_sample.ts,
                )
            if status_sample.mic_muted != self._is_muted:
                self._is_muted = status_sample.mic_muted
                _log(f"Microphone {'MUTED' if self._is_muted else 'on'} (source={status_sample.source})")
                needs_render = True
        if (status_sample.anc is not None or status_sample.mix is not None
                or status_sample.lights is not None or status_sample.mic_muted is not None):
            self.last_status_sample = status_sample
        return needs_render

    def _force_refresh(self):
        sample, _mute, status = self._read_all_once()
        if sample is not None:
            self.last_sample = sample
        if status is not None:
            self._apply_status(status)
        if self.hidraw_reader is not None:
            try:
                state_sample = self.hidraw_reader.read_state()
                if state_sample is not None:
                    self._apply_status(state_sample)
            except Exception:
                pass
        self._render()

    def _tick(self):
        # Pick up a hidraw node that appeared after startup (e.g. after the
        # dongle was replugged following a pyusb session).
        self._rescan_hidraw()
        # Read battery, mute and extra status in a single pass
        battery_sample, mute_sample, status_sample = self._read_all_once()
        
        needs_render = False
        
        if battery_sample is not None:
            # Force render if battery changed
            if self.last_sample is None or self.last_sample.percent != battery_sample.percent:
                needs_render = True
            self.last_sample = battery_sample
            if self._last_logged_percent != battery_sample.percent:
                _log(f"Battery: {battery_sample.percent}% (source={battery_sample.source}, data={battery_sample.raw_hex})")
                self._last_logged_percent = battery_sample.percent
                self._last_logged_error = None
        else:
            # Surface pyusb errors (most common: permission / claim interface)
            err = getattr(self.pyusb_reader, "last_error", None)
            if err and err != self._last_logged_error:
                _log(f"No reading. pyusb error: {err}")
                self._last_logged_error = err
            # Even if no new battery data, keep rendering with last known value
        
        if mute_sample is not None:
            old_muted = self._is_muted
            self.last_mute_sample = mute_sample
            if mute_sample.is_toggle:
                # Code 0x2f 0x02 is a toggle - flip the state
                self._is_muted = not self._is_muted
                status = "MUTED" if self._is_muted else "UNMUTED"
                emoji = "🔇" if self._is_muted else "🎤"
                _log(f"Microphone {emoji} {status} (toggle detected, source={mute_sample.source}, data={mute_sample.raw_hex})")
            else:
                # 0x2f 0x00 = unmuted state, or 0x06 0x00/0x01 mic state (810)
                self._is_muted = bool(mute_sample.muted)
                status = "MUTED" if self._is_muted else "UNMUTED"
                _log(f"Microphone {'🔇' if self._is_muted else '🎤'} {status} (state received, source={mute_sample.source}, data={mute_sample.raw_hex})")
            
            # Force render if mute state changed
            if old_muted != self._is_muted:
                needs_render = True
        
        if status_sample is not None:
            if self._apply_status(status_sample):
                needs_render = True
        
        # Read back the current state via feature reports (0x45/0x67/0x4a/0x62).
        # This fills in ANC/mic/mix/lights immediately after startup even when
        # the headset sends no events, and keeps them fresh if an event was
        # missed (e.g. the tray started while the headset was already on).
        if self.hidraw_reader is not None:
            try:
                state_sample = self.hidraw_reader.read_state()
                if state_sample is not None:
                    if self._apply_status(state_sample):
                        needs_render = True
            except Exception:
                pass
        
        # Serial string: try once per hidraw reader lifetime (810 only).
        if not self._serial_tried and self.hidraw_reader is not None:
            self._serial_tried = True
            try:
                self._serial = self.hidraw_reader.read_serial()
                if self._serial:
                    _log(f"Device serial/part number: {self._serial}")
                    needs_render = True
            except Exception:
                pass
        # Always render, but force update if something changed
        if needs_render or (battery_sample is not None and self._last_label == "--%"):
            self._last_label = None  # Force label update
        self._render()
        return True  # keep timer

    def _render(self):
        percent = self.last_sample.percent if self.last_sample else None
        icon = self._battery_icon_name(percent, self._is_muted)

        # Some desktops (e.g. GNOME with the AppIndicator extension) hide the
        # indicator label and tooltips, so draw the percentage into the icon
        # itself (a small badge with the number).
        use_numeric = percent is not None and self._numeric_icons_ok is not False
        if use_numeric:
            try:
                self._update_numeric_icon(percent)
            except Exception as e:
                self._numeric_icons_ok = False
                _log(f"Numeric icon rendering unavailable: {e}")
                use_numeric = False
        if not use_numeric and icon != self._last_icon:
            # Native themed battery icons: crisp vector icons from the icon
            # theme (same family the desktop battery widget uses).
            self.indicator.set_icon_full(icon, f"{self._model_name} Battery")
            self.indicator.set_status(self.AppIndicator.IndicatorStatus.ACTIVE)
            self._last_icon = icon

        # Menu info row: guaranteed-visible numeric value
        if getattr(self, "_status_item", None):
            try:
                if percent is not None:
                    age_s = max(0.0, time.time() - self.last_sample.ts)
                    self._status_item.set_label(f"Battery: {percent}% (updated {age_s:.0f}s ago)")
                else:
                    self._status_item.set_label("Battery: --% (waiting for data)")
            except Exception:
                pass

        err = getattr(self.pyusb_reader, "last_error", None)
        if percent is not None:
            mute_indicator = " 🔇" if self._is_muted else ""
            label = f"{percent}%{mute_indicator}"
        elif err:
            label = "ERR"
        else:
            label = "--%"
        
        # Always update label if we have battery data or if label changed
        # Force update if we have data but label is still showing "--%"
        should_update = (
            label != self._last_label or 
            self._last_label is None or
            (percent is not None and self._last_label == "--%")
        )
        
        if should_update:
            try:
                self.indicator.set_label(label, "")
                self._last_label = label
                # Log when label is updated for debugging
                if percent is not None:
                    _log(f"Tray label updated: {label}")
            except Exception as e:
                # Some tray implementations don't support set_label
                _log(f"Error updating label: {e}")
                pass

        # Menu items for the extra headset state (ANC / mic / mix / serial)
        try:
            if getattr(self, "_menu_anc_item", None) is not None:
                anc_label = StatusSample.ANC_NAMES.get(self._anc, None) if self._anc is not None else None
                self._menu_anc_item.set_label(f"ANC: {anc_label or '--'}")
            if getattr(self, "_menu_mic_item", None) is not None:
                # Show mic state only once we have received any mute/mic event:
                if self.last_mute_sample is not None:
                    mic = "muted" if self._is_muted else "on"
                else:
                    mic = "--"
                self._menu_mic_item.set_label(f"Microphone: {mic}")
            if getattr(self, "_menu_mix_item", None) is not None:
                tmp = StatusSample(mix=self._mix)
                self._menu_mix_item.set_label(f"Game/Chat: {tmp.mix_label() or '--'}")
            if getattr(self, "_menu_serial_item", None) is not None:
                self._menu_serial_item.set_label(f"Serial: {self._serial or '--'}")
        except Exception:
            pass

        # Tooltip with freshness + source + mute status
        if self.last_sample:
            age_s = max(0.0, time.time() - self.last_sample.ts)
            mute_status = "🔇 MUTED" if self._is_muted else "🎤 Active"
            anc_status = StatusSample.ANC_NAMES.get(self._anc, "--") if self._anc is not None else "--"
            mix_status = StatusSample(mix=self._mix).mix_label() or "--"
            serial_status = self._serial or "--"
            tip = (f"{self._model_name}: {self.last_sample.percent}%\n"
                   f"Microphone: {mute_status}\n"
                   f"ANC: {anc_status}\n"
                   f"Game/Chat mix: {mix_status}\n"
                   f"Serial: {serial_status}\n"
                   f"Source: {self.last_sample.source}\n"
                   f"Updated: {age_s:.0f}s ago\n"
                   f"Data: {self.last_sample.raw_hex}")
        else:
            src = "hidraw" if self.hidraw_reader else "pyusb"
            extra = ""
            if src == "pyusb" and getattr(self.pyusb_reader, "last_error", None):
                extra = f"\nError: {self.pyusb_reader.last_error}"
            mute_status = "🔇 MUTED" if self._is_muted else "🎤 Active"
            tip = f"{self._model_name}: no reading yet\nMicrophone: {mute_status}\nTrying via: {src}{extra}\nTip: use the headset (volume/buttons) to generate traffic."
        try:
            title = f"{self._model_name} Battery {percent}%" if percent is not None else f"{self._model_name} Battery"
            self.indicator.set_title(title)
        except Exception:
            pass
        # Some implementations show tooltip via icon description:
        try:
            self.indicator.set_icon_desc(tip)
        except Exception:
            pass

    def run(self):
        # Handle Ctrl+C nicely when launched from terminal
        import signal

        signal.signal(signal.SIGINT, lambda *_: self._quit())
        signal.signal(signal.SIGTERM, lambda *_: self._quit())
        self.Gtk.main()


def main() -> int:
    parser = argparse.ArgumentParser(description="JBL Quantum 910/810 tray battery monitor (AppIndicator)")
    parser.add_argument("--refresh", type=float, default=1.0, help="Refresh interval in seconds (default: 1.0)")
    parser.add_argument(
        "--prefer-pyusb",
        action="store_true",
        help="(default) Tries pyusb first (recommended for the Quantum 910)",
    )
    parser.add_argument(
        "--prefer-hidraw",
        action="store_true",
        help="Prefer hidraw first (recommended for the Quantum 810)",
    )
    parser.add_argument(
        "--pyusb-detach-kernel",
        action="store_true",
        help="(compat) Ignored: the default behavior already tries best-effort detach like jbl_battery_simple.py",
    )
    parser.add_argument(
        "--numeric-icon",
        action="store_true",
        help="Draw the percentage into the icon as a custom badge "
        "(default: native themed battery icons)",
    )
    parser.add_argument(
        "--no-numeric-icon",
        action="store_true",
        help="(compat) Native themed battery icons (now the default)",
    )
    parser.add_argument(
        "--enable-controls",
        action="store_true",
        help="Add headset controls to the menu (ANC cycle, lights toggle, "
        "sidetone). These CHANGE device state via HID feature reports.",
    )
    args = parser.parse_args()

    app = BatteryTrayApp(
        refresh_seconds=args.refresh,
        prefer_pyusb=(not args.prefer_hidraw),
        pyusb_detach=args.pyusb_detach_kernel,
        numeric_icon=(args.numeric_icon and not args.no_numeric_icon),
        enable_controls=args.enable_controls,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

