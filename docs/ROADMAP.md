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
- [x] Operator physically confirmed M1H manual USB reads twice (Chorus wet=80) and reported Apply control not visible; identified layout ordering and overwide action row as likely causes, corrected in GUI.\n- [x] Operator physically validated corrected M1H end-to-end: explicit USB read wet=80, Apply 80→81 with GUI ACK/readback, Undo 81→80 with ACK/readback, then independent USB read wet=80 (17:59:39–17:59:59, 2026-11-22). Editor controls are operable. No expanded write allowlist.
- [ ] Later: evaluate one additional Chorus parameter only after establishing its valid range/scaling, UI evidence and reversible write/readback test.\n
## M1H — inspector UX (physical happy path accepted)
- [x] Separate live Chorus value from saved snapshot, show evidence/field origins, and preview pending ±1 changes.
- [x] Add group filter and an in-memory activity tab with explicit Copy; no automatic telemetry, disk logging or new USB commands.
- [x] Reject malformed seven-field readback or inconsistent ACK-backed Apply response before presenting success.
- [x] Add offline tests for source labels, 59-effect filters, staged numeric drafts, and success-response parity.
- [x] Validate corrected M1H GUI on physical BP1032 with read→Apply→Undo→fresh read, all successful according to GUI session history. This does not validate every DPI/layout condition or disconnect handling.

## M1I — manual ranges and evidence inspection (offline, physical review pending)
- [x] Recheck ACPWorkbench English user manual §6.1.27: Chorus delay 1..25 ms, depth 0..(delay_length−1), rate 0..10 Hz in 0.1-Hz steps, feedback 0..50%, dry/wet 0..100%.
- [x] Compare against ACPWorkbench.ini raw rate=10, historical protocol note raw100=1.00Hz, original USB log raw100, and M1F physical field3 raw200; **rate scaling and range remain contradictory**.
- [x] Disable Chorus field3 write hints and mark its unit raw/inferred; keep only wet field6 authorized by existing runtime code. Update data/effects.json with unresolved scale rather than a definite conversion.
- [x] Add read-only “Chorus · Evidências” tab with seven raw fields, manual limits, snapshot/live origin, evidence sources and write permission indicators.
- [x] Add offline tests protecting manual range source, unresolved scale, and wet-only permission. CI Windows/Linux green.
- [x] Operator provided screenshot of M1I physical BP1032 Chorus evidence tab: live USB field3 raw=200, wet=80, read-only field3 visible (2026-11-22).
- [x] Cross-check protocol V2.40, `chorus.h`, `pingpong.h`, sample `communication.c`, `ctrlvars.c`, and Ohminecraft ESP32 adaptation; findings in [M1I_PROTOCOL_SDK_CROSSCHECK.md](M1I_PROTOCOL_SDK_CROSSCHECK.md).
- [x] Reconcile ACP PingPong delay **ms** with SDK internal delay **samples**, converted by the BP1048 sample firmware; keep the host schema in ms.
- [x] Operator reports ACPWorkbench displays Chorus rate **2,00 Hz** for the BP1032; physical M1I screenshot shows USB **raw=200**. One paired display point recorded in [M1I_PHYSICAL_RATE_PAIR.md](M1I_PHYSICAL_RATE_PAIR.md); supports raw/100 *at that point*, not the entire rate curve. No field3 writes.
- [ ] Validate BP1032 rate mapping at a second distinct value by safe read-only cross-application comparison before asserting global linearity or enabling a rate editor.
- [ ] Test the actual BP1032 PingPong max_delay/quality range before any write; the ms→samples conversion is evidenced only in the BP1048 sample firmware.

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

**Now:** M1H live Chorus wet read→Apply→Undo→read is operator-accepted on physical BP1032. **M1I read-only evidence view has been reviewed on the operator's physical BP1032**, including USB field3 raw=200 and an operator-reported ACPWorkbench display of 2,00 Hz. This supports a physical raw/100 *display point*, not a general calibration or safe rate writes. Reinspection of supplied ACPWorkbench English manual §6.1.27 uncovered nominal ranges for all six numeric Chorus fields; importantly it contradicts the earlier rate-scale note. Manual says raw10=1.0Hz and raw100=10.0Hz, while previous BPControl notes suggest raw100=1.0Hz and the physical board read raw200. Chorus rate now has **one paired display point (raw 200 ↔ 2,00 Hz)**, while its global conversion/range remains unverified and field3 remains non-writable. The new read-only evidence tab documents every parameter, nominal manual bounds and source confidence. The **only** writable effect field remains Guitar Chorus wet `0x8F`/6 in confirmed ±1 steps; no flash save. See [M1I_CHORUS_MANUAL_RECONCILIATION.md](M1I_CHORUS_MANUAL_RECONCILIATION.md).

Do not claim a successful USB/MIDI/audio implementation until demonstrated on the physical board.

### UI rule learned from M1E

ACPWorkbench appears to send intermediate values during text input: `80 -> 8 -> 81` and `81 -> 8 -> 80`, with duplicate transmissions. BPControl numeric fields must **stage uncommitted text locally**, validate it, and send a single intentional update only on explicit Apply/Enter. No live BPControl writer is activated by this finding.
