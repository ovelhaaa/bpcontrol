# BPControl

**BPControl** is an experimental, evidence-based controller toolkit for MVSilicon BP10xx DSP boards, initially targeting **BP1032** with the observed `HunXiang_F` firmware.

> **Status: M1F physically verified for Windows Chorus wet WRITE/READBACK/RESTORE (2026-11-22); M1G editor prototype implemented, offline tested, pending physical validation.** Owner-reported success `READ OK: 0x8F`, raw values `[1,20,10,200,50,80,80]`, matching passive capture. Firmware/status one-shot reads are also verified on the physical BP1032; CPU usage unit is MCPS as defined by the ACPWorkbench manual. This toolkit neither replaces DSP firmware nor processes audio.

## Goals

- Document real ACPWorkbench protocol traces and effect parameters without reflashing the board.
- Build safe, readback-verified Windows USB control, then an editor and presets.
- Port the control layer to ESP32-S3 USB Host, integrating MIDI, knobs, and optional web UI.

## Observed effects

| Effect | Index | ACP command |
|---|---:|---|
| Mic Echo | 10 | `0x8A` |
| Mic Pro Reverb | 13 | `0x8D` |
| Guitar PingPong | 14 | `0x8E` |
| Guitar Chorus | 15 | `0x8F` |
| Music Pitch Shifter Pro | 20 | `0x94` |
| Music Delay | 28 | `0x9C` |

These IDs are **specific to the tested firmware**, not universal mappings across BP10xx boards. Pro Reverb's individual field labels remain partly provisional.

## Quick start (offline — safe)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m unittest discover -s tests -v
bpcontrol effects
bpcontrol read guitar_chorus
bpcontrol write guitar_chorus modulation_rate 100
bpcontrol decode "A5 5A 8F 0F FF 01 00 07 00 05 00 64 00 19 00 50 00 5A 00 16"
```

The offline CLI `read` and `write` commands **print ACP packets; they DO NOT send anything to hardware**. The specific separate Windows live-read scripts below use the verified HID transport (MI_04, report ID 0, 256-byte USB reports).

## Structure

- `src/bpcontrol/acp.py`: ACP framing and field encoding/decoding
- `src/bpcontrol/effects.py`: effect schemas, guarded fields and conversions
- `src/bpcontrol/cli.py`: offline ACP inspector CLI
- `data/effects.json`: machine-readable schemas with evidence grades
- `docs/`: protocol notes, source observations, USB discovery gaps, roadmap
- `tests/`: unit tests based on observed ACP examples

## Safety and provenance

Do not flash firmware, probe unknown report IDs, issue speculative writes, or connect ACPWorkbench and BPControl concurrently. A one-byte write ACK is not proof of permanence across restart. Always confirm state via readback; Max Delay and unknown fields remain read-only until tested.

Observed RAM for Guitar PingPong (base 65 KB): Normal 70/78/91/116 KB and HQ 82/108/151/237 KB for 100/250/500/1000 ms buffers respectively; measured CPU consumption was approximately insensitive to buffer size. This does not reveal exact buffer format or per-algorithm resource costs.

## License

Not selected yet — repository owner to choose before accepting outside contributions.

## Windows M1A — first one-shot hardware read (operator opt-in)

The owner's 2026-11-22 USBPcap report established HID `MI_04`, control EP0,
SET_REPORT Output / GET_REPORT Input, report ID 0, and 256-byte zero-padded
ACP frames. The Windows HID APIs use 257-byte buffers including a leading ID
selection byte. See [USB_CAPTURE_REPORT.md](docs/USB_CAPTURE_REPORT.md) and
[M1_WINDOWS_FIRST_READ.md](docs/M1_WINDOWS_FIRST_READ.md).

Offline tests:

```powershell
py -m pip install -e .
py -m unittest discover -s tests -v
```

**Only after closing ACPWorkbench**, if you expressly want to send one
non-mutating read query to the BP1032 (no parameter writes):

```powershell
py -m pip install hidapi
py tools/read_chorus_windows.py --live-read-chorus
```

This **actively transmits one ACP read request** in a HID SET_REPORT.
Do not confuse that transport operation with modifying effects. It does
not save to flash, reset, install drivers or retry automatically. The runner
has a parent-side 4-second timeout. Report any error instead of retrying blindly.

GitHub Actions runs the offline test suite on Windows and Linux. CI success
is not a substitute for testing the physical BP1032.

## M1A — Firmware/status one-shot probes (experimental)

The physical Windows Chorus, firmware and status reads all succeeded. The decoding uses MVSilicon protocol v2.40.0 and ACPWorkbench manual §8.1 for MCPS. See `src/bpcontrol/usb_read_only.py`.
The only permitted ACP requests are empty-payload `0x00` and `0x02`.
They use the same Win32 HID Report ID 0 / EP0 scheme and 4-second subprocess
limit as the successful Chorus reader. They print raw reply payload bytes
rather than interpreting unverified runtime telemetry.

```powershell
git pull
py -m pip install -e .
py -m unittest discover -s tests -v
# Close ACPWorkbench; one active read per invocation:
py tools/read_info_windows.py --live-read-firmware
py tools/read_info_windows.py --live-read-status
```

Both scripts have no device access by default, no ACP parameter writes, no
flash persistence, no retries, and an explicit command allowlist. If either
fails, retain the error output and do not automatically repeat.

## M1A physical device status

The owner verified all three read-only commands on 2026-11-22: Chorus `0x8F`, firmware `0x00`, and status `0x02`. Confirmed firmware `0.3.0`, effects library `2.24.0`, RAM `70/320 KB`, **CPU `26 MCPS`**. Manual §8.1 defines MCPS as *mega cycles per second*, not MIPS; relative to the reported 320 MHz maximum, 26 MCPS is 8.1% of nominal cycle capacity, **not a guaranteed instantaneous CPU-utilization metric**. See [M1_PHYSICAL_FIRMWARE_STATUS.md](docs/M1_PHYSICAL_FIRMWARE_STATUS.md).

## M1C — 59 effects + offline explorer (NEW)

The `ACPWorkbench.ini` export identifies **59 distinct instances**, with
commands `0x81..0xBB`, each with its own name, type ID and parameter-name
**hints**. They are catalogued in [`data/effect_instances.json`](data/effect_instances.json).
INI values are **not live measurements**. The UI never fabricates values for
unread effects or treats unverified field names as measured.

The owner reported the **59-effect batch and offline HTML worked on the physical BP1032** on 2026-11-22. The actual JSON has not yet been independently inspected. It uses the same
HID MI_04 EP0 transport proven by individual reads, with a strict firmware
allowlist (`0x30` / `0.3.0` / effects `2.24.0`), one read per instance,
45-second supervisor timeout, no retry, and hard stop on a malformed reply.

Try the offline UI first (only previously measured Chorus, firmware and
status shown; 58 effects explicitly unread):

```powershell
cd C:\\progs\\bpcontrol
git pull
py -m pip install -e .
py -m unittest discover -s tests -v
py tools/render_snapshot.py data/demo_snapshot.json --open
```

Then, **with ACPWorkbench closed** and only when you choose to test the batch:

```powershell
py tools/snapshot_windows.py --live-read-all --output artifacts/snapshots/bp1032-01.json
py tools/render_snapshot.py artifacts/snapshots/bp1032-01.json --open
```

The collector generates a local JSON file; the renderer generates a standalone
HTML report (no web service, no USB calls from the browser). No effects are
modified or saved, and `artifacts/` is excluded from Git. If the collector
stops at an unexpected effect response, **do not rerun automatically**;
inspect the partial JSON and the reported index.

Full procedure: [`docs/M1C_59_EFFECT_SNAPSHOT.md`](docs/M1C_59_EFFECT_SNAPSHOT.md).

## M1D — Audit the 59-effect snapshot (NO USB)

If your local batch completed, audit the same saved JSON; do not query the
board again merely for this stage.

```powershell
cd C:\\progs\\bpcontrol
git pull
py tools/audit_snapshot.py artifacts/snapshots/bp1032-01.json
py tools/audit_snapshot.py artifacts/snapshots/bp1032-01.json --table
py tools/audit_snapshot.py artifacts/snapshots/bp1032-01.json --json > artifacts/snapshots/bp1032-01-audit.json
```

This checks all 59 instance IDs/commands, firmware compatibility, per-instance
field counts versus INI hints, raw ACP bytes versus signed/unsigned values, and
separates known schemas from inferred names or raw-only fields. No edits are
unlocked by a passing audit. See
[`docs/M1D_SNAPSHOT_AUDIT.md`](docs/M1D_SNAPSHOT_AUDIT.md).

## M1D audit passed; M1E write preparation (NO LIVE WRITES)

The owner-reported 2026-11-22 audit on the physical BP1032 snapshot shows
**59/59 effect readbacks, 845 signed/unsigned raw words, 6/6 studied schemas
matching field counts, 53 raw-only instances, zero field-count mismatches,
zero audit errors or warnings**. This structural pass does not validate
musical units, parameter ranges or the safety of effect writes. The full
snapshot JSON has not been independently reviewed in this repository.

A new, intentionally **offline-only** script builds a proposal for one
reversible Guitar Chorus wet adjustment (maximum 1 raw unit) without
opening HID or communicating with the board:

```powershell
cd C:\\progs\\bpcontrol
git pull
py tools/plan_chorus_probe.py artifacts/snapshots/bp1032-01.json
```

The user or local agent must first capture a legitimate ACPWorkbench
single-field write with USBPcap to establish the **actual HID ACK envelope**.
Only then should we implement and explicitly authorize a supervised live
write/readback/restore experiment. No live writes are enabled yet.
See [M1E preparation](docs/M1E_FIRST_WRITE_PREPARATION.md).

## M1E USB write ACK evidence (passive only)

BPControl still cannot change DSP parameters. An offline USBPcap analyzer can
inspect one **operator-driven ACPWorkbench** Chorus wet change and restoration,
including the actual HID `GET_REPORT` ACK envelope. The utility only reads
local PCAP files.

In an **administrator** PowerShell, with BPControl HID tools closed:

```powershell
git pull
py tools/capture_usb_passive.py --scenario chorus-wet-ack --seconds 60 --output artifacts/usb-capture/chorus-wet-01.pcapng
```

During the capture, open ACPWorkbench, read the current Chorus wet value,
move it by 1 point, read back, restore the original, and read back again.
Do not save to flash or update firmware. Then analyze offline:

```powershell
py tools/analyze_chorus_write_ack.py artifacts/usb-capture/chorus-wet-01.pcapng --output artifacts/usb-capture/chorus-wet-01-ack.json
```

The script prints wet write values, matching `GET_REPORT` packet positions,
ACK shapes, and whether there is a *post-restoration readback*. If any part
is missing, do not assume a successful rollback. See
[`docs/M1E_USB_ACK_CAPTURE.md`](docs/M1E_USB_ACK_CAPTURE.md). The raw
capture stays under Git-ignored `artifacts/` and should not be posted publicly.

## M1F — first guarded Windows Chorus wet write/restore probe

The owner-reported physical M1E USBPcap timeline confirmed six Chorus wet
field-6 writes, each with a bare padded `0x8F` HID ACK and matching readback;
Chorus wet restored to `80`. Auto Wah was also toggled and restored
(`enable 0→1→0`) with readback confirmation. ACPWorkbench's numeric editor
appears to transmit partial values during typing; BPControl will NOT do this.

The new `tools/probe_chorus_windows.py` **CAN temporarily modify the physical
BP1032** but only with multiple explicit flags. It is limited to Guitar
Chorus `0x8F` / field 6 (wet), a **one-point change** followed immediately by
one restoration attempt and fresh readback of all seven Chorus fields.
It checks exact Windows HID identity, firmware 0.3.0 and effects library 2.24.0,
requires an explicit expected current wet value, and uses a killable worker
watchdog. A timeout/disconnection can prevent restoration. It never persists
to flash or writes any other effect/parameter.

**The M1F probe succeeded on the physical BP1032 on 2026-11-22** (both ACKs validated, wet 80→79→80, all 7 fields restored by readback). It remains a tightly restricted experiment; only run further tests after reviewing the safety notes,
with ACPWorkbench closed and audio muted:

```powershell
cd C:\progs\bpcontrol
git pull
py -m unittest discover -s tests -v
py tools/probe_chorus_windows.py --live-chorus-probe --expect-wet 80 --authorize-one-temporary-write
```

The expected value 80 is not assumed current: the probe performs two live
preflight readbacks and refuses to send parameter writes if either differs.
Outcomes are `PASS_RESTORED`, `ERROR_BUT_RESTORED`, or `STATE_UNCERTAIN`.
If unsuccessful, do NOT retry automatically; after the worker has exited,
verify wet using ACPWorkbench and restore manually if needed.

Read [`docs/M1F_FIRST_LIVE_WRITE.md`](docs/M1F_FIRST_LIVE_WRITE.md)
for the precise safeguards, limitations, and acceptance criteria.


## Verified M1F physical milestone — 2026-11-22

The first **BPControl-initiated write** to the physical BP1032 passed:

```text
Ran 84 tests in 0.448s
OK

status: PASS_RESTORED
baseline:            [1, 20, 10, 200, 50, 80, 80]
candidate_wet:       79
candidate_readback:  [1, 20, 10, 200, 50, 80, 79]
restoration_readback:[1, 20, 10, 200, 50, 80, 80]
candidate_ack_valid: true
restoration_ack_valid: true
restoration_verified: true
errors: []
```

**What is proven:** Windows HID read/write for one known effect field, its
ACK envelope, immediate readback of the modification and exact readback
of restored seven-field state. No flash persist/firmware write.

**What is not proven:** disconnected or interrupted rollback on hardware,
arbitrary effect writes, continuous sliders, safe concurrent ACPWorkbench
access, persistence or MIDI transport. The temporary M1F test should not
be mistaken for a general-purpose live editor.

Next: M1G staged numeric editing (draft text stored locally, Apply/Enter
only, validated field ranges, fresh readback and conflict detection).
See [M1F_FIRST_LIVE_WRITE.md](docs/M1F_FIRST_LIVE_WRITE.md) and
[ROADMAP.md](docs/ROADMAP.md).


## M1G — First staged visual editor (Windows GUI; hardware acceptance pending)

The initial M1G interface is a local **tkinter desktop** window. It uses the
59-instance snapshot for navigation and read-only parameter inspection. It
exposes exactly one writable parameter, **Guitar Chorus 0x8F / field 6 wet**.
Unlike ACPWorkbench, typing digits into the editor never sends intermediate
values. Only **Apply** or **Enter** plus an explicit confirmation sends a
single volatile **±1** adjustment, after fresh firmware verification and two
identical seven-field readbacks.

First review the interface with **NO USB activity**:

```powershell
cd C:\progs\bpcontrol
git pull
py -m pip install -e .
py -m unittest discover -s tests -v
py tools/chorus_editor_gui.py
```

If the offline interface looks correct, with ACPWorkbench **closed** and
audio muted or low, opt into manual USB reads and confirmation-gated edits:

```powershell
py tools/chorus_editor_gui.py --enable-live-writes
```

Nothing is transmitted merely by opening the window. Click **Consultar
Chorus (USB)**, type the one-point change, select **Aplicar**, and confirm.
If `APPLIED_VERIFIED` appears, **Desfazer último Apply** is available as
another deliberate one-step operation with readback. No flash save is sent.

If `STATE_UNCERTAIN`, the GUI blocks further writes; after the child
process has exited, inspect the state in ACPWorkbench. Do not blindly retry.

**M1G GUI-originated physical writes have not yet been tested**. The
previously verified M1F command-line write/restore should not be confused
with validation of this new graphical workflow.

See [`docs/M1G_GUI_EDITOR.md`](docs/M1G_GUI_EDITOR.md) for safety and tests.

## M1H — inspector UX (offline CI green; hardware acceptance pending)

The same familiar entry point `tools/chorus_editor_gui.py` now opens
the **M1H** inspector. All 59 saved effect instances are navigable with
search and a category filter. The parameter table indicates
**`Snapshot salvo`** versus **`USB / leitura atual`**, so a saved JSON
value cannot be mistaken for a current hardware reading.

The Chorus wet editor shows the **last confirmed live value** separately
from the local draft and displays a preview, such as `80 → 79 (-1)`.
`Aplicar` stays disabled until the operator has manually read the physical
board and entered a value exactly one point higher/lower. Typing, deleting
digits, changing focus, searching or navigating effects sends **no USB
commands**.

A new `Atividade da sessão` tab provides an in-memory record of manual
read, Apply, Undo, and draft cancellation. It stores at most 100 events
locally and copies them to the clipboard only on user request; nothing
is uploaded or automatically written to disk. Device worker responses are
now cross-checked against all seven expected Chorus fields, ACK validity
and the exact requested step before the GUI claims success.

Run **offline, no device access**:

```powershell
cd C:\progs\bpcontrol
git pull
py -m pip install -e .
py -m unittest discover -s tests -v
py tools/chorus_editor_gui.py
```

After inspecting the new layout, optionally try it on BP1032 with
ACPWorkbench closed and audio quiet:

```powershell
py tools/chorus_editor_gui.py --enable-live-writes
```

No automatic USB I/O on window startup. `Consultar Chorus (USB)`,
`Aplicar`, and `Desfazer` still require intentional clicks and
confirmation. The write allowlist, ±1 restriction, worker deadline,
recovery and no-flash policy are unchanged.

**M1H accepted on the physical BP1032 (2026-11-22):** operator GUI history shows manual wet read 80, explicit Apply 80→81 with ACK/readback, Undo 81→80 with ACK/readback, then independent fresh read wet=80. This verifies the corrected layout and tested editing path; USB disconnect safety, other effect writes, and all DPI configurations remain unproven.

See [`docs/M1H_INSPECTOR_UX.md`](docs/M1H_INSPECTOR_UX.md).


## M1I — Chorus manual evidence (read-only; Windows UI review pending)

The supplied ACPWorkbench English manual §6.1.27 documents Chorus delay
1..25 ms; modulation depth 0..(delay_length−1) ms; feedback 0..50%;
dry and wet 0..100%. Crucially the manual defines modulation rate
raw 10=1.0Hz and raw 100=10.0Hz, while earlier BPControl
documentation had raw100=1.0Hz and a physical BP1032 read returned
raw200, beyond the manual nominal limit. **Do not assign a definitive
Hz scale or enable rate writes until this is reconciled with a live
ACPWorkbench display reading.**

The existing desktop script adds a **Chorus · Evidências** tab showing
raw live/snapshot values, manual nominal ranges, data-source confidence,
and explicitly locked parameters. No new HID writers were added;
**only Chorus wet field6 ±1** remains authorized on deliberate Apply.

```powershell
cd C:\progs\bpcontrol
git pull
py -m pip install -e .
py -m unittest discover -s tests -v
py tools/chorus_editor_gui.py
```

Open **Chorus · Evidências** in the offline GUI. The Rate field now
records an **operator-reported paired point: USB raw=200 and ACPWorkbench
display=2.00 Hz**. This supports raw/100 only at that one point; no
general calibration or new write permissions. The six other
Chorus fields remain read-only. Normal wet Apply and Undo use
the unchanged, physically validated M1H backend, but they are not
needed to review this new tab.

See [`docs/M1I_CHORUS_MANUAL_RECONCILIATION.md`](docs/M1I_CHORUS_MANUAL_RECONCILIATION.md).

## M1I source triangulation — V2.40.0, BP1048 SDK and ESP32

A comparison of the owner-supplied **MVSilicon V2.40.0 ACP protocol**,
the connected **[BP1048 SDK](https://github.com/ovelhaaa/bp1048_sdk_v0.1.12)**,
and [ESP32 DSP Core `release`](https://github.com/Ohminecraft/esp32-dsp-core/tree/release)
has clarified two important points:

- Chorus rate `raw/10` is documented for the **BP1048 SDK DSP API**;
  its example firmware resets rate writes over 100 to 10. The physical
  BP1032 was read at `raw=200`. That mismatch requires real device
  investigation; **no new write permissions or definitive Hz conversion**.
- PingPong's **ACP parameter is in milliseconds**, while the **DSP library
  API takes samples**. The example firmware performs the ms→samples
  conversion. The BPControl ACP schema retains milliseconds.

The ESP32 adaptation is an independent DSP implementation, not a native
USB HID/ACP client for the BP1032 and not the same proprietary firmware.

Full provenance, source links, precautions and a safe read-only probe plan:
[`docs/M1I_PROTOCOL_SDK_CROSSCHECK.md`](docs/M1I_PROTOCOL_SDK_CROSSCHECK.md).

## M1I physical rate evidence — 2026-11-22

The operator supplied a screenshot of the M1I **Chorus · Evidências**
tab showing a genuine Windows USB readback of **Guitar Chorus field3
raw=200**, and reported that ACPWorkbench displays **2.00 Hz** for
the same parameter.

This is **one paired display observation supporting raw/100 on
the installed BP1032**; it is not a measurement of the full curve,
maximum/minimum rate, or guaranteed LFO acoustic frequency. The older
BP1048 SDK's raw/10 scaling and raw 0..100 limits must not be
silently applied to the different physical firmware.

The read-only UI now shows **2,00 Hz** only for an actual raw word
of **200**, explicitly citing this observation. Other rate values
remain raw with a scale-pending message; the field3 write API remains
disabled. Only Chorus wet field6 ±1 is writable on deliberate Apply.

See [`docs/M1I_PHYSICAL_RATE_PAIR.md`](docs/M1I_PHYSICAL_RATE_PAIR.md).


## BP1032 Chorus Rate — two display/USB observation pairs (2026-11-22)

A second physical BPControl screenshot confirms **rate raw=1000** after
ACPWorkbench was set to **10.0 Hz**, complementing an earlier
**raw=200 ↔ 2.00 Hz** pair. Both observed display points correspond to
**100 raw units per Hz** in this BP1032 host interface, whereas the
BP1048 SDK's algorithm API describes a different `raw/10` scale.

The M1I evidence inspector displays both observed values in Hz and
labels all other raw values as a **linear-scale hypothesis**, not a
validated calibration. Compact range summaries and a raw-only numeric
column also address truncation seen in the Windows screenshot.

There are **no new hardware writes**: the modulation-rate field remains
strictly read-only, the only writable Chorus field remains wet (index6),
and no `0xFD` flash-save or firmware command is enabled.

See [`docs/M1I_PHYSICAL_RATE_PAIR.md`](docs/M1I_PHYSICAL_RATE_PAIR.md).


## M1I third physical rate point — 2026-11-22

In a third read-only BPControl session, the operator followed the proposed
ACPWorkbench **5.00 Hz** intermediate test and sent a screenshot showing
**Guitar Chorus field3 raw=500**. Alongside the two earlier operator-reported
pairs, the evidence is now:

| ACPWorkbench setting | BP1032 USB readback | Display ratio |
|---|---:|---:|
| 2.00 Hz | 200 | 100 raw/Hz |
| 5.00 Hz | 500 | 100 raw/Hz |
| 10.00 Hz | 1000 | 100 raw/Hz |

**This supersedes earlier one-/two-point status notes above.** All three
points support `f_display_Hz = raw / 100` for this BP1032 / ACPWorkbench
combination. No overall range boundaries, every intermediate step,
acoustic LFO speed, or BPControl Rate write/Undo safety have been proven.

The inspector has been updated to show exactly those **three observed
pairs**, with the **current USB rate raw** in the heading and other raw
values marked as an inferred conversion. The Rate field stays strictly
**read-only**; only Chorus wet field6 retains its confirmed ±1 guarded
write pathway. The compact evidence table remains available.

See [`docs/M1I_PHYSICAL_RATE_PAIR.md`](docs/M1I_PHYSICAL_RATE_PAIR.md).
