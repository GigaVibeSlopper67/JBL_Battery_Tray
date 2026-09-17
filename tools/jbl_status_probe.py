#!/usr/bin/env python3
"""
JBL Quantum 810/910 - live protocol probe (read-only unless --set is used).

Modes:
  --monitor [SEC]   passive: decode interrupt-IN event reports as they arrive
  --features [SEC]  poll known feature reports, print any changed byte
  --scan            one full GET_REPORT(Feature) sweep over report IDs 0x01-0x77
  --correlate       guided: you perform actions, the tool diffs feature state

Uses the shared reader in tools/jbl_status.py.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jbl_status import (  # noqa: E402
    JblStatusReader,
    ANC_NAMES,
    RID_ANC,
    RID_BATTERY,
    RID_LIGHTS,
    RID_MIC,
    RID_MIX,
    RID_MUTE_910,
    RID_POWER_A,
    RID_POWER_B,
    _HIDIOCGFEATURE,
)

import fcntl  # noqa: E402


EVENT_DECODERS = {
    RID_ANC: lambda b: f"ANC={ANC_NAMES.get(b, f'?{b:02x}')}",
    RID_MIC: lambda b: f"MIC={'on' if b else 'off(muted)'}",
    RID_LIGHTS: lambda b: f"LIGHTS={'on' if b else 'off'}",
    RID_BATTERY: lambda b: f"BATTERY={b}%" if b <= 100 else f"BATTERY=?{b}",
    RID_MIX: lambda b: f"MIX={b}/16 ({'chat' if b <= 2 else 'game' if b >= 14 else 'mid'})",
    RID_POWER_A: lambda b: f"POWER-MARKER-A={b:02x}",
    RID_POWER_B: lambda b: f"POWER-MARKER-B={b:02x}",
    RID_MUTE_910: lambda b: f"MUTE-910={'toggle' if b == 2 else 'unmuted' if b == 0 else f'?{b:02x}'}",
}


def decode_event(data: bytes) -> str:
    if len(data) < 2:
        return "short"
    rid, b1 = data[0], data[1]
    dec = EVENT_DECODERS.get(rid)
    extra = " ".join(f"{b:02x}" for b in data[2:8]) if len(data) > 2 else ""
    base = dec(b1) if dec else f"rid=0x{rid:02x}"
    return f"{base}  [{b1:02x}]{('  tail: ' + extra) if extra else ''}"


def monitor(reader: JblStatusReader, seconds: float) -> None:
    print(f"monitoring {reader.path} for {seconds}s input reports (Ctrl+C stops)...")
    print("generate traffic: toggle ANC, mute mic, turn game/chat dial, power off/on")
    fd = reader._fd
    t0 = time.time()
    n = 0
    try:
        while time.time() - t0 < seconds:
            try:
                data = os.read(fd, 64)
            except BlockingIOError:
                time.sleep(0.02)
                continue
            except OSError:
                break
            if not data:
                continue
            n += 1
            ts = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d}"
            print(f"[{ts}] IN  {' '.join(f'{b:02x}' for b in data[:16])}  ->  {decode_event(data)}")
    except KeyboardInterrupt:
        pass
    print(f"\ncaptured {n} event packets")


KNOWN_FEATURE_RIDS = [0x07, 0x31, 0x47, 0x49, 0x4A, 0x50, 0x51, 0x5B, 0x5C,
                      0x61, 0x62, 0x63, 0x68, 0x71, 0x75]


def read_feature(reader: JblStatusReader, rid: int):
    return reader._get_feature(rid, 16)


def features(reader: JblStatusReader, seconds: float) -> None:
    print(f"polling feature reports on {reader.path} for {seconds}s (Ctrl+C stops)...")
    prev: dict[int, bytes] = {}
    t0 = time.time()
    try:
        while time.time() - t0 < seconds:
            cur: dict[int, bytes] = {}
            for rid in KNOWN_FEATURE_RIDS:
                data = read_feature(reader, rid)
                if data:
                    cur[rid] = data
            if not prev:
                for rid, d in sorted(cur.items()):
                    print(f"init 0x{rid:02x}: {' '.join(f'{b:02x}' for b in d[:16])}")
            else:
                for rid in sorted(cur):
                    if rid in prev and cur[rid] != prev[rid]:
                        diff = " ".join(
                            f"{i}:{a:02x}->{b:02x}"
                            for i, (a, b) in enumerate(zip(prev[rid], cur[rid]))
                            if a != b
                        )
                        print(f"CHG  0x{rid:02x}: {diff}")
            prev = cur
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


def scan(reader: JblStatusReader) -> None:
    print(f"GET_REPORT(Feature) sweep on {reader.path} (rid 0x01-0x77, read-only)...")
    for rid in range(0x01, 0x78):
        buf = bytearray(16)
        buf[0] = rid
        for i in range(1, 16):
            buf[i] = 0xA5
        try:
            n = fcntl.ioctl(reader._fd, _HIDIOCGFEATURE | (16 << 16), buf, True)
        except OSError:
            continue
        if n and n > 0:
            data = bytes(buf[:n])
            print(f"rid=0x{rid:02x} len={n:3d} data={' '.join(f'{b:02x}' for b in data)}")


def correlate(reader: JblStatusReader) -> None:
    """Guided: diff feature state + capture events around each manual action."""
    actions = [
        "power the headset OFF, wait 3s, power ON again",
        "toggle the ANC button (off -> on -> talk-through)",
        "mute and unmute the microphone",
        "turn the game/chat dial to full chat, then full game",
        "plug the USB-C charging cable in, then unplug it",
    ]
    prev: dict[int, bytes] = {}
    for rid in KNOWN_FEATURE_RIDS:
        data = read_feature(reader, rid)
        if data:
            prev[rid] = data
    for action in actions:
        input(f"\n>>> NOW: {action}\n    press ENTER when done...")
        # collect events for 2.5s after the action
        events = []
        t0 = time.time()
        while time.time() - t0 < 2.5:
            try:
                data = os.read(reader._fd, 64)
            except BlockingIOError:
                time.sleep(0.02)
                continue
            except OSError:
                break
            if data:
                events.append(data)
        for rid in KNOWN_FEATURE_RIDS:
            data = read_feature(reader, rid)
            if data and rid in prev and data != prev[rid]:
                diff = " ".join(
                    f"{i}:{a:02x}->{b:02x}"
                    for i, (a, b) in enumerate(zip(prev[rid], data))
                    if a != b
                )
                print(f"  feature 0x{rid:02x} CHANGED: {diff}")
            if data:
                prev[rid] = data
        if events:
            print(f"  events ({len(events)}):")
            for d in events[:12]:
                print(f"    {' '.join(f'{b:02x}' for b in d[:16])}  ->  {decode_event(d)}")
        else:
            print("  (no events captured)")


def main() -> int:
    ap = argparse.ArgumentParser(description="JBL Quantum 810/910 protocol probe")
    ap.add_argument("--monitor", nargs="?", const=30.0, default=None, type=float,
                    metavar="SEC", help="decode input-report events for SEC seconds")
    ap.add_argument("--features", nargs="?", const=15.0, default=None, type=float,
                    metavar="SEC", help="watch feature reports for changes, SEC seconds")
    ap.add_argument("--scan", action="store_true", help="one GET_REPORT feature sweep")
    ap.add_argument("--correlate", action="store_true",
                    help="guided action -> byte-change correlation")
    args = ap.parse_args()

    reader = JblStatusReader()
    if not reader.open():
        print("error: no JBL Quantum 810/910 hidraw device found", file=sys.stderr)
        return 1

    print(f"device: {reader._model}  node: {reader.path}  810={reader._is_810}")
    try:
        if args.scan:
            scan(reader)
        if args.correlate:
            correlate(reader)
        if args.features is not None:
            features(reader, args.features)
        if args.monitor is not None:
            monitor(reader, args.monitor)
        if not (args.scan or args.correlate
                or args.features is not None or args.monitor is not None):
            ap.print_help()
    finally:
        reader.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())