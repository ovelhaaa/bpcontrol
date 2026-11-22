# ACP protocol: observations, not USB reports

## Application-layer frame
```
A5 5A CMD LEN [LEN bytes of payload] 16
```
- A field write for effect index n is `A5 5A (0x80+n) 03 FIELD VALUE_LO VALUE_HI 16`.
- An effect read is `A5 5A (0x80+n) 00 16`.
- A write ACK appears in ACPWorkbench as the single byte CMD (not a full frame).
- A readback includes `FF` followed by signed little-endian 16-bit words; first word is enable for studied effects.
- The `0x80` Effect List catalog contains **different numeric IDs**; do not conflate catalog entries and effect command indexes.

## Known values
- Pitch Shifter Pro: 70 => +7 semitones, 120 => +12.
- **Chorus modulation rate has a cross-version scale conflict and two BP1032 physical display pairings; no globally verified conversion.** ACPWorkbench English manual §6.1.27 (PDF page 27)
  defines raw 2=0.2Hz, 10=1.0Hz, 100=10.0Hz and a 0..100 nominal raw
  range (0.1Hz steps). An earlier BPControl note interpreted raw
  100=1.00Hz (raw/100), and the physical BP1032 M1F baseline included
  raw **200**, outside the manual's stated 0..100 range. The ACPWorkbench
  INI uses raw 10 and an ACPWorkbench USB log captured a raw 100
  write. Treat all those as separate observations; do not claim a
  definitive frequency or enable rate writes until reconciled.
- **BP1048 SDK corroboration:** `chorus.h` v1.1.1 documents raw/10
  for the *BP1048 algorithm API*. Its example `communication.c`
  substitutes 10 for Chorus rate writes >100, whereas physical BP1032
  readback contained raw200. The observed value is not proof of
  raw/100 scaling or of identical/different firmware; do not write.
  See [M1I_PROTOCOL_SDK_CROSSCHECK.md](M1I_PROTOCOL_SDK_CROSSCHECK.md).
- **BP1032 physical display observations (2026-11-22):**
  operator-provided M1I USB screenshots show Chorus field3 **raw=200**
  (ACPWorkbench **2.00 Hz** according to operator) and, after setting
  ACPWorkbench to **10.0 Hz**, **raw=1000**. Both match a display
  scale of `raw/100` at these **two observed points**. This is
  stronger than a single pair, but does **not** prove global linearity,
  allowable endpoints, or the acoustically generated LFO. BP1048
  SDK `raw/10` describes another documented API/firmware.
  **Rate remains read-only**.
  See [M1I_PHYSICAL_RATE_PAIR.md](M1I_PHYSICAL_RATE_PAIR.md).
- **Chorus nominal ranges per the manual (§6.1.27):** Delay Length
  1..25 ms; Modulation Depth 0..(delay_length−1) ms; Feedback 0..50%;
  Dry and Wet 0..100%. These are documentation-level limits, not
  completed hardware boundary tests for firmware HunXiang_F.
- **PingPong host/API unit bridge:** protocol V2.40 §5.20.30
  documents ACP `delay` in **ms** (default 250 ms) and `max_delay` in
  **ms** (default 1000 ms). BP1048 SDK `pingpong.h` takes **samples**
  internally; example firmware `ctrlvars.c` explicitly converts
  `delay_samples = delay_ms * sample_rate / 1000` (also max_delay).
  Retain **ms** in BPControl's ACP schema; firmware-specific behavior
  still needs live verification.
- Echo and PingPong gain: approximately `int(32768 * 10**(dB/20))` for -6, -7, -8 dB.
- Mic Echo field 04 is **unknown**; readback-only `max_delay` fields are locked in the observed UI.
- Most individual Pro Reverb labels are **inferred, not independently confirmed**.

## PingPong RAM measurements (displayed KB)
| Max Delay | Normal | High Quality |
|---|---:|---:|
| 100 ms | 70 | 82 |
| 250 ms | 78 | 108 |
| 500 ms | 91 | 151 |
| 1000 ms | 116 | 237 |

Baseline with PingPong off: 65 KB. RAM rises approximately linearly with maximum buffer length; displayed MCPS changed little with buffer size. These data **do not prove** an internal sample format or precise CPU cost.

**USB transport now established:** owner USBPcap trace and one-shot Windows physical reads confirm HID MI_04, control EP0, SET_REPORT Output + GET_REPORT Input, Report ID 0, 256-byte data reports with ACP at offset 0 and zero padding. See [USB_CAPTURE_REPORT.md](USB_CAPTURE_REPORT.md) and [M1_PHYSICAL_FIRMWARE_STATUS.md](M1_PHYSICAL_FIRMWARE_STATUS.md).

## CPU status unit

The ACP protocol v2.40.0 §5.3 calls the 16-bit system-status field `CPU Usage` without stating its unit. The ACPWorkbench English manual v2.25.0 §8.1 (p. 33) **explicitly defines MCPS as mega cycles per second**. Physical BP1032 status returns raw `26`, interpreted as **26 MCPS**. MCPS is not MIPS. Dividing 26 MCPS by the reported maximum clock 320 MHz yields 8.125% of nominal maximum cycle throughput, but should not be labeled a measured instantaneous CPU percentage.
