# BP1032 USB discovery: Windows observations

## Device identity — confirmed by the owner

The BP1032 appears as a USB composite device with VID `0x1235` and PID `0x0003`.

| Windows interface | Reported device class / display name | Interpretation |
|---|---|---|
| `USB\\VID_1235&PID_0003&MI_00` | MEDIA — `mvsilicon B1 usb audio` | Audio interface |
| `HID\\VID_1235&PID_0003&MI_03` | HIDClass — HID-compliant consumer control device | Consumer control collection (likely playback/volume keys) |
| `HID\\VID_1235&PID_0003&MI_04` | HIDClass — HID-compliant vendor-defined device | **Top candidate for ACP protocol transport** |
| `USB\\VID_1235&PID_0003&MI_03` | HIDClass — USB Input Device | HID interface parent for MI_03 |
| `USB\\VID_1235&PID_0003&MI_04` | HIDClass — USB Input Device | HID interface parent for MI_04 |
| `USB\\VID_1235&PID_0003` | USB — USB Composite Device | Composite device parent |

Source: owner-reported `Get-PnpDevice -PresentOnly` output (2026-11-21, Windows).

**Interpretation warning:** An HID vendor-defined collection on MI_04 is an excellent lead, **not yet proof** that ACPWorkbench sends frames through it. We still need HID usage-page/report-length descriptors and ideally one captured ACPWorkbench USB transaction.

## Vendor ID collision

`0x1235` is assigned to Focusrite/Novation, but MV-SILICON-based devices have been independently documented reusing the same VID/PID. **Never decide to write based solely on VID/PID**; correlate strings and interfaces and validate firmware with a known *read-only* request first.

Background: https://lkml.iu.edu/2603.0/00457.html

## Next check — read-only HID enumerator

On Windows with the board connected:

```powershell
py -m pip install hidapi
py tools/inspect_hid.py
```

The script prints the HID collections, interface number if exposed, a sanitized path hint (e.g. MI_04), usage page, usage, manufacturer and product. It **never opens** the device, writes to it or prints unique device paths/serials.

Focus on MI_04. A vendor-defined HID usage page typically lies in `0xFF00..0xFFFF`, but an unknown usage-page number does not rule out this interface.

For actual report lengths, report IDs, endpoint addresses and packet layouts, inspect MI_04 in **USBTreeView/USBView** or capture a read-only ACPWorkbench transaction with **USBPcap/Wireshark**. Do not switch Windows drivers; HIDClass already enumerates.

## Safe Windows sequence

1. Enumerate only via script. Check that MI_04 is the vendor-defined collection and MI_03 is consumer control.
2. Collect detailed USB HID descriptors for MI_04: `bInterfaceClass`, HID report descriptor, report ID(s), Input/Output/Feature report lengths, IN/OUT endpoints, `wMaxPacketSize`.
3. If format is still unclear, capture only BP1032 traffic while ACPWorkbench performs one known read, e.g. `0x8F` Guitar Chorus. Save sanitized fixtures only.
4. After a **verified read-only transport**, implement `read_device_info()` before attempting guarded parameter writes.
5. Never run ACPWorkbench and BPControl against the same HID endpoint concurrently, never flash the DSP firmware or modify drivers merely for enumeration.

## Status

- [x] VID/PID: `0x1235:0x0003`.
- [x] Composite audio interface MI_00 recognized.
- [x] Consumer-control HID collection MI_03 recognized.
- [x] **Vendor-defined HID collection MI_04 recognized**.
- [x] Manufacturer `MV-SILICON`, product `mvsilicon B1 usb audio`, release `0x0100`, collection `MI_04` usage page `0xFF00`, usage `0x55AA` confirmed via hidapi enumeration.\n- [ ] HID report capacities / actual descriptor and report IDs identified.
- [ ] Verified USB ACP read transaction on MI_04.
- [ ] PC read-only BPControl transport implemented.

## Next result — hidapi enumeration supplied by owner

```text
Found 2 HID collection(s) for 1235:0003.
MI_03: UsagePage=0x000C, Usage=0x0001,
       Manufacturer=MV-SILICON, Product=mvsilicon B1 usb audio,
       release=0x0100
MI_04: UsagePage=0xFF00 (vendor-defined), Usage=0x55AA,
       Manufacturer=MV-SILICON, Product=mvsilicon B1 usb audio,
       release=0x0100
```

This strongly isolates `MI_04` as ACP transport candidate. The `0x55AA` usage **does not prove** payload framing, report IDs or report sizes. Do not mistake it for the two-byte `A5 5A` ACP frame header.

### Windows report capacity probe (safe)

```powershell
git pull
py tools/inspect_hid_caps.py
```

The second script uses Windows `HidD_GetPreparsedData` and `HidP_GetCaps`, opening the HID collection with desired access **zero**. It prints `InputReportByteLength`, `OutputReportByteLength` and `FeatureReportByteLength` without requesting or sending USB reports. This establishes **capacities**, not report IDs or the raw HID descriptor. Exact sizes, HID report IDs, endpoint transport, and ACP packet framing may require a passive ACPWorkbench USBPcap trace.

Windows API reference: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/hidpi/ns-hidpi-_hidp_caps
