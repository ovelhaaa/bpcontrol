"""Read-only discovery of MVSilicon BP1032 HID collections.

Uses hidapi only for enumeration; deliberately DOES NOT open a device, send ACP
frames, read reports, or install/replace drivers.

Usage:
    python -m pip install hidapi
    python tools/inspect_hid.py
"""
from __future__ import annotations

import sys

VID = 0x1235
PID = 0x0003


def fmt_hex(value: object, width: int = 4) -> str:
    if isinstance(value, int):
        return f"0x{value:0{width}X}"
    return "unknown"


def iface_hint(path: object) -> str:
    """Look for MI_XX only; never output USB serials or unique Windows paths."""
    if isinstance(path, bytes):
        path_text = path.decode("utf-8", "replace")
    else:
        path_text = str(path or "")
    import re
    match = re.search(r"(?i)mi_([0-9a-f]{2})", path_text)
    return "MI_" + match.group(1).upper() if match else "not shown in HID path"


def main() -> int:
    try:
        import hid  # installed with: python -m pip install hidapi
    except ImportError:
        print("Missing dependency: python -m pip install hidapi", file=sys.stderr)
        return 2

    devices = hid.enumerate(VID, PID)
    print(f"Found {len(devices)} HID collection(s) for {VID:04X}:{PID:04X}.")
    print("This enumerates descriptors only; it does not open or modify devices.")

    for index, info in enumerate(devices, 1):
        usage_page = info.get("usage_page")
        vendor_defined = isinstance(usage_page, int) and 0xFF00 <= usage_page <= 0xFFFF
        print(f"\nHID collection {index}")
        print(f"  interface_number  : {info.get('interface_number', 'unknown')}")
        print(f"  path MI hint      : {iface_hint(info.get('path'))}")
        print(f"  usage_page        : {fmt_hex(usage_page)}" +
              (" (vendor-defined)" if vendor_defined else ""))
        print(f"  usage             : {fmt_hex(info.get('usage'))}")
        print(f"  manufacturer      : {info.get('manufacturer_string', 'unknown')}")
        print(f"  product           : {info.get('product_string', 'unknown')}")
        print(f"  release_number    : {fmt_hex(info.get('release_number'))}")

    if not devices:
        print("\nNo HID collection found. Check that the BP1032 is connected.")
    print("\nUnique device paths and serial numbers are intentionally omitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
