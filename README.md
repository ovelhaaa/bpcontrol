# BPControl

**BPControl** is an experimental, evidence-based controller toolkit for MVSilicon BP10xx DSP boards, initially targeting **BP1032** with the observed `HunXiang_F` firmware.

> **Status: M1A (USB HID transport candidate implemented, live test pending).** The Windows driver is restricted to a single explicitly authorized Chorus read; it has **not yet been verified against the physical BP1032**. This project does not replace DSP firmware or process audio.

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

The `read` and `write` commands **print ACP packets; they DO NOT send anything to hardware**. USB HID descriptors, report IDs, padding, and transport details still require verification.

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
