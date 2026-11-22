"""Windows HID EP0 transport for BP1032, restricted to one Chorus READ.

Based on owner-captured USBPcap: SET_REPORT(Output, id0, MI04) followed by
GET_REPORT(Input, id0, MI04). USB data is 256 bytes; Windows HID API buffers
are 257 bytes, with leading report-ID selection byte 0.

Only an explicitly invoked READ of command 0x8F is permitted. This sends a
SET_REPORT containing a *read request*, not an effect write. Never use for
unknown devices or while ACPWorkbench has MI_04 open.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import sys

from .acp import ACPError, decode_frame, decode_readback, encode_read

VID = 0x1235
PID = 0x0003
INTERFACE = 4
USAGE_PAGE = 0xFF00
USAGE = 0x55AA
MANUFACTURER = "MV-SILICON"
PRODUCT = "mvsilicon B1 usb audio"
API_REPORT_SIZE = 257
WIRE_DATA_SIZE = 256
CHORUS_INDEX = 15
CHORUS_COMMAND = 0x8F

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3


class HIDTransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChorusSnapshot:
    """Seven signed readback fields in the observed firmware's field order."""

    enable: int
    delay_length: int
    modulation_depth: int
    modulation_rate_raw: int
    feedback: int
    dry: int
    wet: int


def make_chorus_output_report() -> bytes:
    """Windows HID API format, not raw USB wire payload."""
    frame = encode_read(CHORUS_INDEX)
    assert frame == bytes.fromhex("A5 5A 8F 00 16")
    return b"\x00" + frame + bytes(WIRE_DATA_SIZE - len(frame))


def parse_chorus_input_report(api_report: bytes) -> ChorusSnapshot:
    """Strictly validate the ID slot, ACP length, command and zero-filled tail."""
    if len(api_report) != API_REPORT_SIZE:
        raise HIDTransportError(f"expected {API_REPORT_SIZE} API bytes, got {len(api_report)}")
    if api_report[0] != 0:
        raise HIDTransportError("unexpected Windows HID report-ID slot")
    payload = api_report[1:]
    if payload[:2] != b"\xA5\x5A":
        raise HIDTransportError("ACP header missing from USB data offset 0")
    frame_length = 5 + payload[3]
    if frame_length > WIRE_DATA_SIZE:
        raise HIDTransportError("ACP length exceeds HID report capacity")
    if any(payload[frame_length:]):
        raise HIDTransportError("nonzero bytes after ACP frame")
    try:
        frame = decode_frame(payload[:frame_length])
        if frame.command != CHORUS_COMMAND or len(frame.payload) != 15:
            raise HIDTransportError("unexpected command/length for Chorus readback")
        values = decode_readback(payload[:frame_length], CHORUS_INDEX)
    except ACPError as exc:
        raise HIDTransportError(f"invalid ACP reply: {exc}") from exc
    if len(values) != 7:
        raise HIDTransportError("wrong number of Chorus fields")
    return ChorusSnapshot(*values)


def find_target_path() -> str:
    """Enumerate only: match known collection identity, reject ambiguity."""
    if sys.platform != "win32":
        raise HIDTransportError("Windows is required for HID control transport")
    try:
        import hid
    except ImportError as exc:
        raise HIDTransportError("Install hidapi with: py -m pip install hidapi") from exc

    matches = [
        entry for entry in hid.enumerate(VID, PID)
        if entry.get("interface_number") == INTERFACE
        and entry.get("usage_page") == USAGE_PAGE
        and entry.get("usage") == USAGE
        and entry.get("manufacturer_string") == MANUFACTURER
        and entry.get("product_string") == PRODUCT
        and entry.get("release_number") == 0x0100
    ]
    if len(matches) != 1:
        raise HIDTransportError(
            f"Expected one verified BP1032 MI_04 HID collection, found {len(matches)}"
        )
    path = matches[0]["path"]
    return path.decode("utf-8") if isinstance(path, bytes) else path


def _win_error(label: str) -> HIDTransportError:
    code = ctypes.get_last_error()
    return HIDTransportError(f"{label} failed, WinError {code} (no retry)")


def read_guitar_chorus_once() -> ChorusSnapshot:
    """One active READ. Run in a killable child process to bound Win32 blocking."""
    path = find_target_path()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    hiddll = ctypes.WinDLL("hid", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    hiddll.HidD_SetOutputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    hiddll.HidD_SetOutputReport.restype = ctypes.c_ubyte
    hiddll.HidD_GetInputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    hiddll.HidD_GetInputReport.restype = ctypes.c_ubyte

    handle = kernel32.CreateFileW(
        path, GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None,
    )
    if handle in (None, ctypes.c_void_p(-1).value):
        raise _win_error("CreateFileW for MI_04")

    try:
        output = (ctypes.c_ubyte * API_REPORT_SIZE).from_buffer_copy(make_chorus_output_report())
        # This is one ACP read query, not a parameter write.
        if not hiddll.HidD_SetOutputReport(handle, output, API_REPORT_SIZE):
            raise _win_error("HidD_SetOutputReport")
        incoming = (ctypes.c_ubyte * API_REPORT_SIZE)()
        incoming[0] = 0
        if not hiddll.HidD_GetInputReport(handle, incoming, API_REPORT_SIZE):
            raise _win_error("HidD_GetInputReport")
        return parse_chorus_input_report(bytes(incoming))
    finally:
        kernel32.CloseHandle(handle)
