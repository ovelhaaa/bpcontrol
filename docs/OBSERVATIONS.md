# Observed evidence and provenance

Mappings were derived from owner-supplied ACPWorkbench USB TX/RX text logs, cross-checked with UI screenshots. Full raw captures are not bundled.

| Effect | Source log | Evidence |
|---|---|---|
| Mic Pro Reverb | Texto colado(20261122-005854).txt | partial, many fields inferred |
| Guitar Chorus | Texto colado(20261122-010029).txt | writes and readbacks |
| Music Delay | Texto colado(20261122-012121).txt | writes, readback, max delay read-only |
| Mic Echo | Texto colado(20261122-012619).txt | writes and readbacks, unknown field 04 |
| Guitar PingPong | Texto colado(20261122-012850).txt | writes/readback, RAM observations |
| Pitch Shifter Pro | Texto colado(20261122-020353).txt | change +7 to +12 semitones |

Firmware identifier returned by effect `0xFC` is `HunXiang_F`; this is not a complete verified firmware version. Observed packet data is at the application framing layer, not a raw USB bus capture.
