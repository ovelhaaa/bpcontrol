# M1A — Passive USB HID capture plan (Windows, BP1032)

## Ground truth (actual connected board)

- Vendor ID: `0x1235`; Product ID: `0x0003`.
- Product: `mvsilicon B1 usb audio`; manufacturer: `MV-SILICON`.
- Audio `MI_00`; consumer HID `MI_03` (usage page `0x000C`, usage `0x0001`).
- **Vendor-defined HID `MI_04`** (usage page `0xFF00`, usage `0x55AA`).
- Windows `HidP_GetCaps` for MI_04:
  - `InputReportByteLength = 257`
  - `OutputReportByteLength = 257`
  - `FeatureReportByteLength = 9`

These values include the 1-byte Windows report-ID slot, whether or not the device uses numbered report IDs. The HID report **capacity** is at most 256 input/output data bytes and 8 feature data bytes per declared maximum-sized report. `HIDP_CAPS` does **not** reveal report IDs, actual report descriptor, padded ACP byte offsets, or whether the transport uses Output, Feature, interrupt IN, or control transfers. We cannot assume byte 0 is `0x00` or that the ACP frame begins at offset 1.

Microsoft: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/hidpi/ns-hidpi-_hidp_caps

## Recommended experiment: passive observation of ACPWorkbench

**Do not send test writes or change firmware/drivers yet.** Use the already working ACPWorkbench to generate legal device traffic and capture it with Wireshark + USBPcap.

1. Make sure **BP1032** is connected, but leave any independent BPControl HID program closed. Use USBTreeView or Windows Device Manager to identify the USB controller/root hub containing `1235:0003`. Other connected devices, including ESP32-S3, may share that root hub.
2. If Wireshark/USBPcap is not installed, install from the official sources, with the USBPcap capture component enabled. Capturing USB on Windows installs a driver and may require elevated permissions or reboot. If you prefer not to install it, use USBTreeView to collect detailed HID descriptors first.
3. In Wireshark, select the **USBPcap** capture interface corresponding to the board's hub. Begin recording **before** ACPWorkbench is opened so that it includes a known initial read.
4. Open ACPWorkbench, wait for connection, optionally select **Guitar Chorus** once to request its parameters, then stop Wireshark promptly. **Do not edit any parameter** during this capture.
5. Locate the board's current USB address via observed device descriptor / product string and filter to that address. For many Wireshark/USBPcap versions, `usb.device_address == N` works. If multiple buses are captured, add `usb.bus_id == B` where supported. USB addresses may change after reconnecting.
6. Inspect URB Control / Interrupt IN/OUT payloads. Find an outbound ACP application read frame (e.g. `A5 5A 8F 00 16`) and the corresponding readback beginning `A5 5A 8F ... FF`. It may appear with report ID/padding or other encapsulation; **do not assume** the exact offset or that a single USB report contains one ACP frame.
7. Record the **direction**, transfer type (control/interrupt), endpoint/address, USB payload length, any report ID, the first 32-64 payload bytes, and the total number of reports used for one ACP frame. If a report is not recognized by Wireshark, note its raw bytes and inspect the surrounding URB.
8. Avoid uploading the full capture publicly: an entire USB root hub capture may include unrelated devices and sensitive keyboard traffic. Share only device-filtered, sanitized relevant frames or a short textual summary.

### Expected ACP *application* frames (not HID report layouts)

```text
Guitar Chorus read request:  A5 5A 8F 00 16
Firmware info read request:  A5 5A 00 00 16
System status read request:  A5 5A 02 00 16
Guitar Chorus readback:     A5 5A 8F LEN FF [16-bit little-endian words...] 16
```

ACPWorkbench's text logs confirm the application-layer frames. Only an actual USB capture will tell us their HID envelope.

## Acceptance criteria for Windows HID transport implementation

- Verified `MI_04` receives ACPWorkbench traffic, not just vendor-defined usage.
- Known USB report IDs and usable Windows buffer lengths.
- Verified direction and method for read/write transaction, including timeouts.
- A byte-exact fixture of one ACPWorkbench **read request and response**.
- Only then implement HID transaction transport in `src/bpcontrol/`, **read-only first**.
- Exclude `0xFD` persist/save, `0xFE` firmware upgrade, reset and reserved fields from normal control paths.

Wireshark reference: https://www.wireshark.org/docs/dfref/u/usb.html
USB capture guide: https://wiki.wireshark.org/CaptureSetup/USB
