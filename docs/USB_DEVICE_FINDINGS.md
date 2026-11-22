# BP1032 USB discovery: Windows observations (2026-11-21)

## Confirmed from the owner's Device Manager event

The user reported a **Windows software audio endpoint**:

```text
SWD\MMDEVAPI\{0.0.0.00000000}.{3e4ce032-a22b-4d36-b3d3-17b49715fe9d}
Driver: audioendpoint.inf (Microsoft)
Parent: USB\VID_1235&PID_0003&MI_00\7&3551e31d&4&0000
```

Derived physical identifiers:
- VID: `0x1235`
- PID: `0x0003`
- Interface shown as parent: `MI_00`
- Connection displayed by ACPWorkbench: `mvsilicon B1 usb audio`

**Crucial distinction:** `SWD\MMDEVAPI\...` is an audio endpoint, *not* the HID interface used for ACP. `audioendpoint.inf` does not establish HID report details. `MI_00` is a USB interface number associated with that audio endpoint and must not be hard-coded as the ACP control interface.

## USB identifier conflict — independent public corroboration

A Linux kernel patch dated 2026-03-01, titled *ALSA: usb-audio: Deconflict VID between Focusrite Novation & MV-SILICON*, explicitly documents:
- `idVendor=1235, idProduct=0003`
- `Product: mvsilicon B1 usb audio`
- `Manufacturer: MV-SILICON`

Reference: https://lkml.iu.edu/2603.0/00457.html

The `0x1235` VID is registered to Focusrite/Novation; MV-SILICON-based devices can reuse this VID. **Never identify the target solely by VID/PID** when deciding whether to write. Check manufacturer/product strings, interface class and optionally a read-only ACP firmware identification. No claim is made that this specific physical board has the same serial as examples in the patch.

## Next diagnostic: Windows PnP tree (read-only)

With the BP1032 connected, run Windows PowerShell:

```powershell
Get-PnpDevice -PresentOnly |
  Where-Object { $_.InstanceId -match 'VID_1235&PID_0003' } |
  Select-Object Class, FriendlyName, InstanceId |
  Format-List
```

Look for `HID\VID_1235&PID_0003...` or `USB\VID_1235&PID_0003&MI_XX` entries. **Absence from the list does not prove HID is absent:** further descriptor inspection is warranted.

Then, if necessary, capture the descriptors using USBTreeView/USBView, identifying:
- Device `bDeviceClass`, manufacturer/product strings.
- All interfaces `bInterfaceNumber`, `bInterfaceClass`, `bInterfaceSubClass`, `bInterfaceProtocol`.
- HID report descriptor if present, endpoint directions/addresses and `wMaxPacketSize`.

Do not change Windows drivers, install WinUSB/libusb replacements, or run speculative writes merely to inspect the device. Keep ACPWorkbench closed when a future independent controller actually opens the USB interface.

## Status

- [x] Parent USB VID/PID discovered.
- [x] Audio endpoint on interface MI_00 identified.
- [ ] HID interface confirmed (number/class/endpoints unknown).
- [ ] Raw HID report descriptor or actual transfer captured.
- [ ] BPControl read-only USB communication tested.
