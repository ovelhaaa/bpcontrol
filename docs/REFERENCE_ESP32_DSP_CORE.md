# External reference: Ohminecraft/esp32-dsp-core

Source repository: https://github.com/Ohminecraft/esp32-dsp-core
Examined reference: `release` branch, tree `b95bdfcc73af04b75de103d4be127ebe394a00e2` (2026-11-22).
License reported in source: MIT, copyright 2026 Shine Nagumo.

## What it is / isn't

This is a complete **ESP32/ESP32-S3 self-hosted audio DSP engine**, not a control client for external MVSilicon BP1032 hardware. It performs I2S audio processing on its own MCU, with controls over USB serial/UART and Wi-Fi WebSocket, a browser/Electron UI and NVS presets. It contains no active BP1032 USB HID host implementation and does not use ACP framing.

**Protocol incompatibility**:
- This ESP32 engine uses `AA 55 CMD MOD_ID LEN_LO LEN_HI ... XOR` (see `docs/protocol.md`, `dsp-control-app/js/protocol.js`).
- BPControl targets MVSilicon ACP application frames `A5 5A CMD LEN ... 16` wrapped in the still-undetermined MI_04 HID transport.
- Do **not** send the former to the BP1032 or reuse its binary frame parser as if it were ACP.

## Active audio modules

`src/effects/dsp_pipeline.cpp` instantiates: parameter gain, pre EQ, pre gain, compander, exciter, dynamic bass, dynamic EQ, two ISF blocks, two parametric EQs, independent left/right EQ, multiband DRC and post gain (14 chain slots). It processes float32 buffers in place. Audio I/O uses I2S.

No active implementations of BP1032 PingPong, Chorus, Echo, Plate/Pro Reverb or Pitch Shifter Pro were found in the inspected tree.

The `src/effects/compander.cpp` header says "optimized per MVSilicon SDK patterns." `include/config.h` says the architecture is inspired by MVSilicon BP10xx. `src/effects/exciter.cpp` explicitly implements its own three-band crossover + soft clipping. These are **inspired/adapted implementations, not demonstrated bit-identical ports of firmware algorithms**.

`unused/effects/virtual_bass.cpp` claims "rewritten based on MVSilicon BP1048 SDK Virtual Bass (v4.4.2)" and documents crossover, harmonic generation, gating and gain smoothing. That source is outside the active pipeline and uses a `q31_t*` process signature while the active pipeline's base interface expects `float*`. It cannot be assumed drop-in compatible without an adaptation and tests.

## Useful architectural ideas for BPControl

1. **Control separation:** communication, UI/WebSocket, DSP/target backend and presets should stay in independent modules; do not embed HID I/O into UI callbacks.
2. **State sync:** use an explicit device snapshot -> UI model -> guarded write -> confirm/readback loop; batch UI updates, not speculative USB commands.
3. **Presets:** save locally, validate against actual discovered BP1032 effect schema, offer safe restore. Do not call BP1032 firmware-save `0xFD` by default.
4. **UI:** inspect touch-friendly editor layout and parameter visualization only as inspiration, because MVSilicon native effect ranges and scaling differ.
5. **Possible separate DSP project:** the biquad, compressor, dynamic EQ and dynamics architectures can inform another ESP32 audio pedal, but **BPControl** remains USB Host controller for existing BP1032 firmware.

## Risks / discrepancies to keep in mind

- The source's MIT license governs the repository's declared code, but it does not independently establish the redistribution rights of any third-party MVSilicon SDK-derived material. Verify provenance before copying algorithms.
- README advertises 2.67 ms while `include/config.h` configures `DSP_FRAME_SIZE=512` for ESP32-S3 and `DSP_SAMPLE_RATE_DEFAULT=96000`; **512 / 96000 = 5.33 ms per block**, before I2S/DMA or processing overhead. The 2.67 ms number corresponds to 256 frames at 96 kHz (configured for ESP32).
- Build workflow exists, but there is no obvious automated listening/response or benchmarking test suite in the inspected source tree. Build success is not proof of tonal fidelity.
- The author's proprietary UART/WebSocket binary protocol is not compatible with MVSilicon ACP and gives no evidence about BP1032 HID MI_04 Report ID, padding or packet segmentation.

## Source code references

- [Audio pipeline](https://github.com/Ohminecraft/esp32-dsp-core/blob/release/src/effects/dsp_pipeline.cpp)
- [MVSilicon-inspired config](https://github.com/Ohminecraft/esp32-dsp-core/blob/release/include/config.h)
- [Independent control protocol](https://github.com/Ohminecraft/esp32-dsp-core/blob/release/docs/protocol.md)
- [Compander](https://github.com/Ohminecraft/esp32-dsp-core/blob/release/src/effects/compander.cpp)
- [Exciter](https://github.com/Ohminecraft/esp32-dsp-core/blob/release/src/effects/exciter.cpp)
- [Virtual Bass (unused)](https://github.com/Ohminecraft/esp32-dsp-core/blob/release/unused/effects/virtual_bass.cpp)
- [License](https://github.com/Ohminecraft/esp32-dsp-core/blob/release/LICENSE)

**BPControl M1 priority unchanged:** collect a *passive* ACPWorkbench transaction on the verified BP1032 MI_04 (`0x1235:0x0003`, usage page `FF00`, usage `55AA`) using Wireshark/USBPcap; input/output caps 257 bytes, feature caps 9 bytes, report ID unknown.
