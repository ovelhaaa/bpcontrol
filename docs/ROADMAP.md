# BPControl roadmap

## M0 — Protocol foundation (offline)
- [x] ACP encode/decode including signed 16-bit values.
- [x] Six evidence-graded effect mappings, fixtures and conversions.
- [x] Offline CLI; automated tests.
- [ ] USB descriptors and raw host-device report capture.
- [ ] Validate firmware differences and parameter ranges.

## M1 — Windows USB read-only MVP
- [ ] Device enumeration with known VID/PID and verified interfaces.
- [ ] Read-only firmware tag and effect state; timeouts and controlled retries.
- [ ] Recording/replaying safe fixtures and simulated transport tests.
- [ ] User-approved single safe write, ACK, readback, restore.

## M2 — Controller software
- [ ] Editor/UI grouped by effect, bypass, guarded parameters.
- [ ] Local JSON presets; explicit apply and safe undo/restore.
- [ ] Resource estimates for PingPong HQ vs normal.

## M3 — ESP32-S3 standalone controller
- [ ] Port transport through ESP-IDF USB Host without touching DSP firmware.
- [ ] Encoders/buttons, USB/MIDI, presets and optional web UI.
- [ ] Stable reconnect, nonblocking control task, bounded queues.
- [ ] Audition and validate live parameter changes, artifact-free tap tempo.

Do not claim USB or musical audio behavior validated until measured on hardware.
