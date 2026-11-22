# BPControl roadmap — USB-first

## Hardware constraint (confirmed by owner)

The user's BP1032 board exposes **no accessible UART pins**. The working ACPWorkbench connection is through the board's USB interface. Therefore **USB is the primary control path**. Do not require soldering wires, hardware modifications, a firmware flash, or inaccessible UART/I2C connections as part of the MVP. If alternative interfaces are discovered later, treat them only as optional.

The owner's 2026-11-22 USBPcap analysis confirms vendor HID **MI_04**, EP0 control SET_REPORT Output and GET_REPORT Input, Report ID **0**, `wIndex=4`, `wLength=256`, ACP at offset 0, zero pad. Windows HIDP_CAPS buffers are 257 bytes including the ID slot. The one-shot Win32 HID Chorus read was **confirmed successful on the owner's physical BP1032** on 2026-11-22 (exact same seven fields as passive USBPcap capture). Firmware and status reads were also **confirmed on the physical BP1032**; firmware 0.3.0, effects library 2.24.0, memory 70/320 KB, CPU 26 MCPS (per ACPWorkbench §8.1), max frequency 320 MHz.

## M0 — ACP application protocol (offline)
- [x] ACP encode/decode including signed 16-bit words.
- [x] Six observed effect schemas and packet fixtures; offline CLI and unit tests.
- [x] Review owner-supplied official ACPWorkbench manual, V2.40.0 communication specification and exported INI.
- [x] Implement 0x02 status parsing with physical fixture and MCPS unit.
- [x] Extract 59 instance names/types/parameter hints from owner-supplied ACPWorkbench.ini (not proof of current values).
- [x] Implement offline structural M1D auditor with raw-byte/word parity checks and 59-instance mapping-confidence table.
- [x] Operator-run M1D audit output: 59/59, 845 raw parameter fields, 0 INI field-count discrepancies, 0 audit errors/warnings (2026-11-22).\n- [ ] Validate per-field semantics, musical scaling and parameter ranges using independent protocol/UI evidence; full raw JSON remains local.
- [ ] Correct Echo quality mode (0..2); reconcile Chorus rate scaling vs UI evidence.

## M1A — Windows USB discovery (read-only, no reflash)
- [x] Capture USB VID:PID and enumerate composite interfaces: audio MI_00, consumer HID MI_03, vendor-defined HID MI_04.
- [x] Determine HIDP_CAPS capacities for MI_04: **Input 257, Output 257, Feature 9** bytes (report-ID slot included).
- [ ] Acquire detailed HID report descriptor, report IDs and endpoint information.
- [x] Confirm USB composite with Microsoft HID driver and vendor-defined collection at `MI_04` (`usage_page 0xFF00`, `usage 0x55AA`).
- [x] Confirm by passive capture that ACPWorkbench sends ACP traffic on MI_04.
- [x] Capture two complete Chorus reads via USBPcap; report and byte-exact fixtures in [USB_CAPTURE_REPORT.md](USB_CAPTURE_REPORT.md).
- [ ] Save sanitized descriptor and transaction fixtures. Avoid including other USB devices' unrelated/private traffic in the repository.
- [x] Implement tightly restricted experimental one-shot Windows MI_04 Chorus read + offline tests.
- [x] Verify a real Windows one-shot Chorus read on BP1032: `[1,20,10,200,50,80,80]`.
- [x] Implement opt-in, one-shot, no-retry firmware `0x00` and status `0x02` readers with offline tests.
- [x] Verify firmware and status reads on physical board; decode observed values from official protocol v2.40.0 and ACPWorkbench MCPS unit. See [M1_PHYSICAL_FIRMWARE_STATUS.md](M1_PHYSICAL_FIRMWARE_STATUS.md).
- [x] Implement one bounded 59-effect snapshot with strict version gate, explicit opt-in, fail-closed reports and offline tests.
- [x] Operator reports successful physical batch read and HTML visualization (2026-11-22).
- [x] User supplied complete M1D console output confirming 59/59 reads with 845 words and 0 structural errors/warnings.\n- [ ] Independently inspect the saved raw JSON when provided; continue to avoid automatic USB retries.
- [ ] Robust reconnect handling and cancellation across UI workflows. Do not open ACPWorkbench simultaneously.

## M1E — First write preparation (no live writes yet)\n- [x] Add offline-only Chorus wet ±1 proposal with strict live-snapshot audit gate and byte-exact rollback frames.\n- [x] Add regression tests refusing partial/corrupt snapshots or incompatible firmware.\n- [x] Implement passive USBPcap Chorus wet-write/ACK analyzer with baseline and post-restore readback checks; synthetic regression tests pass.\n- [ ] Collect one *physical* ACPWorkbench Chorus wet write/ACK capture with verified restoration; no BPControl parameter writes.\n- [ ] Implement narrowly whitelisted, operator-approved single write + readback + verified rollback only after ACK transport is confirmed.\n\n## M1B — Safe controls
- [ ] Guarded, user-approved write on a known parameter, with readback verification, rollback to prior value and safe interruption behavior.
- [ ] Never emit `0xFD` persist/save, `0xFE` firmware upgrade, factory reset or unknown/reserved writes in the default transport.
- [ ] Acknowledge application-layer ACK is not proof of persistent configuration.
- [ ] Introduce local presets only after reliable read/write is proven.

## M2 — UI and resource management
- [x] First offline read-only snapshot explorer: groups, search, CPU MCPS/RAM, raw signed/u16 parameter cards.
- [ ] Live desktop editor with safe write confirmation, validated ranges, bypass and local presets.
- [ ] 0x02 system status telemetry (CPU and RAM) validated against ACPWorkbench.
- [ ] PingPong memory model and resource warnings for 100/250/500/1000 ms normal/HQ.
- [ ] Avoid assuming algorithms only present in the generic manual are installed on this board.

## M3 — ESP32-S3 USB Host standalone controller
- [ ] Prove native ESP32-S3 USB OTG **host** can enumerate the actual BP1032 interface and transfer verified HID/control reports.
- [ ] Provide correct VBUS 5 V power, common ground and a suitable host-capable USB connector/adapter. Verify electrical current budget first.
- [ ] Consider powered USB hub if board power needs exceed controller board supply.
- [ ] Reuse ACP core with ESP-IDF USB Host backend; avoid USB peripheral conflicts with the S3's serial/JTAG interface.
- [ ] Add encoders/buttons, MIDI, presets, display and safe reconnect.
- [ ] Audit clicks, live delay-time modulation, patch-switching and tap tempo with actual audio later.

## Evidence gate

**Now:** the user-run M1D audit is **clean: 59/59 effects, 845 raw words, six matching schemas, zero count mismatches, zero audit errors and warnings**. This proves structural consistency only, not all parameter semantics. The offline M1E Chorus wet ±1 proposal is available; **no BPControl effect writes have been enabled**. Next evidence is one ACPWorkbench single-field write/ACK USBPcap capture, analyzed with `tools/analyze_chorus_write_ack.py` and verified restoration; see [M1E_USB_ACK_CAPTURE.md](M1E_USB_ACK_CAPTURE.md). See [M1E_FIRST_WRITE_PREPARATION.md](M1E_FIRST_WRITE_PREPARATION.md).

Do not claim a successful USB/MIDI/audio implementation until demonstrated on the physical board.
