# USB transport: open questions and safe validation

ACPWorkbench's text log shows ACP **application frames**, not raw USB reports.

Collect evidence for the exact board:
1. VID/PID, interface class/subclass/protocol, interface and endpoint descriptors.
2. HID report IDs, input/output report sizes and any padding.
3. Whether reports contain complete ACP frames, chunking, or another envelope.
4. The Windows I/O method (HID feature reports, interrupt, or vendor-specific).
5. ACK/read sequencing, reconnects, timeouts and exclusive access behavior.

## First connected milestone
- Capture descriptors using USBView or equivalent.
- Capture a **read-only** ACPWorkbench transaction with USBPcap/Wireshark if needed.
- Confirm transport using **one known read** (Guitar Chorus, 0x8F).
- Compare readback word count to fixture.
- Only then perform one user-confirmed bounded write, read back and restore original.
- Never run ACPWorkbench and BPControl against the device concurrently.
- No guesswork, brute force or speculative writes to unknown reports.

ESP32-S3 USB Host port must follow after Windows transport is proven.
