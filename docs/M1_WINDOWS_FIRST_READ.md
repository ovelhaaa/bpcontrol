# BPControl M1 — First controlled Windows HID read

## Evidence behind the implementation

See [USB_CAPTURE_REPORT.md](USB_CAPTURE_REPORT.md), based on the owner's passive `chorus-02.pcapng` recording (2026-11-22). The source PCAP is **local only** and was not uploaded to the repository.

Confirmed for the physical BP1032:
- VID:PID `1235:0003`; manufacturer `MV-SILICON`, product `mvsilicon B1 usb audio`, release `0x0100`.
- HID interface `MI_04`, usage page `FF00`, usage `55AA`.
- Control EP0: SET_REPORT Output `21 09 00 02 04 00 00 01` and GET_REPORT Input `A1 01 00 01 04 00 00 01` (the last two bytes are little-endian wLength=256).
- Two identical Guitar Chorus reads in PCAP:
  - TX ACP `A5 5A 8F 00 16` + 251 zero pad bytes.
  - RX ACP `A5 5A 8F 0F FF 01 00 14 00 0A 00 C8 00 32 00 50 00 50 00 16` + 236 zero pad bytes.
  - Parsed fields `[1, 20, 10, 200, 50, 80, 80]`.
- HIDP_CAPS Windows buffers are **257 bytes including an initial zero Report ID selection**. PCAP wire payload was 256 bytes beginning directly at `A5`, not `00`.

## Offline tests — no USB interaction

From repository root:

```powershell
git pull
py -m pip install -e .
py -m unittest discover -s tests -v
```

All `tests/test_usb_hid.py` cases verify buffer shape and fail-closed parsing using the byte-exact Chorus response documented above. They do not need a connected device.

**Important:** these new tests have been added; until a local run or CI success is observed, do not claim Windows transport is proven working.

## Optional hardware smoke test — ONLY when operator chooses

Install `hidapi` if needed (`py -m pip install hidapi`). Close ACPWorkbench completely, ensure the target BP1032 is plugged in and audio is muted or at low volume; then run:

```powershell
py tools/read_chorus_windows.py --live-read-chorus
```

This explicitly authorizes **one ACP read** (command `0x8F` only). The script:
- Selects precisely one verified MI_04 vendor HID collection using VID/PID, interface number, Usage Page/Usage, manufacturer/product and release.
- Uses `CreateFileW`, `HidD_SetOutputReport` and `HidD_GetInputReport` via Win32 HIDClass APIs.
- Sends a 257-byte Windows API buffer: zero report-ID slot + 5-byte ACP read query + 251 zero bytes.
- Issues exactly one `GET_REPORT`, validates reply ID slot, ACP framing/command/length, signed fields, 256-byte payload boundaries and zero padding.
- Runs synchronous Windows API calls in a child process; after a **4-second parent-side deadline**, the child is terminated and handles are released. Does not retry after any failure.
- Does **not** send a field write, firmware save, factory reset or upgrade.

No hardware invocation occurs unless `--live-read-chorus` is supplied.

### Expected output on success

```text
READ OK: 0x8F Guitar Chorus
values: enable=1, delay_length=20, depth=10, rate_raw=200, feedback=50, dry=80, wet=80
```

**These values were captured earlier and may have changed.** Actual result must come from the device. The raw Chorus rate-to-Hz conversion remains in dispute across versions; print the raw value only.

### If the command fails

Provide the complete error (you may redact local Windows user paths), but do not retry repeatedly or switch Windows drivers.

- `CreateFileW ... WinError 5`: another process (ACPWorkbench) could hold the interface, or the OS could deny requested access.
- `HidD_SetOutputReport` or `HidD_GetInputReport` failure: Windows HIDClass method or device timing is unproven. A new USBPcap trace of **the one attempted read** (operator-approved) will distinguish failing setup/transfer type, if any.
- `invalid ACP reply`: inspect the report carefully; do not modify parsing to accept arbitrary bytes.
- `TIMEOUT`: child process is terminated; do not automatically retry.

## Validation boundary

The PCAP proves ACPWorkbench's USB behavior but does **not** prove these exact Win32 API calls succeed with this firmware. The one-shot hardware test is the next milestone. Never confuse the `SET_REPORT` HID **transport request** carrying an ACP *read query* with an ACP parameter write.

References:
- [Microsoft HidD_SetOutputReport](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/hidsdi/nf-hidsdi-hidd_setoutputreport)
- [Microsoft HidD_GetInputReport](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/hidsdi/nf-hidsdi-hidd_getinputreport)

## Live read success — 2026-11-22

The owner ran `py tools/read_chorus_windows.py --live-read-chorus` against
the physical BP1032, with ACPWorkbench closed, and reported:

```text
READ OK: 0x8F Guitar Chorus
values: enable=1, delay_length=20, depth=10, rate_raw=200, feedback=50, dry=80, wet=80
```

This exactly matches the earlier passive Chorus PCAP readback fixture and
confirms physical Windows HID SET_REPORT/GET_REPORT transport and parsing for
this read. No parameter writes or save commands were issued. It does **not**
yet prove other command handling or ESP32-S3 USB Host operation.

Next stage is explicitly opt-in firmware and status reads; see
`tools/read_info_windows.py`. No `0xFD` / `0xFE` operations are permitted.
