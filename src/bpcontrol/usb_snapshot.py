"""Bounded-use Windows HID session for *known read commands only*.

Requires authorization of exact observed BPxx firmware before any status/effect
query. The same open handle is used for a finite snapshot of 59 instances.
Never run without a parent-process deadline (tools/snapshot_windows.py).

USB: class control EP0; SET_REPORT Output / GET_REPORT Input; ID=0;
256 report data bytes; the Windows API buffer includes an extra zero ID slot.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from .acp import ACPError, ACPFrame, decode_frame, effect_command
from .device_info import parse_firmware_info
from .snapshot import INSTANCE_COUNT, require_observed_firmware
from .usb_hid import (
    HIDTransportError, API_REPORT_SIZE, WIRE_DATA_SIZE,
    GENERIC_READ, GENERIC_WRITE, FILE_SHARE_READ, FILE_SHARE_WRITE,
    OPEN_EXISTING, find_target_path, _win_error,
)

READ_OPCODES = frozenset((0x00, 0x02)) | frozenset(
    effect_command(i) for i in range(1, INSTANCE_COUNT + 1)
)


class WindowsSnapshotSession:
    def __init__(self):
        self._handle = None
        self._kernel32 = None
        self._hiddll = None
        self._firmware_ok = False
        self._read_count = 0

    def __enter__(self):
        if self._handle is not None:
            raise HIDTransportError("USB snapshot session already open")
        path = find_target_path()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        hid = ctypes.WinDLL("hid", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        hid.HidD_SetOutputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
        hid.HidD_SetOutputReport.restype = ctypes.c_ubyte
        hid.HidD_GetInputReport.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
        hid.HidD_GetInputReport.restype = ctypes.c_ubyte

        handle = kernel32.CreateFileW(
            path, GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None,
        )
        if handle in (None, ctypes.c_void_p(-1).value):
            raise _win_error("CreateFileW for BP1032 MI_04")
        self._handle, self._kernel32, self._hiddll = handle, kernel32, hid
        return self

    def __exit__(self, *_):
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None
        return False

    def query(self, command: int) -> ACPFrame:
        if self._handle is None:
            raise HIDTransportError("USB session is not open")
        if type(command) is not int or command not in READ_OPCODES:
            raise HIDTransportError("opcode is not on the strict read-only allowlist")
        if command != 0x00 and not self._firmware_ok:
            raise HIDTransportError("verify observed firmware BEFORE other queries")
        if self._read_count >= INSTANCE_COUNT + 2:
            raise HIDTransportError("bounded snapshot request limit exceeded")
        raw = ACPFrame(command, b"").to_bytes()
        output = (ctypes.c_ubyte * API_REPORT_SIZE).from_buffer_copy(
            b"\x00" + raw + bytes(WIRE_DATA_SIZE - len(raw))
        )
        if not self._hiddll.HidD_SetOutputReport(self._handle, output, API_REPORT_SIZE):
            raise _win_error(f"HidD_SetOutputReport 0x{command:02X}")
        self._read_count += 1
        incoming = (ctypes.c_ubyte * API_REPORT_SIZE)()
        incoming[0] = 0
        if not self._hiddll.HidD_GetInputReport(self._handle, incoming, API_REPORT_SIZE):
            raise _win_error(f"HidD_GetInputReport 0x{command:02X}")
        result = bytes(incoming)
        if result[0] != 0 or result[1:3] != b"\xA5\x5A":
            raise HIDTransportError("unexpected Report ID or ACP header")
        data = result[1:]
        size = 5 + data[3]
        if size > WIRE_DATA_SIZE or any(data[size:]):
            raise HIDTransportError("invalid ACP length or nonzero HID padding")
        try:
            frame = decode_frame(data[:size])
        except ACPError as exc:
            raise HIDTransportError(f"invalid ACP frame: {exc}") from exc
        if frame.command != command:
            raise HIDTransportError(
                f"reply command 0x{frame.command:02X} does not match 0x{command:02X}"
            )
        if not frame.payload:
            raise HIDTransportError("empty ACP reply payload")
        if command == 0x00 and len(frame.payload) != 7:
            raise HIDTransportError("unexpected firmware reply length")
        if command == 0x02 and len(frame.payload) != 10:
            raise HIDTransportError("unexpected system status reply length")
        if 0x81 <= command <= 0xBB and (
            frame.payload[0] != 0xFF or (len(frame.payload) - 1) % 2
        ):
            raise HIDTransportError("unexpected effect readback format")
        return frame

    def authorize_after_firmware(self, frame: ACPFrame):
        """Only the exact physical firmware observed can unlock effect queries."""
        info = parse_firmware_info(frame)
        require_observed_firmware(info)
        self._firmware_ok = True
        return info
