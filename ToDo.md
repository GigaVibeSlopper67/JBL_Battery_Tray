Observations with the LED:
- When I use the light change Feature it turns the light off. When I turn it back on it is lit up again in the chosen color but i am getting mix ups over time like described in the following points.
- The option to turn it white does only make the logo white. And it cycles through red, and it doesn't affect ring color.
- Setting it to color blue makes the Color cycle through blue and red
- The option to turn it red has a last second of blue in it.
- Picking a color like yellow actually creates white.
- My Asumption: The JBL headset has some weird color Palette.
- Seting to Factory Teal doesn't seem to cxhange the colors.
- The "Pick a color" feature only affects the Logo and not the Ring.
    - Also the color seems to added to the sequence with residue of the previous color. 

For the color management: I am assuming that something in the implementation is mixing up the colors.
Would resetting the colors before each change maybe fix these mixups?

---

Diagnosis (2026-09-17, from the observations above) - implemented in the tray and `tools/jbl_rgb.py`:

- Not a weird device palette and not a GTK picker bug (the picker converts
  0-1 floats to 0-255 bytes correctly). Two real causes in the write path:
  1. **Dropped writes**: all 14 SET_REPORTs (arm -> 4b 00 -> 6 reports per
     zone -> 4b 01) were sent back-to-back with no pacing. The ring's
     reports are the LAST in the burst and were dropped entirely - that is
     why "Pick a color" only ever changed the logo. Partially dropped logo
     frames also leave stale segments in the running effect.
  2. **Stale segments (the "residue")**: the device's color table holds
     more than the 5 segments we write, so old colors keep cycling. The
     factory table itself contains a red/magenta segment at index 2
     (`ff 00 cc`) - that is the "red" residue seen with white/blue.
     "Yellow -> white" is the new yellow (255,255,0) blended with a stale
     blue (0,0,255) residue.
- Fix implemented: every color change now (a) paces each SET_REPORT by
  ~20 ms (`LIGHT_SET_DELAY` / `--delay`) and (b) overwrites the whole
  table with 16 identical segments per element (`LIGHT_RESET_SEGMENTS` /
  `--segments 16`) - i.e. the "reset the colors before each change" idea,
  done by overwriting (no separate clear report is known; `0x4c`/`0x4d`
  have no read-back either).
- Verify with `tools/jbl_rgb.py`: blue -> red (no blue tail), yellow
  (stays yellow, no white), `--element ring --solid 00ff00` (ring must
  change), `--default --lights on` (factory teal restored).

---

Round 2 (2026-09-17, after the live test):
- Colors now apply correctly (white worked, the ring is reachable) - the
  pacing fixed the dropped-write side. Two follow-ups from that test:
  - The 16-segment table pulsed "super fast": the `0x4c` segment count
    sets how many segments share the tempo cycle - higher count = faster
    pulse. The write is now TWO passes: a clearing pass (16 identical
    frames, wipes stale colors) followed by the final QuantumENGINE-shape
    table (5 frames = stock pulse tempo). CLI knobs: `--reset-segments`
    (clear pass) / `--segments` (final table, default 5).
  - The paced writes blocked the GTK main loop (tray felt "very slow"/
    froze): the lighting write now runs in a background worker thread
    (busy-guarded, renders via `GLib.idle_add`).
- Open: a slight teal residue was still visible in white - if it comes
  back, widen the clearing pass (`--reset-segments 32`) to find the
  device's real table size.

---

Round 3 (2026-09-17, "very slow" clarified = latency until the lighting reacts):
- Cause: every change re-ran the 12-GET arming round plus 48 paced SETs
  (20 ms each) -> ~1.5 s until the commit. Fixes:
  - the arming round is skipped while fresh (`LIGHT_ARM_TTL` = 60 s; the
    armed state persists for several minutes - verified earlier),
  - the per-SET pause is 10 ms (tray: `--lighting-delay`, CLI: `--delay`),
  - rapid menu clicks are coalesced: the newest color is queued and
    applied right after the in-flight write (nothing is dropped).
- Expected reaction time now ~0.5 s per change. If color mixing ever
  reappears at 10 ms, raise the delay back to 0.02 - dropped writes are
  worse than latency.

---

Round 4 (2026-09-17, "turn off doesn't register" + rapid flashing):
- The rapid flashing = the device was still playing a 16-slot table from
  the earlier single-pass writes (tempo cycle divided over 16 segments).
- The lights toggle could lose a race: an in-flight lighting write ends
  with its own lights-on commit, silently re-lighting the headset after a
  toggle. Fixed: "Lights: toggle" now aborts an in-flight write (the
  toggle is authoritative; a later color pick re-enables the write) and
  logs the `0x4a` read-back after every toggle.
- Live device state during the diagnosis: `4b 00` accepted but no `0x07`
  ACK; `0x4a` answered `4a 00 00 02` (4-byte payload, dongle view = off).
  Factory table re-written (clear pass + final 5-segment pass), lights
  left off - the next lights-on applies stock teal at stock tempo.
- Headset power-off: hold the power button ~10 s. If unresponsive, replug
  the dongle first (resets the lighting pipeline and the arming state),
  then hold power again. Sound/charging working = core firmware is fine;
  the lighting controller recovers on replug. QuantumENGINE on Windows
  can always restore the lighting defaults.
- QuantumENGINE could NOT control the lights either while the headset was
  wedged (installed on a Windows system) - the lighting MCU ignores
  everything until a dongle replug / headset power cycle. Note: an active
  dongle (QuantumENGINE polling or our GET polling) can wake/keep the
  headset alive - to power it off, unplug the dongle first, then hold
  power 15-30 s.