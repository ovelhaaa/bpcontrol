# BPControl roadmap — USB-first

## Hardware constraint (confirmed by owner)

The user's BP1032 board exposes **no accessible UART pins**. The working ACPWorkbench connection is through the board's USB interface. Therefore **USB is the primary control path**. Do not require soldering wires, hardware modifications, a firmware flash, or inaccessible UART/I2C connections as part of the MVP. If alternative interfaces are discovered later, treat them only as optional.

The ACPWorkbench manual documents USB HID for PC communication, but the **actual VID/PID, HID interface, report ID, USB report length, endpoint, padding, and transport framing remain unverified** for this specific board. Do not claim raw application ACP frames can be sent to the USB device as-is.

## M0 — ACP application protocol (offline)
- [x] ACP encode/decode including signed 16-bit words.
- [x] Six observed effect schemas and packet fixtures; offline CLI and unit tests.
- [x] Review owner-supplied official ACPWorkbench manual, V2.40.0 communication specification and exported INI.
- [ ] Incorporate the 59 instance effect catalog, 0x02 status parsing, and documented parameter limits.
- [ ] Correct Echo quality mode (0..2); reconcile Chorus rate scaling vs UI evidence.

## M1A — Windows USB discovery (read-only, no reflash)
- [ ] Capture USB VID:PID, device/configuration/interface and HID descriptors using USBView, UsbTreeView, or Windows device information.
- [ ] Identify whether device is USB composite (audio plus HID), which interface ACPWorkbench actually opens, and whether native Windows drivers already claim it.
- [ ] Capture **one read-only ACPWorkbench transaction** with USBPcap/Wireshark if descriptors alone do not establish report IDs, padding and chunking.
- [ ] Save sanitized descriptor and transaction fixtures. Avoid including other USB devices' unrelated/private traffic in the repository.
- [ ] Implement a read-only PC transport after the above is verified: request firmware info `0x00`, system status `0x02`, then one mapped effect read.
- [ ] Timeouts, cancellation, reconnect detection, clear errors and test fakes. Do not open ACPWorkbench simultaneously.

## M1B — Safe controls
- [ ] Guarded, user-approved write on a known parameter, with readback verification, rollback to prior value and safe interruption behavior.
- [ ] Never emit `0xFD` persist/save, `0xFE` firmware upgrade, factory reset or unknown/reserved writes in the default transport.
- [ ] Acknowledge application-layer ACK is not proof of persistent configuration.
- [ ] Introduce local presets only after reliable read/write is proven.

## M2 — UI and resource management
- [ ] Desktop editor for the documented effects, with bypass, guarded ranges, preset import/export.
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

**Now:** ACP application-layer traffic is known; USB report transport is not. The next concrete input is a USB descriptor capture (VID/PID, interfaces, endpoints, HID report descriptor) from the device connected to Windows.

Do not claim a successful USB/MIDI/audio implementation until demonstrated on the physical board.
