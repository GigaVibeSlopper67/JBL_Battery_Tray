# JBL Quantum 810/910 - HID Report Map

All values below were confirmed on a **Quantum 810 dongle (`0ecb:2069`, HID
interface 5)** by live GET_REPORT probing and by parsing the USB captures
attached to [HeadsetControl issue #357](https://github.com/Sapd/HeadsetControl/issues/357).
The Quantum 910 (`0ecb:2088`) shares the battery event (`0x08`) and its own
mute events (`0x2f`); everything else is 810-generation specific unless noted.

The vendor HID interface is USB interface **5** (the dongle also exposes
standard USB-audio interfaces 0-4). Access it via hidraw (see
`tools/find_hidraw.py`) - no pyusb claiming needed (claiming the interface
*destroys the hidraw node* until the dongle is replugged).

## Event reports (interrupt IN, pushed by the dongle)

First byte of the packet is the report ID.

| Report | Meaning | Payload |
|--------|---------|---------|
| `0x02` | ANC state | byte1: `00`=off, `01`=on, `02`=talk-through |
| `0x03` | Power-on marker | `03 00` (headset powered on) |
| `0x06` | Microphone | byte1: `00`=off (muted), `01`=on |
| `0x07` | Lights | byte1: `00`=off, `01`=on |
| `0x08` | Battery | byte1: percent 0..100 |
| `0x09` | Power-on marker | `09 01` (headset powered on) |
| `0x10` | Game/Chat mix | byte1: `00`=full chat ... `0x10`=full game (16 steps) |
| `0x2f` | Mute (910 only) | `02`=toggle mute, `00`=unmuted |

When the headset powers on, the dongle emits a full state burst:
`02, 03, 06, 07, 08 (x4), 09, 10` - this is the best way to (re)sync all
state at once.

Battery (`0x08`) is also pushed periodically (~every 2 s while the headset
is in use).

> **Hardware note:** the mic arm overrides the mute button. With the arm
> up (muted) the mute button does nothing - the state stays muted and no
> event is emitted. This is intended headset behavior, not a monitoring
> gap. Both mute sources (mic arm and mute button) feed the same
> `0x06`/`0x67` state.

## Feature reports (GET_REPORT - read-only)

| Report | Meaning | Notes |
|--------|---------|-------|
| `0x49` | Battery percent | `[0x49, percent]`; answers anytime (810) |
| `0x45` | **ANC state** | `[0x45, 0=off/1=on/2=tt]` - mirrors SET `0x46` / event `0x02` (verified live) |
| `0x4a` | **Lights state** | `[0x4a, 0=off/1=on]` - mirrors SET `0x4b` / event `0x07` (verified live) |
| `0x5c` | **Sidetone level** | `[0x5c, 0=off/1=low/2=mid/3=high]` - mirrors SET `0x5d` (verified live) |
| `0x62` | **Game/chat mix** | `[0x62, 0..16]` - mirrors event `0x10` (verified live) |
| `0x67` | **Mic state** | `[0x67, 1=on, 0=muted]` - mirrors event `0x06` (verified live) |
| `0x61` | Part/serial number | ASCII string, e.g. `MM0169-EM0015659` |
| `0x62`, `0x63`, `0x68` | More identity strings | variants of the same string |
| `0x51` | EQ-like data | 12 small values `01 03 02 00 03 02 01 00 02 01 03 02` (undecoded) |
| `0x5b` | Config data | structure like 0x51 (undecoded) |
| `0x71` | `[0x71, 01, 02, 00...]` | undecoded |
| `0x75` | `[0x75, 18, 02, 00...]` | undecoded |
| `0x07` (feature) | dynamic byte | byte1 fluctuates at runtime (0x0e, 0x07, 0x00 observed; undecoded) |
| `0x47`, `0x4a` (lower bytes), `0x50` | static info | `00 00 05 5c 03 00 80 2c` (undecoded) |

**Pattern:** for every SET command the read-back report is `SET id - 1`
(`0x46`→`0x45` ANC, `0x4b`→`0x4a` lights, `0x5d`→`0x5c` sidetone).

Note: on this device a GET_REPORT for an unknown report ID does not stall -
the firmware answers with the nearest known lower report. The kernel may
also leave stale tail bytes, so verify the echoed report ID before trusting
a response.

## Feature reports (SET_REPORT - CHANGES DEVICE STATE)

Payload is 2 bytes: `[report_id, value]`.

| Report | Command | Values |
|--------|---------|--------|
| `0x46` | ANC mode | `0`=off, `1`=on, `2`=talk-through |
| `0x4b` | Lights | `0`=off, `1`=on |
| `0x5d` | Sidetone | `0`=off, `1`=low, `2`=mid, `3`=high |

The Windows "QuantumENGINE" software sends exactly these as class
SET_REPORT(Feature) requests; on Linux the hidraw `HIDIOCSFEATURE` ioctl is
equivalent. Each accepted command is acknowledged by the matching event
report (`0x02` for ANC, `0x07` for lights).

### Lighting colors/effects (RGB) - reports 0x4c/0x4d

Decoded from the #357 captures and verified live on a Quantum 810
(2026-09) - see the full "Lighting (RGB)" section below.

## Lighting (RGB) - decoded and verified live

QuantumENGINE's lighting model: per lighting **element** (0 = logo,
1 = ring on the earcups) an effect (Breathing/Solid/Wave/Glitch) plays a
sequence of color **segments** whose interval distribution follows a
**tempo** slider. The software pushes it over HID feature reports:

| Report | Payload | Meaning |
|--------|---------|---------|
| `0x4c` | `[4c, element, tempo, segments]` | table header; tempo ∈ {`0x28`,`0x32`,`0x64`}; segments ∈ {2, 5} (never more than 5) |
| `0x4d` | `[4d, element, index, R, G, B, M, index*2]` | one color segment; **RGB = bytes 3-5** (verified: `ff0000` renders red, `00ff00` green, `0000ff` blue); `M` = interval/duration marker ∈ {`00`,`01`,`02`,`04`,`05`}; `index` ∈ 0..4; last byte = `index*2` (0..8) |
| `0x4b` | `[4b, 0/1]` | lights off/on (commit; already known) |

> **Safe value ranges** (from the original QuantumENGINE USB capture in
> `pcaps/`): segment count **2 or 5 only**, tempo **`0x28`/`0x32`/`0x64`**,
> frame index **0..4**, last byte **0..8**, and the `M` byte
> **`0x00`/`0x01`/`0x02`/`0x04`/`0x05`**. Segment counts above 5 (the old
> 16/32-segment "reset") wedge the lighting MCU into a strobe lockup. The
> tray and `tools/jbl_rgb.py` hard-clamp every value to these ranges.

### ⚠️ Deadlock warning - do NOT exceed the safe ranges

Writing a value **outside the ranges above can permanently deadlock the RGB
lighting** and is **not recoverable by factory reset or a normal power-off**:

- The lighting runs on a **separate MCU** that latches bad table values into
  a tight loop (the "absurd strobe") and then **ignores all further writes** -
  including from QuantumENGINE on Windows.
- The trigger observed in this project was a **segment count above 5** (a
  "clearing pass" of 16 or 32 segments). The extra frames pushed the `0x4d`
  index to 0..15/31 and the last byte to `0x1e`/`0x3e`, far outside the
  device's 0..4 / 0..8.
- Once wedged, a soft reset (power button, dongle replug, factory reset) does
  **not** clear it because none of those hard-cut power to the lighting MCU.
  A firmware update may also fail to complete. Recovery requires a true cold
  boot (full battery drain to zero, or physically disconnecting the battery)
  or a wired reflash - see `docs/RGB_SAFE_RANGES.md`.

**Rule for any implementation:** never emit a value that QuantumENGINE itself
does not emit. The safe set above is the complete observed set; treat
everything else as untested and potentially device-bricking.

Verified behavior (live on a Quantum 810 via hidraw):

- **Arming required**: the lighting SETs only take effect after the
  QuantumENGINE connect-time GET round (`0x68, 0x67, 0x62, 0x5c, 0x75,
  0x49, 0x51, 0x47, 0x4a, 0x45` in that order - from the QuantumENGINE
  capture in `pcaps/`). Without it the dongle
  still accepts and caches the SETs - the `0x4a` read-back even flips! -
  but the headset ignores them (no LED change, no `07` event). Arming
  persists for at least several minutes.
- **Apply cycle**: the table takes effect on the lights OFF->ON transition.
  Writes while the lights are on do not change the running effect; the
  dongle applies the cached table at the next off->on cycle.
- **ACKs**: `0x4b` toggles are ACKed by `0x07` events, but only on actual
  state changes (a redundant `4b 01` while already on produces no event).
- **Toggle vs table-write race** (live, 2026-09-17): a lighting write ends
  with its own lights-on commit, which silently re-lights the headset even
  when the user toggled the lights off during the write. The tray aborts an
  in-flight write when the lights are toggled off (checks between reports,
  never commits afterwards) so the toggle stays authoritative. Also seen
  once after a wedged 16-segment table: a `4b 00` was accepted without a
  `07` ACK and the `0x4a` read-back answered a 4-byte payload
  (`4a 00 00 02`) instead of the usual 2-byte `[4a, state]` - replug /
  power-cycle recovers the lighting controller.
- **Element mapping**: element 0 = logo, element 1 = ring (verified live
  with distinct colors per element).
- **No read-back**: GET on `0x4c`/`0x4d`/`0x4e` answers with the nearest
  known lower report (`0x61` serial, echo-ID mismatch) - the color table
  cannot be read back. QuantumENGINE also only ever pushes it.
- A solid color = 5 identical segments and renders as a breathing-style
  pulse (a true steady "Solid" encoding is still open, see below).
- **Color mixups diagnosed** (live, 2026-09-17): SETs fired back-to-back
  can be dropped outright (the ring's writes, last in the burst, went
  missing entirely) and partially delivered tables leave stale colors
  cycling (the factory table's index-2 segment is `ff 00 cc` = the "red
  residue" seen with white/blue; "yellow rendering white" is the new
  yellow blended with a stale blue residue). Remedy used by the tray and
  `tools/jbl_rgb.py`: pace every SET (`--delay`, tray `LIGHT_SET_DELAY`)
  and clear the table before the final table (two passes: clearing frames
  first, then the QuantumENGINE-shape table).
- **Segment count = pulse tempo** (live, 2026-09-17): the `0x4c` segment
  count sets how many segments share the tempo cycle - a 16-segment table
  pulsed visibly "super fast" and later wedged the lighting MCU into a
  strobe. The capture confirms QuantumENGINE only ever sends 2 or 5
  segments, so every write (clearing pass included) is now hard-clamped to
  `1..5` (tray `LIGHT_MAX_SEGMENTS`, CLI `MAX_SEGMENTS`); the final table
  stays at the stock 5.

Open questions (not yet decoded):

- Exact meaning of the `M` byte (interval length in tempo units?). The
  `0x4c` 4th byte behaves as the segment count: the played segments share
  the tempo cycle (live: 5 = stock pulse). Whether it can also act as an
  effect ID is still open - but values above 5 wedge the MCU, so any
  experiment must stay within 1..5.
- How "Solid"/"Wave"/"Glitch" effects are encoded (other header values,
  other reports, or tempo `0x00`?).
- The minimal arming GET (the full round is used as the safe recipe).

### Controlling the lighting from Linux

Both implementations arm automatically (the GET round above), then write
the per-element table and toggle the lights to trigger the off->on apply
cycle. Three guards fix the color mixups (diagnosed live, 2026-09-17):
every SET_REPORT is paced (~10 ms - back-to-back writes were dropped, the
ring's writes went missing entirely); a clearing pass overwrites the whole
table (identical segments per element - stale colors from earlier writes
otherwise keep cycling); and every value is hard-clamped to the safe ranges
derived from the QuantumENGINE capture (segments 1..5, tempo 0x28/0x32/0x64,
M 0x00/0x01/0x02/0x04/0x05). The tray runs the whole sequence on a worker
thread so the UI never blocks; it skips re-arming while fresh
(`LIGHT_ARM_TTL`, 60 s) and coalesces rapid color clicks (newest color wins):

- **Tray** (`--enable-controls`): menu -> Lighting -> "Pick color…" (GTK
  color chooser) or the presets Red/Green/Blue/White/Teal (factory).
  Applies one color to both elements (logo + ring) as a paced two-pass
  write (`LIGHT_RESET_SEGMENTS` + `LIGHT_SEGMENTS`, `LIGHT_SET_DELAY`).
- **CLI** `tools/jbl_rgb.py`:
  - `--status` - read-only probe (state + `0x4c`/`0x4d`/`0x4e` GET attempts)
  - `--solid RRGGBB [--element logo|ring|both]` - clearing pass plus one
    color as `--segments` identical segments (breathing-style effect)
  - `--default` - replay the factory teal table (`33 ff cc`, tempo `0x64`)
  - `--reset-segments N` - clearing pass before the final table (default 5,
    clamped to 1..5; 0 disables - wipes stale colors of earlier writes)
  - `--segments N` - final table segments per element (default 5, clamped
    to 1..5 - QuantumENGINE never sends more than 5)
  - `--speed N` - override the `0x4c` tempo byte (default `0x64`; clamped to
    `0x28`/`0x32`/`0x64`)
  - `--mode N` - override the `0x4d` M byte (default `0x02` logo / `0x05`
    ring; clamped to `0x00`/`0x01`/`0x02`/`0x04`/`0x05`)
  - `--delay SEC` - pause between SET reports (default 0.02; raise it if
    writes are still dropped)
  - `--lights on|off|keep` - lights state after the write (default `keep`)
  - `--listen SEC` - seconds to listen for `0x07` ACK events after a SET
  - `--raw "4c 00 64 05;4d 00 00 ff 00 00 02 00"` - send raw feature reports
    (**NOT clamped** - bypasses every safety guard and can wedge the lighting
    MCU; use only with values from the safe-ranges table above)

## What is NOT (yet) monitorable

- **Charging state**: verified empirically - while the headset was charging
  (battery climbing 65->70%), no event or feature report changed except the
  battery value itself. The `0x08` battery packets carry no charging flag.
  The dongle simply does not expose charging state over HID.
- **Spatial sound / DTS**: seen in captures only as SET_REPORTs without an
  event echo; not decoded.
- **Head tracking**: only the newer Quantum 950 generation (event `0x86...`
  protocol, IMU data `0x1a`); the 810/910 do not have head tracking.

## Tools using this map

- `tools/jbl_status.py` - status reader + controls CLI (`--json`, `--watch`,
  `--set-anc`, `--set-lights`, `--set-sidetone`)
- `tools/jbl_rgb.py` - RGB lighting CLI (`--status` read-only probe,
  `--solid RRGGBB [--element logo|ring|both]`, `--default` factory table,
  `--raw` hex sequences, `--speed`/`--mode` tuning overrides,
  `--lights on|off|keep`, `--listen SEC`; arms automatically before writes)
- `tools/jbl_status_probe.py` - live protocol probe (`--monitor`, `--features`,
  `--scan`, `--correlate`)
- `jbl_quantum910_tray.py` - tray shows ANC/mic/mix/lights/sidetone/serial
  plus a battery drain estimate; menu controls behind `--enable-controls`
  (ANC cycle, lights toggle, sidetone radio group) including a **Lighting**
  submenu with a color picker and presets (breathing effect)