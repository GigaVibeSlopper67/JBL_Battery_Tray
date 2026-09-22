#!/usr/bin/env python3
"""
JBL Quantum 810 - RGB lighting CLI/experiment (Linux, hidraw).

Decoded from the HeadsetControl #357 USB captures and verified live on a
Quantum 810 (see docs/HID_REPORTS.md). QuantumENGINE's lighting model:
per lighting ELEMENT (0 = logo, 1 = ring on the earcups) an effect
(Breathing/Solid/Wave/Glitch) plays a sequence of color SEGMENTS whose
interval distribution follows a TEMPO slider. Over HID:

    GET round  "arming": the QuantumENGINE connect-time GETs
               (0x68, 0x67, 0x62, 0x5c, 0x75, 0x49, 0x51, 0x47,
               0x4a, 0x45) - REQUIRED before lighting SETs take effect
               (otherwise the dongle caches them, the headset ignores
               them). Arming persists for at least several minutes.
    SET 0x4c   [zone, tempo, segments]           table header
    SET 0x4d   [zone, index, R, G, B, M, index*2]  one color segment; M is
               the interval/duration marker (00/02/04/05 seen)
    SET 0x4b   [0|1]                             lights off/on (commit)

The table applies on the lights OFF->ON transition; writes while the
lights are on do not change the running effect. Each 4b toggle is ACKed
by an 0x07 event (only on actual state changes). A solid color is
expressed as 5 identical segments and renders as a breathing-style pulse.

Two live-verified pitfalls cause the "color mixups":
  - SETs sent back-to-back can be DROPPED by the dongle/2.4 GHz link (the
    ring's writes - last in the burst - went missing entirely). Every SET
    is therefore paced by WRITE_DELAY seconds (--delay).
  - The device table keeps colors from earlier writes beyond the 5 written
    segments ("residue"). --solid therefore writes TWO passes: a clearing
    pass of --reset-segments identical frames (default 5) then the final
    QuantumENGINE-shape table (--segments, default 5). All segment counts
    are hard-clamped to 1..5: the QuantumENGINE capture (pcaps/) only ever
    sends 2 or 5 segments, and counts above 5 wedge the lighting MCU into
    a strobe lockup (the old 16/32-segment "reset").

CHANGES DEVICE STATE: colors persist until overwritten (QuantumENGINE on
Windows can always restore them; `--default` replays the factory table).

Examples:
    python3 tools/jbl_rgb.py --status                 # read-only probe
    python3 tools/jbl_rgb.py --solid ff0000 --lights on
    python3 tools/jbl_rgb.py --solid ff0000 --reset-segments 5    # full-table clear (max safe)
    python3 tools/jbl_rgb.py --solid 00ffcc --element logo --lights keep
    python3 tools/jbl_rgb.py --default --lights off   # factory teal + lights off
    python3 tools/jbl_rgb.py --raw "4c 00 64 05;4d 00 00 ff 00 00 02 00"
"""

from __future__ import annotations

import argparse
import fcntl
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jbl_status import (  # noqa: E402
    JblStatusReader,
    _HIDIOCSFEATURE,
)

# --- Report IDs ------------------------------------------------------------------

FEAT_TABLE_HEADER = 0x4C  # SET: [0x4c, element, tempo, segment_count]
FEAT_TABLE_FRAME = 0x4D  # SET: [0x4d, element, index, R, G, B, M, index*2]
FEAT_SET_LIGHTS = 0x4B    # SET: [0x4b, 0=off/1=on] (known)
FRAME_COUNT = 5           # QuantumENGINE default segments per element
MAX_SEGMENTS = 5          # hard cap (QuantumENGINE capture: only 2 or 5 ever sent)
RESET_SEGMENTS = 5        # clearing-pass slots per element (safe: == MAX_SEGMENTS)
# Value ranges observed in the original QuantumENGINE USB capture (pcaps/).
# Anything outside these wedged the lighting MCU into a strobe lockup (the
# old 16/32-segment "reset" is what broke it): segment counts are 2 or 5
# only, the 0x4c tempo byte is one of 0x28/0x32/0x64, and the 0x4d M byte is
# one of 0x00/0x01/0x02/0x04/0x05. The frame index stays 0..4 and the last
# byte stays 0..8 (index*2) - all implied by clamping segments to <= 5.
SAFE_TEMPOS = (0x28, 0x32, 0x64)
SAFE_MODES = (0x00, 0x01, 0x02, 0x04, 0x05)
# Pause after each lighting SET_REPORT (pacing, live-verified need): the
# dongle relays the writes to the headset over its 2.4 GHz link and drops
# reports sent back-to-back (the ring's writes - last in the burst - went
# missing entirely; partially delivered tables leave stale colors cycling).
# 10 ms keeps a change snappy; raise it (--delay) if mixing reappears.
WRITE_DELAY = 0.01
# Lighting elements (verified live): 0 = logo, 1 = ring.
ELEMENTS = {"logo": 0, "ring": 1}
ZONES = (0, 1)

# QuantumENGINE connect-time GET round. Required before lighting SETs take
# effect (verified live); the armed state persists for several minutes.
# Order taken from the original QuantumENGINE capture in pcaps/.
ARM_GET_RIDS = (0x68, 0x67, 0x62, 0x5C, 0x75, 0x49,
                0x51, 0x47, 0x4A, 0x45)

# Factory table observed in headset-usb-connect.pcapng (QuantumENGINE pushes
# this on connect): teal 33 ff cc frames, frame 2 = ff 00 cc, speed 0x64,
# M = 0x02 (zone 0) / 0x05 (zone 1).
FACTORY_SPEED = 0x64
FACTORY_MODES = {0: 0x02, 1: 0x05}
FACTORY_FRAMES = {
    0: [(0x33, 0xFF, 0xCC), (0x33, 0xFF, 0xCC), (0xFF, 0x00, 0xCC), (0x33, 0xFF, 0xCC), (0x33, 0xFF, 0xCC)],
    1: [(0x33, 0xFF, 0xCC), (0x33, 0xFF, 0xCC), (0xFF, 0x00, 0xCC), (0x33, 0xFF, 0xCC), (0x33, 0xFF, 0xCC)],
}


def _hexs(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)


def _clamp_segments(n: int) -> int:
    """Clamp a segment count to QuantumENGINE's observed safe range (1..5)."""
    return max(1, min(int(n), MAX_SEGMENTS))


def _clamp_tempo(tempo: int) -> int:
    """Clamp the 0x4c tempo byte to the values QuantumENGINE actually sends."""
    tempo = int(tempo)
    return tempo if tempo in SAFE_TEMPOS else min(SAFE_TEMPOS, key=lambda v: abs(v - tempo))


def _clamp_mode(mode: int) -> int:
    """Clamp the 0x4d M byte to the values QuantumENGINE actually sends."""
    mode = int(mode)
    return mode if mode in SAFE_MODES else min(SAFE_MODES, key=lambda v: abs(v - mode))


def set_feature_bytes(reader: JblStatusReader, data: bytes,
                      delay: float = WRITE_DELAY) -> bool:
    """SET_REPORT(Feature, data) with data[0] = report ID. CHANGES DEVICE STATE.

    Paces the write with a short pause afterwards: lighting SETs fired
    back-to-back can be dropped by the dongle/2.4 GHz link (live-verified:
    the ring's writes - last in the burst - went missing).
    """
    if reader._fd is None:
        return False
    try:
        fcntl.ioctl(reader._fd, _HIDIOCSFEATURE | (len(data) << 16), bytes(data), True)
        if delay > 0:
            time.sleep(delay)
        return True
    except OSError as e:
        print(f"SET feature 0x{data[0]:02x} failed: {e}", file=sys.stderr)
        return False


def arm_lighting(reader: JblStatusReader) -> bool:
    """QuantumENGINE connect-time GET round; required before lighting SETs.

    Verified live: without this round the dongle accepts the SETs but the
    headset ignores them. The GETs are read-only.
    """
    answered = 0
    for rid in ARM_GET_RIDS:
        if reader._get_feature(rid, 64) is not None:
            answered += 1
    print(f"arming GET round: {answered}/{len(ARM_GET_RIDS)} reports answered")
    return answered > 0


def send_table(reader: JblStatusReader, frames: dict, speed: int = FACTORY_SPEED,
               modes: dict | None = None, lights: str = "keep",
               segments: int = RESET_SEGMENTS, delay: float = WRITE_DELAY) -> bool:
    """Write the per-element color table using the QuantumENGINE sequence.

    `segments` frames are written per zone; `frames[zone]` supplies the
    colors (cycled when shorter). Writing MORE than the 5 QuantumENGINE
    default segments overwrites the whole device table - a reset that
    clears stale segments from earlier writes (the color mixups).
    """
    modes = modes or FACTORY_MODES
    segments = _clamp_segments(segments)
    speed = _clamp_tempo(speed)
    for zone in ZONES:
        if zone not in frames:
            continue
        header = bytes([FEAT_TABLE_HEADER, zone, speed, segments])
        if not set_feature_bytes(reader, header, delay):
            return False
        print(f"  SET 0x4c zone {zone}: {_hexs(header)}")
        for i in range(segments):
            r, g, b = frames[zone][i % len(frames[zone])]
            mode = _clamp_mode(modes.get(zone, 0x02))
            frame = bytes([FEAT_TABLE_FRAME, zone, i, r, g, b, mode, i * 2])
            if not set_feature_bytes(reader, frame, delay):
                return False
    if lights == "on":
        ok = reader.set_lights(True)
        print(f"  SET 0x4b lights on: {'ok' if ok else 'FAILED'}")
    elif lights == "off":
        ok = reader.set_lights(False)
        print(f"  SET 0x4b lights off: {'ok' if ok else 'FAILED'}")
    return True


def listen_events(reader: JblStatusReader, seconds: float) -> None:
    """Print interrupt-IN events for a while (ACKs like the 0x07 lights event)."""
    print(f"listening for dongle events for {seconds:.0f}s...")
    t0 = time.time()
    seen = 0
    while time.time() - t0 < seconds:
        try:
            data = os.read(reader._fd, 64)
        except BlockingIOError:
            time.sleep(0.02)
            continue
        except OSError:
            break
        if not data:
            continue
        seen += 1
        print(f"  INTR: {_hexs(data[:16])}")
    if not seen:
        print("  (no events)")


def probe(reader: JblStatusReader) -> None:
    """Read-only: known state + RGB read-back attempts (0x4c/0x4d/0x4e)."""
    st = reader.poll()
    print(f"model:   {st.model}")
    print(f"node:    {reader.path}")
    print(f"battery: {st.battery_percent}%   ANC: {st.anc_label()}   mic: "
          f"{'muted' if st.mic_muted else 'on'}   lights: "
          f"{'on' if st.lights_on else 'off'}")
    print(f"mix:     {st.mix_label()}   sidetone: {st.sidetone or '--'}")
    print()
    print("RGB read-back attempts (unknown GETs may echo the nearest known")
    print("lower report, so verify the echoed report id):")
    for rid in (0x4C, 0x4D, 0x4E):
        for length in (8, 16):
            feat = reader._get_feature(rid, length)
            if feat:
                echoed = feat[0] == rid
                print(f"  GET 0x{rid:02x} len={length:2d} -> {_hexs(feat[:16])}"
                      f"   {'(echo matches)' if echoed else '(ECHO MISMATCH - nearest-known answer)'}")
            else:
                print(f"  GET 0x{rid:02x} len={length:2d} -> (no answer)")


def parse_hex_sequence(text: str) -> list:
    """'4c 00 64 05;4d 00 00 ff 00 00 02 00' -> [bytes, bytes]."""
    reports = []
    for part in text.split(";"):
        tokens = part.split()
        if not tokens:
            continue
        try:
            reports.append(bytes(int(t, 16) for t in tokens))
        except ValueError:
            raise SystemExit(f"invalid hex sequence near: {part!r}")
    return reports


def main() -> int:
    ap = argparse.ArgumentParser(description="JBL Quantum 810 RGB lighting CLI "
                                             "(feature reports 0x4c/0x4d/0x4b)")
    ap.add_argument("--status", action="store_true",
                    help="read-only probe: known state + 0x4c/0x4d/0x4e GET attempts")
    ap.add_argument("--solid", metavar="RRGGBB",
                    help="single color (breathing effect) written as --segments "
                         "identical segments - CHANGES DEVICE STATE")
    ap.add_argument("--element", choices=["logo", "ring", "both"], default="both",
                    help="lighting element for --solid (default both; verified: "
                         "element 0 = logo, 1 = ring)")
    ap.add_argument("--default", action="store_true",
                    help="replay the factory teal table - CHANGES DEVICE STATE")
    ap.add_argument("--raw", metavar="SEQ",
                    help="semicolon-separated hex feature reports, "
                         "e.g. '4c 00 64 05;4d 00 00 ff 00 00 02 00' - CHANGES DEVICE STATE")
    ap.add_argument("--speed", type=lambda s: _clamp_tempo(int(s, 0)), default=None,
                    help="speed byte for the 0x4c header (default 0x64; safe set: "
                         "0x28/0x32/0x64 - other values are clamped to the nearest)")
    ap.add_argument("--mode", type=lambda s: _clamp_mode(int(s, 0)), default=None,
                    help="M byte for the 0x4d frames (default: 0x02 zone 0 / 0x05 "
                         "zone 1; safe set 0x00/0x01/0x02/0x04/0x05 - other values "
                         "are clamped to the nearest)")
    ap.add_argument("--segments", type=lambda s: _clamp_segments(int(s, 0)),
                    default=FRAME_COUNT, metavar="N",
                    help=f"final 0x4d table segments per element (default "
                         f"{FRAME_COUNT}, QuantumENGINE-exact tempo; counts are "
                         f"clamped to 1..{MAX_SEGMENTS} - QuantumENGINE never "
                         "sends more than 5)")
    ap.add_argument("--reset-segments",
                    type=lambda s: 0 if int(s, 0) == 0 else _clamp_segments(int(s, 0)),
                    default=RESET_SEGMENTS, metavar="N",
                    help=f"clearing pass: overwrite N slots per element before "
                         f"the final table (default {RESET_SEGMENTS}; 0 disables; "
                         f"clamped to 1..{MAX_SEGMENTS} - >5 wedged the lighting "
                         "MCU)")
    ap.add_argument("--delay", type=float, default=WRITE_DELAY, metavar="SEC",
                    help=f"pause between SET reports (default {WRITE_DELAY}s; "
                         "raise it if writes are still dropped)")
    ap.add_argument("--lights", choices=["on", "off", "keep"], default="keep",
                    help="after writing a table: turn lights on/off or leave as-is (default keep)")
    ap.add_argument("--listen", type=float, default=3.0, metavar="SEC",
                    help="listen for dongle ACK events for SEC seconds after a SET (default 3)")
    args = ap.parse_args()

    reader = JblStatusReader()
    if not reader.open():
        print("error: no JBL Quantum 810/910 hidraw device found (or no write access)",
              file=sys.stderr)
        return 1

    try:
        if args.status or not (args.solid or args.default or args.raw):
            probe(reader)
            return 0

        # Baseline before changing anything (the revert path).
        st = reader.poll()
        print("baseline before change:")
        print(f"  lights: {'on' if st.lights_on else 'off'}   battery: {st.battery_percent}%")
        print("  revert options: '--default' (factory teal) or QuantumENGINE on Windows")
        print()
        # Arming GET round: without it the dongle caches lighting SETs but
        # the headset ignores them (verified live).
        if not arm_lighting(reader):
            print("warning: arming GET round failed - the headset may ignore lighting writes",
                  file=sys.stderr)
        print()

        if args.solid:
            rgb = bytes.fromhex(args.solid)
            if len(rgb) != 3:
                raise SystemExit("--solid expects RRGGBB, e.g. ff0000")
            r, g, b = rgb[0], rgb[1], rgb[2]
            wanted = {"logo": (0,), "ring": (1,), "both": ZONES}[args.element]
            modes = ({0: args.mode, 1: args.mode} if args.mode is not None else FACTORY_MODES)
            speed = (args.speed if args.speed is not None else FACTORY_SPEED)
            ok = True
            if args.reset_segments:
                # Clearing pass: overwrite every slot with the new color
                # (stale colors from earlier writes otherwise keep cycling),
                # then the final table restores the QuantumENGINE shape.
                clear = {element: [(r, g, b)] * args.reset_segments
                         for element in wanted}
                print(f"reset pass: {args.reset_segments} segments per element:")
                ok = send_table(reader, clear, speed=speed, modes=modes,
                                lights="keep", segments=args.reset_segments,
                                delay=args.delay)
            if ok:
                frames = {element: [(r, g, b)] * args.segments
                          for element in wanted}
                print(f"writing color #{args.solid.upper()} (R={r} G={g} B={b}) "
                      f"to element(s): {args.element} ({args.segments} segments):")
                ok = send_table(reader, frames, speed=speed,
                                modes=modes, lights=args.lights,
                                segments=args.segments, delay=args.delay)
            print(f"table write: {'OK' if ok else 'FAILED'}")

        if args.default:
            print("writing factory table (teal 33 ff cc, speed 0x64):")
            ok = True
            if args.reset_segments:
                clear = {zone: [FACTORY_FRAMES[zone][i % len(FACTORY_FRAMES[zone])]
                                for i in range(args.reset_segments)]
                         for zone in ZONES}
                print(f"reset pass: {args.reset_segments} segments per element:")
                ok = send_table(reader, clear, speed=FACTORY_SPEED,
                                modes=FACTORY_MODES, lights="keep",
                                segments=args.reset_segments, delay=args.delay)
            if ok:
                ok = send_table(reader, FACTORY_FRAMES, speed=FACTORY_SPEED,
                                modes=FACTORY_MODES, lights=args.lights,
                                segments=args.segments, delay=args.delay)
            print(f"table write: {'OK' if ok else 'FAILED'}")

        if args.raw:
            reports = parse_hex_sequence(args.raw)
            print(f"sending {len(reports)} raw feature reports:")
            for rep in reports:
                ok = set_feature_bytes(reader, rep, args.delay)
                print(f"  SET 0x{rep[0]:02x} ({len(rep)}B): {_hexs(rep)}  "
                      f"{'ok' if ok else 'FAILED'}")

        listen_events(reader, args.listen)
    finally:
        reader.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())