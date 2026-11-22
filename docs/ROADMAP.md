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
- [x] Operator-run M1D audit output: 59/59, 845 raw parameter fields, 0 INI field-count discrepancies, 0 audit errors/warnings (2026-11-22).
- [ ] Validate per-field semantics, musical scaling and parameter ranges using independent protocol/UI evidence; full raw JSON remains local.
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
- [x] User supplied complete M1D console output confirming 59/59 reads with 845 words and 0 structural errors/warnings.
- [ ] Independently inspect the saved raw JSON when provided; continue to avoid automatic USB retries.
- [ ] Robust reconnect handling and cancellation across UI workflows. Do not open ACPWorkbench simultaneously.

## M1E — First write preparation (no live writes yet)
- [x] Add offline-only Chorus wet ±1 proposal with strict live-snapshot audit gate and byte-exact rollback frames.
- [x] Add regression tests refusing partial/corrupt snapshots or incompatible firmware.
- [x] Implement passive USBPcap Chorus wet-write/ACK analyzer with baseline and post-restore readback checks; synthetic regression tests pass.
- [x] Operator reports physical Chorus wet write/ACK capture: 6/6 bare 0x8F ACKs, baseline 80 and final readback restoration. Intermediate 8/81 values match live typing in ACPWorkbench.
- [x] Provide offline mixed Chorus/Auto Wah timeline for diagnostic review.
- [x] Physical mixed-activity timeline confirms Auto Wah enable 0→1→0 with final full readback 0, same as pre-test.
- [x] Implement M1F opt-in Windows-only one-step Chorus wet probe with 2 preflight readbacks, strict ACK, readback, one restoration attempt and 7-field verification; 84 offline tests passed and physical success verified.
- [x] First physical M1F probe succeeded (2026-11-22): PASS_RESTORED, Chorus wet 80→79→80, both ACKs valid, all 7 fields identical after restoration; no flash save. See [M1F_FIRST_LIVE_WRITE.md](M1F_FIRST_LIVE_WRITE.md).\n
## M1B — Safe controls
- [x] First guarded user-approved write on Chorus wet, with valid candidate readback and verified restoration on physical BP1032.
- [ ] Expand to separately validated parameters only; handle disconnection, stale state, and cancellation failures conservatively.
- [ ] Never emit `0xFD` persist/save, `0xFE` firmware upgrade, factory reset or unknown/reserved writes in the default transport.
- [ ] Acknowledge application-layer ACK is not proof of persistent configuration.
- [ ] Introduce local presets only after reliable read/write is proven.

## M1G — UI editing, staged not streaming
- [x] Implement a desktop M1G prototype with 59-effect snapshot browser; Chorus wet numeric draft is local and typing/Backspace/focus changes never send ACP (offline tests passed).
- [x] Apply only on explicit Enter/button plus user confirmation; integer 0..100, exactly ±1 per change, firmware and full 7-field double readback before write (offline tested).
- [x] Implement one volatile single-shot edit with readback, separate user-approved Undo, and one attempted restoration on error; never flash save (offline tested).
- [x] Operator reports M1G Windows GUI worked on the physical BP1032 (2026-11-22); exact Apply/Undo terminal/readback traces were not supplied.
- [x] Operator explicitly confirms both GUI **Aplicar** and **Desfazer** work on physical BP1032 (2026-11-22). Full per-operation USB/JSON traces are not yet archived; this is operator acceptance, not an independent capture.
- [x] Display every other field in read-only snapshot table, show mapping evidence and errors/uncertain-state lock.
- [x] Exercise pure draft parsing, ±1 validation, full-state conflicts, lost ACK, failed rollback, drift, worker timeout and bad worker output with offline mocks.
- [x] M1H: grouped 59-effect navigation/search, dedicated snapshot-vs-live origin, pure ±1 draft preview, in-memory activity history, and stricter 7-field worker reply validation (offline CI passed).
- [ ] Operator physical acceptance of M1H UI: navigation, staged draft, Apply/Undo feedback and activity log. No expanded write allowlist.
- [ ] Later: evaluate one additional Chorus parameter only after establishing its valid range/scaling, UI evidence and reversible write/readback test.\n
## M1H — inspector UX (implementation complete, physical acceptance pending)
- [x] Separate live Chorus value from saved snapshot, show evidence/field origins, and preview pending ±1 changes.
- [x] Add group filter and an in-memory activity tab with explicit Copy; no automatic telemetry, disk logging or new USB commands.
- [x] Reject malformed seven-field readback or inconsistent ACK-backed Apply response before presenting success.
- [x] Add offline tests for source labels, 59-effect filters, staged numeric drafts, and success-response parity.
- [ ] Validate M1H GUI on BP1032 (M1G already approved, M1H not yet physically checked).

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

**Now:** M1F write/readback/restore passed on the physical BP1032, and operator accepted both Apply and Undo of M1G on hardware. **M1H has now been implemented and passed offline tests on Windows/Linux, but has not yet been tried by the operator on the physical BP1032.** It improves grouped navigation, source labels (snapshot vs USB), a purely local ±1 draft preview, in-memory operation history and strict response validation. The only physically writable field remains Chorus `0x8F` field 6 wet with explicit approval; no flash saves, continuous writes, or additional effect writes. See [M1H_INSPECTOR_UX.md](M1H_INSPECTOR_UX.md).

Do not claim a successful USB/MIDI/audio implementation until demonstrated on the physical board.

### UI rule learned from M1E

ACPWorkbench appears to send intermediate values during text input: `80 -> 8 -> 81` and `81 -> 8 -> 80`, with duplicate transmissions. BPControl numeric fields must **stage uncommitted text locally**, validate it, and send a single intentional update only on explicit Apply/Enter. No live BPControl writer is activated by this finding.
