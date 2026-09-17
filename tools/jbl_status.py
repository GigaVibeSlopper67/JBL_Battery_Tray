#!/usr/bin/env python3
"""
JBL Quantum 810/910 - Full headset status reader (Linux, hidraw).

Reads far more than the battery: the dongle pushes vendor event reports
(interrupt IN) and answers feature-report GETs (control). Everything below
was confirmed by live probing of a Quantum 810 dongle (0ecb:2069) and by
parsing the USB captures attached to HeadsetControl issue #357
(https://github.com/Sapd/HeadsetControl/issues/357).

Event reports (interrupt IN, first byte = report ID):
    0x02  ANC state        byte1: 0=off, 1=on, 2=talk-through
    0x06  Microphone       byte1: 0=off (muted), 1=on
    0x07  Lights           byte1: 0=off, 1=on
    0x08  Battery          byte1: 0..100 percent
    0x10  Game/Chat mix    byte1: 0x00=full chat ... 0x10=full game (0..16)
    0x03  Power marker     seen as `03 00` when the headset powers on
    0x09  Power marker     seen as `09 01` when the headset powers on
    0x2f  Mute (910 only)  0x2f 0x02 = toggle mute, 0x2f 0x00 = unmuted

    When the headset powers on, the dongle emits a full state burst:
    02, 03, 06, 07, 08 (x4), 09, 10.

Feature reports (GET_REPORT, 810 confirmed; 910 differs):
    0x49  Battery          echo 0x49, byte1 = percent (pollable anytime)
    0x61  Part/serial      ASCII string, e.g. "MM0169-EM001565..."
    0x51  EQ-like data     12 small values (undecoded, read-only)
    0x07  Dynamic status   byte1 changes at runtime (undecoded)

Feature reports (SET_REPORT, 810 confirmed - these CHANGE device state):
    0x46  ANC              byte1: 0=off, 1=on, 2=talk-through
    0x4b  Lights           byte1: 0=off, 1=on
    0x5d  Sidetone         byte1: 0=off, 1=low, 2=mid, 3=high

CLI:
    python3 tools/jbl_status.py --json          # one-shot JSON dump
    python3 tools/jbl_status.py --watch 0.5     # continuous status output
    python3 tools/jbl_status.py --set-anc on    # control (needs write access)
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

# --- Device identification ---------------------------------------------------

VENDOR_ID = 0x0ECB
KNOWN_PRODUCTS = {
    0x2088: "JBL Quantum910 Wireless",
    0x2069: "JBL Quantum810 Wireless",
}

# --- Confirmed event report IDs (interrupt IN) --------------------------------

RID_ANC = 0x02        # byte1: 0=off, 1=on, 2=talk-through
RID_POWER_A = 0x03    # `03 00` on power-on (marker, meaning not fully decoded)
RID_MIC = 0x06        # byte1: 0=off (muted), 1=on
RID_LIGHTS = 0x07     # byte1: 0=off, 1=on
RID_BATTERY = 0x08    # byte1: percent 0..100
RID_POWER_B = 0x09    # `09 01` on power-on (marker)
RID_MIX = 0x10        # byte1: 0x00=full chat .. 0x10=full game (0..16)
RID_MUTE_910 = 0x2F   # 910: 0x02=toggle mute, 0x00=unmuted

# --- Feature reports -----------------------------------------------------------

FEAT_BATTERY = 0x49   # GET: [0x49, percent]; 810 only
FEAT_SET_ANC = 0x46   # SET: [0x46, 0=off/1=on/2=tt]
FEAT_SET_LIGHTS = 0x4B  # SET: [0x4b, 0/1]
FEAT_SET_SIDETONE = 0x5D  # SET: [0x5d, 0=off/1=low/2=mid/3=high]
FEAT_SERIAL = 0x61    # GET: ASCII part/serial string
FEAT_EQ = 0x51        # GET: EQ-like data (undecoded)

# Feature reports that READ BACK the current state (all verified live;
# the GET report id is the SET report id minus 1 for the SET commands):
FEAT_GET_ANC = 0x45       # GET: [0x45, 0=off/1=on/2=tt]  (mirrors SET 0x46)
FEAT_GET_LIGHTS = 0x4A    # GET: [0x4a, 0=off/1=on]       (mirrors SET 0x4b)
FEAT_GET_SIDETONE = 0x5C  # GET: [0x5c, 0=off/1=low/2=mid/3=high] (mirrors SET 0x5d)
FEAT_GET_MIX = 0x62       # GET: [0x62, 0..16 game/chat mix] (mirrors event 0x10)
FEAT_GET_MIC = 0x67       # GET: [0x67, 1=on, 0=muted]    (mirrors event 0x06)

ANC_NAMES = {0: "off", 1: "on", 2: "talk-through"}
SIDETONE_NAMES = {0: "off", 1: "low", 2: "mid", 3: "high"}

_MIX_STEPS = 16  # 0x00 (chat) .. 0x10 (game)

_HIDIOCGFEATURE = (3 << 30) | (0x48 << 8) | 0x07
_HIDIOCSFEATURE = (3 << 30) | (0x48 << 8) | 0x06


@dataclass
class HeadsetStatus:
    """Snapshot of everything we can observe on the headset/dongle."""

    model: Optional[str] = None
    hidraw: Optional[str] = None
    # Event-derived state (only valid if seen since last power cycle):
    battery_percent: Optional[int] = None
    battery_source: Optional[str] = None      # "event" / "feature"
    anc: Optional[int] = None                 # 0=off, 1=on, 2=talk-through
    mic_muted: Optional[bool] = None
    lights_on: Optional[bool] = None
    mix: Optional[int] = None                 # 0..16, 0=full chat, 16=full game
    sidetone: Optional[int] = None            # 0=off, 1=low, 2=mid, 3=high
    serial: Optional[str] = None
    # Bookkeeping:
    seen_rids: set = field(default_factory=set)
    last_event_ts: Optional[float] = None
    eq_data: Optional[list] = None            # raw feature 0x51 values

    def mix_label(self) -> Optional[str]:
        if self.mix is None:
            return None
        m = max(0, min(_MIX_STEPS, self.mix))
        if m <= 2:
            return f"chat ({m}/{_MIX_STEPS})"
        if m >= _MIX_STEPS - 2:
            return f"game ({m}/{_MIX_STEPS})"
        return f"balanced ({m}/{_MIX_STEPS})"

    def anc_label(self) -> Optional[str]:
        if self.anc is None:
            return None
        return ANC_NAMES.get(self.anc, f"unknown(0x{self.anc:02x})")

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "hidraw": self.hidraw,
            "battery_percent": self.battery_percent,
            "battery_source": self.battery_source,
            "anc": self.anc_label(),
            "mic_muted": self.mic_muted,
            "lights_on": self.lights_on,
            "game_chat_mix": self.mix,
            "mix_label": self.mix_label(),
            "sidetone": SIDETONE_NAMES.get(self.sidetone) if self.sidetone is not None else None,
            "serial": self.serial,
            "seen_rids": sorted(f"0x{r:02x}" for r in self.seen_rids),
            "eq_data": self.eq_data,
        }


def find_hidraw_device() -> Optional[str]:
    """Find the hidraw node of a supported JBL Quantum dongle."""
    base = "/sys/class/hidraw"
    if not os.path.isdir(base):
        return None
    for entry in sorted(os.listdir(base)):
        uevent = os.path.join(base, entry, "device", "uevent")
        try:
            with open(uevent, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        upper = text.upper()
        if "00000ECB" not in upper:
            continue
        for pid in KNOWN_PRODUCTS:
            if f"0000{pid:04X}" in upper:
                return os.path.join("/dev", entry)
    return None


def detect_model_name() -> Optional[str]:
    """HID name from sysfs, e.g. 'Harman International Inc JBL Quantum810 Wireless'."""
    base = "/sys/class/hidraw"
    if not os.path.isdir(base):
        return None
    for entry in sorted(os.listdir(base)):
        uevent = os.path.join(base, entry, "device", "uevent")
        try:
            with open(uevent, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        if "00000ECB" not in text.upper():
            continue
        for pid in KNOWN_PRODUCTS:
            if f"0000{pid:04X}" in text.upper():
                for line in text.splitlines():
                    if line.startswith("HID_NAME="):
                        return line.split("=", 1)[1].strip()
    return None


class JblStatusReader:
    """hidraw-based status reader for the Quantum 810/910 dongles.

    State is updated from interrupt-IN event reports; the battery is polled
    directly via feature report 0x49 on the 810 (no headset traffic needed).
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or find_hidraw_device()
        self._fd: Optional[int] = None
        self._model = detect_model_name()
        self._is_810 = bool(self._model and "810" in self._model)
        self.status = HeadsetStatus(model=self._model, hidraw=self.path)
        self._feature_poll_ok: Optional[bool] = None
        self._state_read_ok: Optional[bool] = None

    # -- device handling -------------------------------------------------------

    def open(self) -> bool:
        if self._fd is not None:
            return True
        if not self.path or not os.path.exists(self.path):
            self.path = find_hidraw_device()
            self.status.hidraw = self.path
            if not self.path:
                return False
        try:
            # O_RDWR: GET/SET feature ioctls need write access.
            self._fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError:
            self._fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
            print(f"warning: read-only access to {self.path} (feature polling/controls disabled)",
                  file=sys.stderr)
        except OSError:
            self._fd = None
            return False
        return self._fd is not None

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._fd = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # -- low-level helpers ------------------------------------------------------

    def _get_feature(self, rid: int, length: int = 16) -> Optional[bytes]:
        """GET_REPORT(Feature, rid). Returns up to `length` bytes or None."""
        if self._fd is None:
            return None
        buf = bytearray(length)
        buf[0] = rid
        for i in range(1, length):
            buf[i] = 0x5A  # sentinel to detect real short payloads
        try:
            n = fcntl.ioctl(self._fd, _HIDIOCGFEATURE | (length << 16), buf, True)
        except OSError:
            return None
        if not n or n <= 0:
            return None
        return bytes(buf[:n])

    def _set_feature(self, rid: int, value: int) -> bool:
        """SET_REPORT(Feature, [rid, value]). CHANGES DEVICE STATE."""
        if self._fd is None:
            return False
        buf = bytes([rid, value])
        try:
            fcntl.ioctl(self._fd, _HIDIOCSFEATURE | (len(buf) << 16), buf, True)
            return True
        except OSError as e:
            print(f"SET feature 0x{rid:02x} failed: {e}", file=sys.stderr)
            return False

    # -- event parsing -----------------------------------------------------------

    def parse_event(self, packet: bytes) -> bool:
        """Fold one interrupt-IN packet into the status. Returns True if known."""
        if len(packet) < 2:
            return False
        rid, b1 = packet[0], packet[1]
        st = self.status
        st.seen_rids.add(rid)
        st.last_event_ts = time.time()
        if rid == RID_BATTERY and 0 <= b1 <= 100:
            st.battery_percent = int(b1)
            st.battery_source = "event"
            return True
        if rid == RID_ANC and b1 in ANC_NAMES:
            st.anc = int(b1)
            return True
        if rid == RID_MIC and b1 in (0, 1):
            st.mic_muted = (b1 == 0)
            return True
        if rid == RID_LIGHTS and b1 in (0, 1):
            st.lights_on = bool(b1)
            return True
        if rid == RID_MIX and 0 <= b1 <= _MIX_STEPS:
            st.mix = int(b1)
            return True
        if rid in (RID_POWER_A, RID_POWER_B):
            # Power-on markers; the dongle follows them with a full state burst.
            return True
        if rid == RID_MUTE_910:
            # Quantum 910 mute events (existing repo knowledge).
            st.mic_muted = (b1 == 0x02)
            return True
        return False

    def poll(self) -> HeadsetStatus:
        """Drain available events, then poll battery/serial via features."""
        if not self.open():
            return self.status
        # Drain interrupt-IN packets (non-blocking).
        for _ in range(64):
            try:
                data = os.read(self._fd, 64)
                if not data:
                    break
                self.parse_event(data)
            except BlockingIOError:
                break
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    break
                self.close()
                return self.status
        # Battery via feature 0x49 (810) as an always-fresh fallback.
        if self._is_810 and self._feature_poll_ok is not False:
            feat = self._get_feature(FEAT_BATTERY, 2)
            if feat and feat[0] == FEAT_BATTERY and 0 <= feat[1] <= 100:
                self._feature_poll_ok = True
                self.status.battery_percent = int(feat[1])
                self.status.battery_source = "feature"
            else:
                self._feature_poll_ok = False
        # Read back live state (verified live: these mirror the SET/event
        # values, so the status is correct immediately after startup even
        # without any event traffic).
        if self._state_read_ok is not False:
            ok_any = False
            feat = self._get_feature(FEAT_GET_ANC, 2)
            if feat and feat[0] == FEAT_GET_ANC and feat[1] in ANC_NAMES:
                self.status.anc = int(feat[1])
                ok_any = True
            feat = self._get_feature(FEAT_GET_MIC, 2)
            if feat and feat[0] == FEAT_GET_MIC and feat[1] in (0, 1):
                # 0x67 mirrors event 0x06: 1 = mic on, 0 = mic off (muted).
                self.status.mic_muted = (feat[1] == 0)
                ok_any = True
            feat = self._get_feature(FEAT_GET_LIGHTS, 2)
            if feat and feat[0] == FEAT_GET_LIGHTS and feat[1] in (0, 1):
                self.status.lights_on = bool(feat[1])
                ok_any = True
            feat = self._get_feature(FEAT_GET_MIX, 2)
            if feat and feat[0] == FEAT_GET_MIX and 0 <= feat[1] <= _MIX_STEPS:
                self.status.mix = int(feat[1])
                ok_any = True
            feat = self._get_feature(FEAT_GET_SIDETONE, 2)
            if feat and feat[0] == FEAT_GET_SIDETONE and feat[1] in (0, 1, 2, 3):
                self.status.sidetone = int(feat[1])
                ok_any = True
            self._state_read_ok = True if ok_any else False
        # Serial string (read once; cache).
        if self.status.serial is None:
            feat = self._get_feature(FEAT_SERIAL, 32)
            if feat and len(feat) > 2:
                raw = feat[1:].rstrip(b"\x00")
                text = raw.decode("ascii", errors="replace").strip()
                if text and any(c.isalnum() for c in text):
                    self.status.serial = text
        return self.status

    # -- controls (state-changing!) ----------------------------------------------

    def set_anc(self, mode: str) -> bool:
        """mode: 'off' | 'on' | 'tt' (talk-through)."""
        value = {"off": 0, "on": 1, "tt": 2}.get(mode)
        if value is None:
            raise ValueError(f"invalid ANC mode: {mode!r}")
        ok = self._set_feature(FEAT_SET_ANC, value)
        if ok:
            # Optimistic update; the dongle also pushes an 0x02 event.
            self.status.anc = value
        return ok

    def set_lights(self, on: bool) -> bool:
        ok = self._set_feature(FEAT_SET_LIGHTS, 1 if on else 0)
        if ok:
            self.status.lights_on = bool(on)
        return ok

    def set_sidetone(self, level: str) -> bool:
        value = {"off": 0, "low": 1, "mid": 2, "high": 3}.get(level)
        if value is None:
            raise ValueError(f"invalid sidetone level: {level!r}")
        return self._set_feature(FEAT_SET_SIDETONE, value)

    # -- extras -------------------------------------------------------------------

    def read_eq_data(self) -> Optional[list]:
        """Raw feature 0x51 data (EQ-like, meaning not decoded yet)."""
        feat = self._get_feature(FEAT_EQ, 16)
        if feat and len(feat) > 1:
            self.status.eq_data = list(feat[1:])
            return self.status.eq_data
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="JBL Quantum 810/910 status reader")
    ap.add_argument("--json", action="store_true", help="output JSON")
    ap.add_argument("--watch", nargs="?", const=1.0, default=None, type=float,
                    metavar="SEC", help="watch continuously (default interval 1s)")
    ap.add_argument("--set-anc", choices=["off", "on", "tt"], metavar="MODE",
                    help="set ANC mode (off|on|tt) - CHANGES DEVICE STATE")
    ap.add_argument("--set-lights", choices=["on", "off"],
                    help="set lights on/off - CHANGES DEVICE STATE")
    ap.add_argument("--set-sidetone", choices=["off", "low", "mid", "high"],
                    help="set sidetone level - CHANGES DEVICE STATE")
    ap.add_argument("--eq", action="store_true", help="also read feature 0x51 (EQ-like data)")
    args = ap.parse_args()

    reader = JblStatusReader()
    if not reader.open():
        print("error: no JBL Quantum 810/910 hidraw device found", file=sys.stderr)
        print("hint: replug the USB dongle (its hidraw node may have been removed by a pyusb session)",
              file=sys.stderr)
        return 1

    control_requested = args.set_anc or args.set_lights or args.set_sidetone
    st = reader.poll()

    if args.set_anc:
        ok = reader.set_anc(args.set_anc)
        print(f"set ANC {args.set_anc}: {'ok' if ok else 'FAILED'}")
    if args.set_lights:
        ok = reader.set_lights(args.set_lights == "on")
        print(f"set lights {args.set_lights}: {'ok' if ok else 'FAILED'}")
    if args.set_sidetone:
        ok = reader.set_sidetone(args.set_sidetone)
        print(f"set sidetone {args.set_sidetone}: {'ok' if ok else 'FAILED'}")

    if args.eq:
        reader.read_eq_data()

    if args.json:
        print(json.dumps(reader.status.to_dict(), indent=2))
    else:
        if control_requested:
            time.sleep(0.2)  # give the dongle a moment to push state events
            reader.poll()
        _print_status(reader.status)

    if args.watch is not None:
        last = None
        try:
            while True:
                time.sleep(args.watch)
                reader.poll()
                key = json.dumps(reader.status.to_dict(), sort_keys=True)
                if key != last:
                    _print_status(reader.status, label=f"[{time.strftime('%H:%M:%S')}] status changed:")
                    print()
                    last = key
        except KeyboardInterrupt:
            pass

    reader.close()
    return 0


def _print_status(st: HeadsetStatus, label: str = "") -> None:
    if label:
        print(label, flush=True)
    batt = "--" if st.battery_percent is None else f"{st.battery_percent}%"
    anc = st.anc_label() or "--"
    mic = "--" if st.mic_muted is None else ("muted" if st.mic_muted else "on")
    lights = "--" if st.lights_on is None else ("on" if st.lights_on else "off")
    mix = st.mix_label() or "--"
    print(f"  battery: {batt} ({st.battery_source or '-'})", flush=True)
    print(f"  ANC: {anc}", flush=True)
    print(f"  mic: {mic}", flush=True)
    print(f"  lights: {lights}", flush=True)
    print(f"  game/chat mix: {mix}", flush=True)
    side = "--" if st.sidetone is None else SIDETONE_NAMES.get(st.sidetone, str(st.sidetone))
    print(f"  sidetone: {side}", flush=True)
    print(f"  serial: {st.serial or '-'}", flush=True)
    if st.eq_data:
        print(f"  eq_data(0x51): {st.eq_data}", flush=True)
    if st.seen_rids:
        print(f"  event report IDs seen: {', '.join(f'0x{r:02x}' for r in sorted(st.seen_rids))}", flush=True)


if __name__ == "__main__":
    sys.exit(main())