"""Inspect Windows HID report capacities for BP1032 MI_04, without USB I/O.

This program only opens the HID collection with dwDesiredAccess=0 and reads
Windows HID preparsed metadata. It does not request input reports, write
output/feature reports, send ACP commands, or replace drivers.

Prerequisite: py -m pip install hidapi
Usage:        py tools/inspect_hid_caps.py
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys

VID = 0x1235
PID = 0x0003
EXPECTED_INTERFACE = 4
EXPECTED_USAGE_PAGE = 0xFF00
EXPECTED_USAGE = 0x55AA

FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
OPEN_EXISTING = 3
HIDP_STATUS_SUCCESS = 0x00110000


class HIDP_CAPS(ctypes.Structure):
    """Exact HIDP_CAPS layout from Windows SDK hidpi.h (64 bytes)."""

    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


def _as_win_path(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="strict")
    return value


def _get_caps(path: str) -> HIDP_CAPS:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    hid_dll = ctypes.WinDLL("hid", use_last_error=True)

    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    hid_dll.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    hid_dll.HidD_GetPreparsedData.restype = ctypes.c_ubyte
    hid_dll.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    hid_dll.HidD_FreePreparsedData.restype = ctypes.c_ubyte
    hid_dll.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
    hid_dll.HidP_GetCaps.restype = ctypes.c_long

    # Access=0: metadata access only. No ReadFile, WriteFile or HidD_SetFeature.
    handle = kernel32.CreateFileW(
        path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None, OPEN_EXISTING, 0, None,
    )
    if handle == ctypes.c_void_p(-1).value or handle is None:
        code = ctypes.get_last_error()
        raise OSError(code, f"CreateFileW metadata-only open failed (WinError {code})")

    preparsed = ctypes.c_void_p()
    try:
        if not hid_dll.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
            code = ctypes.get_last_error()
            raise OSError(code, f"HidD_GetPreparsedData failed (WinError {code})")
        try:
            caps = HIDP_CAPS()
            status = hid_dll.HidP_GetCaps(preparsed, ctypes.byref(caps))
            if status != HIDP_STATUS_SUCCESS:
                raise RuntimeError(f"HidP_GetCaps returned NTSTATUS 0x{status & 0xFFFFFFFF:08X}")
            return caps
        finally:
            hid_dll.HidD_FreePreparsedData(preparsed)
    finally:
        kernel32.CloseHandle(handle)


def main() -> int:
    if sys.platform != "win32":
        print("This tool requires Windows; no device operations performed.", file=sys.stderr)
        return 2
    try:
        import hid
    except ImportError:
        print("Install prerequisite: py -m pip install hidapi", file=sys.stderr)
        return 2

    devices = [
        item for item in hid.enumerate(VID, PID)
        if item.get("interface_number") == EXPECTED_INTERFACE
        and item.get("usage_page") == EXPECTED_USAGE_PAGE
        and item.get("usage") == EXPECTED_USAGE
    ]
    print(f"Matched {len(devices)} MI_04, usage 0xFF00/0x55AA collection(s) for 1235:0003.")
    if not devices:
        print("No matching collection; verify the BP1032 is connected.")
        return 1
    if ctypes.sizeof(HIDP_CAPS) != 64:
        print("Unexpected Windows HIDP_CAPS structure size; refusing metadata query.")
        return 3

    errors = 0
    for number, device in enumerate(devices, 1):
        print(f"\nCollection #{number}: {device.get('manufacturer_string')} / {device.get('product_string')}")
        try:
            caps = _get_caps(_as_win_path(device["path"]))
        except (OSError, ValueError, RuntimeError) as exc:
            errors += 1
            print(f"Could not obtain caps: {exc}")
            continue
        print(f"UsagePage               : 0x{caps.UsagePage:04X}")
        print(f"Usage                   : 0x{caps.Usage:04X}")
        print(f"InputReportByteLength   : {caps.InputReportByteLength}")
        print(f"OutputReportByteLength  : {caps.OutputReportByteLength}")
        print(f"FeatureReportByteLength : {caps.FeatureReportByteLength}")
        print("Windows report capacities include report-ID position; actual IDs are not revealed.")

    print("\nNo ACP bytes were transmitted. No report was read or written.")
    print("Device paths and serial numbers are intentionally not printed.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
