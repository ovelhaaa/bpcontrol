# BPControl M1C — 59 effect instances, read-only snapshot and offline UI

## What is implemented

**Firmware-specific source of truth:** the owner's `ACPWorkbench.ini`
(exported 2026-11-21, ACPWorkbench 2.43.3) contains one effect-list `list`
array of **59 type IDs**, `name_effect1` ... `name_effect59` and 59
sections `[0x81-...]` ... `[0xBB-...]`. Parsed into
[`data/effect_instances.json`](../data/effect_instances.json).

- **Effect instance ID**: integer 1..59, maps to ACP command `0x80 + ID`.
- **Effect type ID** from `[0x80-Effect_List]` is *not* the command.
- **Effect name and parameters from INI are hints**, not a current device
  snapshot and not evidence that names/scales correspond to raw field positions.
- Six previously investigated effects have evidence-graded schemas in
  `src/bpcontrol/effects.py`. Field names are applied only if the complete
  observed word count matches the schema. Every other field is `field_NN`
  with optional `ini_hint`; both signed and unsigned 16-bit views are kept.

The new collector reads **exactly 61 known ACP queries** at most:
`0x00` (firmware), `0x02` (status), then `0x81..0xBB` in instance order.
All are application-level read requests with empty payloads; HID still uses
one SET_REPORT Output and one GET_REPORT Input for each.

Physical board validation from previous stages: `0x8F`, `0x00`, `0x02`
**passed**. The owner later reported that the **59-effect bulk read and offline visualizer worked** (2026-11-22); the actual JSON has not yet been reviewed independently. Continue with [M1D snapshot audit](M1D_SNAPSHOT_AUDIT.md).

## Safety gates

1. The collector does nothing to USB without `--live-read-all`.
2. Before **any effect read** it reads and validates the connected device:
   `MV-SILICON`, `mvsilicon B1 usb audio`, VID:PID `1235:0003`, HID
   `MI_04`, usage `FF00:55AA`, release `0x0100`.
3. The `0x00` firmware must match **type `0x30` / firmware `0.3.0` /
   effects library `2.24.0`**. Otherwise it refuses effect reads.
4. Read command allowlist is fixed to `0x00`, `0x02`, `0x81..0xBB`. No
   `0x80` catalog discovery request with unknown payload; never `0xFD`,
   `0xFE`, `0x01` system control, effect parameter writes, reset or save.
5. A single open Windows HID session is supervised by a **45-second subprocess
   timeout**. No automatic retries, no polling or simultaneous requests.
6. Replies must match the requested command and have valid ACP frame, ID=0
   and zero report padding. Effect readbacks must contain `FF` plus an even
   number of bytes. A bad effect response **stops the batch**. The JSON then
   has `complete:false`, an `error_effect_index`, and unread entries.
7. JSON snapshots never contain device serial numbers, PnP instance paths,
   host timestamps from USBPcap, or unrelated USB traffic.
8. Outputs under `artifacts/` are Git-ignored; neither HTML nor JSON is
   automatically committed or published.

## Try it on Windows

Close ACPWorkbench and do not run another BPControl USB process concurrently.
An initial, **offline-only** check:

```powershell
cd C:\progs\bpcontrol
git pull
py -m pip install -e .
py -m unittest discover -s tests -v
py tools/render_snapshot.py data/demo_snapshot.json --open
```

The **demo** combines only the three historical, independently verified
readbacks (firmware, status and Chorus), so it has **58 unread effects**. It is
clearly marked as partial and never claims to be an actual 59-effect reading.

When comfortable, use one intentional **hardware** snapshot:

```powershell
py tools/snapshot_windows.py --live-read-all --output artifacts/snapshots/bp1032-01.json
```

Expected successful summary (illustrative; reported successful by the operator, exact terminal output not provided):

```text
Saved: artifacts/snapshots/bp1032-01.json
Read: 59/59 effects
COMPLETE. All effects were read. No DSP parameters changed.
```

If the collector returns `PARTIAL`, **do not repeat automatically**. Keep the
generated JSON, report the stopping effect index and error, and investigate
before any new hardware test.

After a successful or partial snapshot, render locally:

```powershell
py tools/render_snapshot.py artifacts/snapshots/bp1032-01.json --open
```

The output `artifacts/snapshots/bp1032-01.html` is **a standalone read-only
report**, not a USB control UI. Open it in any browser. It uses no web
requests, local server, Vite, package manager or browser permission to USB.

## UI and interpretation notes

- Dark left rail with grouped effect instances; warm off-white main canvas,
  graphite typography and orange accent.
- Firmware version, read count, memory KB and CPU **MCPS**.
- CPU relative-to-nominal-max ratio is `MCPS / max MHz`, **not** a measured
  instantaneous CPU utilization percentage.
- A green read-status indicator means **the ACP frame parsed**, not that
  every parameter's display label has been experimentally validated.
- `status:unread` and `status:error` are explicit; no fabricated values.
- Detail cards show raw signed/u16 fields and INI names as reference only.

## Next after successful 59/59 read

1. Audit mismatches between count of actual readback words and INI hints,
   prioritizing Chorus, PingPong, Pro Reverb, Echo and active EQs.
2. Read back one subset a second time with a manual operator command, then
   compare to the saved snapshot to confirm stability (no background polling).
3. Implement named, test-backed parameter editors **later**, behind an
   explicit write authorization gate, readback, and rollback. No save to flash.
4. Once a Windows control UI is stable, port the same known EP0 USB/HID
   application framing to ESP32-S3 in USB Host mode.

## Source references

- `ACPWorkbench.ini`: source for per-instance names, type IDs, field **hints**.
- `固件与用户应用程序通信协议V2.40.0.pdf`: ACP effects readback structures
  and firmware/status fields.
- [`docs/USB_CAPTURE_REPORT.md`](USB_CAPTURE_REPORT.md): verified
  HID transport, report lengths, actual two Chorus transactions.
- [`docs/M1_PHYSICAL_FIRMWARE_STATUS.md`](M1_PHYSICAL_FIRMWARE_STATUS.md):
  physical firmware/status, including MCPS unit evidence.
