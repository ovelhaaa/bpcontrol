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
- Chorus rate: 100 => 1.00 Hz.
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

**Transport remains unknown:** ACPWorkbench textual logs do not establish USB VID/PID, HID report IDs, endpoint, report sizes, padding, fragmentation, or feature-vs-interrupt mechanism.
