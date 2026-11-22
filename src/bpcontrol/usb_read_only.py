"""Windows-only BP1032 HID read-only probes for firmware and runtime status.

Uses proven MI_04 EP0 HID Control SET_REPORT(Output, ID0) + GET_REPORT(Input, ID0).
Only zero-payload application ACP READ commands 0x00 and 0x02 are allowed.
A successful HID SET_REPORT is *not* a parameter write in these transactions.

These synchronous Win32 APIs must run in a killable child process: see
tools/read_info_windows.py. No retries, writes, save (0xFD), upgrade (0xFE).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from .acp import ACPError, ACPFrame, decode_frame
from .usb_hid import (
    API_REPORT_SIZE, WIRE_DATA_SIZE, HIDTransportError,
    GENERIC_READ, GENERIC_WRITE, FILE_SHARE_READ, FILE_SHARE_WRITE,
    OPEN_EXISTING, find_target_path, _win_error,
)

READ_ONLY_COMMANDS = {
    0x00: "firmware",
    0x02: "status",
}


def _allowed(command: int) -> None:
    if type(command) is not int or command not in READ_ONLY_COMMANDS:
        raise HIDTransportError(
            "Only known zero-payload firmware (0x00) and status (0x02) reads are allowed"
        )


def make_read_output_report(command: int) -> bytes:
    """Return 257-byte Windows HID API buffer: report ID 0 + ACP + zeros."""
    _allowed(command)
    query = ACPFrame(command, b"").to_bytes()
    return b"\x00" + query + bytes(WIRE_DATA_SIZE - len(query))


def parse_read_input_report(api_report: bytes, command: int) -> ACPFrame:
    """Reject wrong ID/command, malformed ACP framing or nonzero padding."""
    _allowed(command)
    if len(api_report) != API_REPORT_SIZE:
        raise HIDTransportError(f"expected {API_REPORT_SIZE} API bytes, got {len(api_report)}")
    if api_report[0] != 0:
        raise HIDTransportError("unexpected HID report ID")
    data = api_report[1:]
    if data[:2] != b"\xA5\x5A":
        raise HIDTransportError("ACP header absent from HID data offset zero")
    length = 5 + data[3]
    if length > WIRE_DATA_SIZE:
        raise HIDTransportError("ACP frame length exceeds 256 bytes")
    if any(data[length:]):
        raise HIDTransportError("HID padding contains nonzero bytes")
    try:
        frame = decode_frame(data[:length])
    except ACPError as exc:
        raise HIDTransportError(f"invalid ACP framing: {exc}") from exc
    if frame.command != command:
        raise HIDTransportError("unexpected ACP command in reply")
    if not frame.payload:
        raise HIDTransportError("empty ACP reply payload")
    if command == 0x00 and len(frame.payload) != 7:
        raise HIDTransportError("unexpected firmware reply size; expected 7 payload bytes")
    return frame


def read_info_once(command: int) -> ACPFrame:
    """Perform one ACTIVE read query. Never invoke without a bounded supervisor."""
    _allowed(command)
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
    hiddll.HidD_SetOutputReport.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG
    ]
    hiddll.HidD_SetOutputReport.restype = ctypes.c_ubyte
    hiddll.HidD_GetInputReport.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG
    ]
    hiddll.HidD_GetInputReport.restype = ctypes.c_ubyte

    handle = kernel32.CreateFileW(
        path, GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None,
    )
    if handle in (None, ctypes.c_void_p(-1).value):
        raise _win_error("CreateFileW for MI_04")
    try:
        outbound = (ctypes.c_ubyte * API_REPORT_SIZE).from_buffer_copy(
            make_read_output_report(command)
        )
        if not hiddll.HidD_SetOutputReport(handle, outbound, API_REPORT_SIZE):
            raise _win_error("HidD_SetOutputReport")
        inbound = (ctypes.c_ubyte * API_REPORT_SIZE)()
        inbound[0] = 0
        if not hiddll.HidD_GetInputReport(handle, inbound, API_REPORT_SIZE):
            raise _win_error("HidD_GetInputReport")
        return parse_read_input_report(bytes(inbound), command)
    finally:
        kernel32.CloseHandle(handle)
