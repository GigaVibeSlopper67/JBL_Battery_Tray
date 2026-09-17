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
| `0x4c` | `[4c, element, tempo, segments]` | table header; tempo seen: `0x32`/`0x64` (slider 50/100); segments = 5 |
| `0x4d` | `[4d, element, index, R, G, B, M, index*2]` | one color segment; **RGB = bytes 3-5** (verified: `ff0000` renders red, `00ff00` green, `0000ff` blue); `M` = interval/duration marker (`00/02/04/05` seen; `05` pulses visibly longer than `02`); last byte = `index*2` |
| `0x4b` | `[4b, 0/1]` | lights off/on (commit; already known) |

Verified behavior (live on a Quantum 810 via hidraw):

- **Arming required**: the lighting SETs only take effect after the
  QuantumENGINE connect-time GET round (`0x50, 0x68, 0x51, 0x45, 0x67,
  0x5c, 0x62, 0x49, 0x47, 0x4a, 0x5b` in that order). Without it the dongle
  still accepts and caches the SETs - the `0x4a` read-back even flips! -
  but the headset ignores them (no LED change, no `07` event). Arming
  persists for at least several minutes.
- **Apply cycle**: the table takes effect on the lights OFF->ON transition.
  Writes while the lights are on do not change the running effect; the
  dongle applies the cached table at the next off->on cycle.
- **ACKs**: `0x4b` toggles are ACKed by `0x07` events, but only on actual
  state changes (a redundant `4b 01` while already on produces no event).
- **Element mapping**: element 0 = logo, element 1 = ring (verified live
  with distinct colors per element).
- **No read-back**: GET on `0x4c`/`0x4d`/`0x4e` answers with the nearest
  known lower report (`0x61` serial, echo-ID mismatch) - the color table
  cannot be read back. QuantumENGINE also only ever pushes it.
- A solid color = 5 identical segments and renders as a breathing-style
  pulse (a true steady "Solid" encoding is still open, see below).

Open questions (not yet decoded):

- Exact meaning of the `M` byte (interval length in tempo units?) and of
  the `0x4c` 4th byte (segment count vs effect ID - `01`/`04` variants
  were tried with unclear results).
- How "Solid"/"Wave"/"Glitch" effects are encoded (other header values,
  other reports, or tempo `0x00`?).
- Why later table writes only partially replace segments (colors from
  older writes can persist in the cycle) - possibly a rolling segment
  queue rather than a fixed table.
- The minimal arming GET (the full round is used as the safe recipe).

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
  `--raw` hex sequences; arms automatically before writes)
- `tools/jbl_status_probe.py` - live protocol probe (`--monitor`, `--features`,
  `--scan`, `--correlate`)
- `jbl_quantum910_tray.py` - tray shows ANC/mic/mix/lights/sidetone/serial
  plus a battery drain estimate; menu controls behind `--enable-controls`,
  including a Lighting color picker (breathing effect)