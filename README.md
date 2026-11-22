# BPControl

**BPControl** is an experimental, evidence-based controller toolkit for MVSilicon BP10xx DSP boards, initially targeting **BP1032** with the observed `HunXiang_F` firmware.

> **Status: M0 (offline ACP protocol MVP).** Encoders, decoders and automated tests run without hardware. **USB HID transport is not yet implemented.** The project does not replace DSP firmware or process audio.

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
