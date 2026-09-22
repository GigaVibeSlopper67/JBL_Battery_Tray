# JBL Quantum 810 RGB lighting - safe value ranges & deadlock finding

> Portable reference for anyone implementing Quantum 810 lighting control
> (HeadsetControl, OpenRGB, this project, etc.). Read this before writing
> **any** `0x4c`/`0x4d`/`0x4b` feature report to the device.

## Scope

- **Device**: JBL Quantum 810 wireless headset, USB dongle `0ecb:2069`
  (HID interface 5). The Quantum 910 (`0ecb:2088`) shares the battery/mute
  events but its lighting is not covered here.
- **Source of truth**: the original **QuantumENGINE** software captured on
  Windows (USBPcap, link-type 249) - `pcaps/jbl quantum 810 - Initial first
  cap - just random setting changes.pcapng`.

## The lighting protocol (what is actually sent)

Per lighting **element** (`0` = logo, `1` = ring on the earcups) an effect
plays a sequence of color **segments**. It is pushed over HID feature reports:

| Report | Payload | Field | Meaning |
|--------|---------|-------|---------|
| `0x4c` | `[4c, element, tempo, segments]` | element | `0` logo / `1` ring |
| | | tempo | effect speed slider |
| | | segments | number of `0x4d` frames that follow |
| `0x4d` | `[4d, element, index, R, G, B, M, index*2]` | index | 0-based frame number |
| | | R,G,B | color (bytes 3-5) |
| | | M | interval/duration marker |
| | | last byte | `index*2` |
| `0x4b` | `[4b, 0/1]` | — | lights off/on (the commit) |

Required sequence, in order:

1. **Arm** - GET the connect-time round `0x68, 0x67, 0x62, 0x5c, 0x75, 0x49,
   0x51, 0x47, 0x4a, 0x45`. Without it the dongle caches the SETs but the
   headset ignores them (no LED change). Arming persists for minutes.
2. **Write** the per-element table (`0x4c` header + N × `0x4d` frames).
3. **Commit** via a lights **off → on** transition (`0x4b 00` then `0x4b 01`);
   the table only applies on that transition.

A solid color is expressed as **5 identical segments** and renders as a
breathing-style pulse.

## The safe value ranges (complete observed set)

These are the **only** values QuantumENGINE was observed to emit. Treat every
other value as untested and potentially device-bricking.

| Field | Safe range |
|-------|------------|
| `0x4c` segment count | **2 or 5** (never more than 5) |
| `0x4c` tempo byte | **`0x28` / `0x32` / `0x64`** |
| `0x4d` element | **0 or 1** |
| `0x4d` frame index | **0–4** |
| `0x4d` R / G / B | **0x00–0xFF** (any byte is fine) |
| `0x4d` M byte | **`0x00` / `0x01` / `0x02` / `0x04` / `0x05`** |
| `0x4d` last byte | **0–8** (`index*2`) |

> The last byte and the index are implied by the segment count: with
> `segments <= 5`, `index` stays 0..4 and `index*2` stays 0..8. The dangerous
> values only appear once `segments > 5`.

## ⚠️ The deadlock finding (why RGB can get "bricked")

Writing a value **outside the safe ranges can permanently deadlock the RGB
lighting**, and it is **not recoverable by factory reset or a normal
power-off**.

What happens, step by step:

1. The lighting runs on a **separate MCU** from the audio/battery MCU.
2. A bad table value (observed: a segment count of **16 or 32**, from a
   "clearing pass" intended to wipe stale colors) latches the lighting MCU
   into a tight loop - the "absurd strobe".
3. The extra frames pushed `0x4d` index to 0..15/31 and the last byte to
   `0x1e`/`0x3e`, far outside the device's 0..4 / 0..8.
4. Once wedged, the lighting MCU **ignores all further writes**, including
   from QuantumENGINE on Windows. A factory reset does not help (it doesn't
   touch the lighting config), and a firmware update may fail to complete
   because the headset re-applies the corrupt table during the boot/handshake.
5. A **soft** power-off (button, dongle replug) does not clear it because the
   power button is handled by the *main* MCU and never hard-cuts power to the
   *lighting* MCU.

### Recovery (best → most invasive)

1. **True cold boot via full battery drain** - unplug the dongle (so its
   polling can't keep the headset awake), power the headset on, and leave it
   until the battery is completely empty (all LEDs dead). Charge, power on,
   then retry the firmware update.
2. **Wired USB-C reflash** - connect wired and force a full firmware
   *reinstall* (not "update") via QuantumENGINE; a full reflash reinitializes
   the lighting MCU.
3. **Physical battery disconnect** - open an earcup and unplug the battery
   connector ~30 s. Definitive, but voids warranty.
4. **RMA** - a firmware value that bricks the lighting against a factory reset
   is a JBL firmware bug; the capture is strong evidence for a warranty claim.

### Rules for implementers

- **Never emit a value QuantumENGINE does not emit.** The table above is the
  complete observed set.
- **Hard-clamp** segment count to `1..5`, tempo to `0x28/0x32/0x64`, and the M
  byte to `0x00/0x01/0x02/0x04/0x05` *before* building any report - never rely
  on the caller.
- A raw/"unsafe" escape hatch (e.g. `--raw`) must be clearly marked as capable
  of bricking the lighting and should not be exposed in normal UI paths.
- Prefer **writing 5 segments** (the stock shape). A single correctly-paced
  5-segment write fully overwrites the 5-slot table; there is no need for a
  larger "clearing pass" - that larger pass is exactly what caused the lockup.

## Raw SET_REPORT payloads observed (for reference)

The factory table QuantumENGINE pushes on connect (teal, tempo `0x64`):

```
4c 00 64 05
4d 00 00 33 ff cc 02 00
4d 00 01 33 ff cc 02 02
4d 00 02 ff 00 cc 02 04
4d 00 03 33 ff cc 02 06
4d 00 04 33 ff cc 02 08
4c 01 64 05
4d 01 00 33 ff cc 05 00
4d 01 01 33 ff cc 05 02
4d 01 02 ff 00 cc 05 04
4d 01 03 33 ff cc 05 06
4d 01 04 33 ff cc 05 08
4b 01
```

Note the index-2 segment `ff 00 cc` (magenta) is part of the **factory**
table - it is *not* residue from a bad write, and it shows through whenever a
write drops/leaves that slot stale.
