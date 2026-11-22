# BPControl M1E — First reversible control: evidence and safety gates

## Starting point: M1D validated by operator

The user supplied the full console output of the offline M1D audit
for the 2026-11-22 BP1032 snapshot:

- **59/59** effects successfully read, `complete=true`, no read errors.
- **845** raw 16-bit parameter words saved.
- **6/6** known evidence-graded effect schemas match field counts;
  `Pro Reverb` still contains inferred field labels.
- **53** instances are currently `raw_only` (INI names are unverified hints).
- **0** field-count discrepancies relative to `ACPWorkbench.ini`.
- **0** M1D structural audit errors and **0** warnings.

These are results from the user's terminal output. The exact raw JSON
snapshot remains local and has **not** been independently reviewed in this
repository. Structural integrity **does not** establish safe writes to the
845 fields.

## Proposed first change

Use Guitar Chorus, instance #15, ACP command `0x8F`, field #6
(`wet`). This individual field was already changed and read back with
ACPWorkbench in the source logs `Texto colado(20261122-010029).txt`.
The protocol's single-field write is:

```text
A5 5A 8F 03 06 LL HH 16
```

where `LL HH` is the **signed 16-bit little-endian** target wet value.
Existing evidence demonstrates non-persistent ACP effect parameter writes
and the **application-level single-byte ACK** `8F` in ACPWorkbench logs.

The evidence DOES NOT yet establish exactly how the 1-byte ACK is
encapsulated in a Windows 256-byte HID `GET_REPORT` payload. The
`usb_snapshot.py` transaction/parser currently expects a complete ACP
readback frame and must **not** be reused for writes without adapting to
the confirmed ACK envelope. The earlier USBPcap trace intentionally
contained read requests only. Therefore **no live write support is
enabled in BPControl M1E at this point**.

## Offline preflight tool (implemented)

```powershell
git pull
py -m unittest discover -s tests -v
py tools/plan_chorus_probe.py artifacts/snapshots/bp1032-01.json
```

It checks that:
- the saved snapshot came from a full live 59-effect capture;
- the M1D structural audit has no errors/warnings;
- the firmware type and versions match the known source catalog;
- Chorus field #6 is specifically mapped as `wet`, `write_readback`,
  percentage, with exactly seven observed fields;
- its saved value is within `0..100`.

The proposal **only prints** a change of **one raw unit** (e.g. if the
saved value is 80, candidate 79, rollback 80) and their exact ACP
application-layer bytes. It **never opens USB**, calls HID, sends
commands, starts ACPWorkbench, or edits the JSON file.

Example *hypothetical* offline proposal when Chorus wet=80:

```text
Read ACP:       A5 5A 8F 00 16
Proposed write: A5 5A 8F 03 06 4F 00 16
Rollback:       A5 5A 8F 03 06 50 00 16
```

This is not confirmation the board has 80% wet **right now**:
snapshot data may be stale. Do not transmit these bytes from a generic
USB console.

## Required next observation: ONE legitimate ACPWorkbench parameter change

With **BPControl closed**, audio muted, Wireshark/USBPcap available, and
ACPWorkbench open, capture exactly this controlled experiment:

1. Read the **current** Guitar Chorus wet setting and record it.
2. Adjust the wet setting by **one unit** (preferably a decrease) in
   ACPWorkbench. Record exact original and new value.
3. Observe `SET_REPORT` on `MI_04` and the next `GET_REPORT`:
   the command framing, `wValue`, `wIndex`, report size, Report ID,
   first 32 bytes of USB data, zero padding, and ACK presence/position.
4. Confirm the change with ACPWorkbench's readback if available.
5. **Restore original wet value in ACPWorkbench**, confirm it in the UI,
   then stop the capture. Ensure no unintentional permanent save was used.
6. If something looks abnormal or the USB session disconnects, do not
   improvise more commands. Reopen ACPWorkbench and verify state safely.

Only share **filtered, sanitized** `1235:0003` records. Do not publish
the full USBPcap root-hub capture or unrelated USB traffic.

A local agent may automate start/stop/filter/report, but it should not
independently drag GUI sliders or send parameter writes unless its plan
is specifically approved. The operator should perform and then undo
the one step.

## M1E implementation acceptance gates for an eventual live writer

- Validate ACK report's actual Windows HID format from physical capture.
- Require user opt-in **per transaction**, never any implicit writes.
- Lock to exact USB identity and exact firmware `0x30/0.3.0/2.24.0`.
- Restrict to Chorus #15, wet field #6, integer 0..100 and max **1-step**.
- Read exact current values just before writing; compare with explicit
  expectation, fail closed on discrepancy.
- Save original 7-value in-process snapshot; send at most one write.
- Verify ACK *and* immediate full readback. ACK alone is not proof.
- Restore original value even on readback mismatch, where USB still works.
- Verify full readback restores every field; if restoration fails,
  explicitly report uncertainty and stop; no false "rollback succeeded".
- No automatic retries or speculative writes; enforce parent-side
  timeout and cleanup of HID handles.
- Never permit `0xFD` flash save, `0xFE` firmware upgrade, reset,
  `0x01` system control, or writes to arbitrary effects and fields.
- No continuous slider updates, MIDI writes, presets or auto-save at
  this milestone.

**No further write capability is shipped or activated by this document.**

## Passive ACK analyzer implemented

The follow-up preparation includes a bounded USBPcap capture scenario and
`tools/analyze_chorus_write_ack.py`, tested against synthetic USBPcap URBs.
No direct device write was added. Follow the step-by-step procedure in
[M1E_USB_ACK_CAPTURE.md](M1E_USB_ACK_CAPTURE.md) before creating a live writer.
