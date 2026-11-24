"""Experimental M1K-B Harmonic Exciter (0x9D) write-verify-restore, opt-in only.

Only Harmonic Exciter instance 29 / command 0x9D fields 1 (cutoff), 2 (dry),
and 3 (wet) are supported for a single reversible step, based on the M1K-A
passive USBPcap evidence (bare 0x9D zero-padded 256-byte HID ACK).

The caller must run in a supervised worker process (see
tools/probe_exciter_windows.py) because Windows HidD_GetInputReport is
synchronous and may block. Never send ACP 0xFD/0xFE; never save to flash
or retry a failed write.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass

from .acp import encode_write
from .exciter_evidence import (
    EXCITER_COMMAND,
    EXCITER_FIELD_COUNT,
    EXCITER_INDEX,
    EXCITER_OPERATOR_REPORTED_MIN_CUTOFF_HZ,
    EXCITER_SDK_BP1048_CUTOFF_RANGE,
)
from .usb_hid import API_REPORT_SIZE, WIRE_DATA_SIZE, HIDTransportError, _win_error
from .usb_snapshot import WindowsSnapshotSession

EXCITER_ACK_REPORT = b"\x00\x9D" + bytes(255)  # Windows HID API: ID=0 + 256 wire bytes.

PROBEABLE_EXCITER_FIELDS: dict[str, int] = {
    "cutoff": 1,
    "dry": 2,
    "wet": 3,
}


def parse_exciter_ack(report: bytes) -> None:
    """Reject any other report ID, effect ACK, report size, or nonzero padding."""
    if not isinstance(report, bytes) or report != EXCITER_ACK_REPORT:
        raise HIDTransportError(
            "wrong or malformed Exciter write ACK (expected ID0 + 0x9D + 255 zero bytes)"
        )


def exciter_values(frame) -> tuple[int, ...]:
    """Strictly decode the four observed signed little-endian Exciter words."""
    if frame.command != EXCITER_COMMAND or len(frame.payload) != 1 + 2 * EXCITER_FIELD_COUNT:
        raise HIDTransportError("Exciter reply must contain four 16-bit fields")
    if frame.payload[0] != 0xFF:
        raise HIDTransportError("Exciter reply lacks 0xFF readback marker")
    p = frame.payload[1:]
    return tuple(
        int.from_bytes(p[i:i + 2], "little", signed=True)
        for i in range(0, len(p), 2)
    )


def plan_exciter_step(field_name: str, current: int) -> int:
    """Compute one small reversible step within conservative physical/SDK bounds."""
    if field_name not in PROBEABLE_EXCITER_FIELDS:
        raise HIDTransportError(f"Unsupported Exciter probe field: {field_name}")
    if type(current) is not int:
        raise HIDTransportError("Exciter field value must be an integer")
    if field_name == "cutoff":
        low = EXCITER_OPERATOR_REPORTED_MIN_CUTOFF_HZ
        high = EXCITER_SDK_BP1048_CUTOFF_RANGE[1]
        if not low <= current <= high:
            raise HIDTransportError(f"Exciter cutoff must be integer {low}..{high}")
        return current + 100 if current <= high - 100 else current - 100
    if not 0 <= current <= 100:
        raise HIDTransportError(f"Exciter {field_name} must be integer 0..100")
    return current - 1 if current > 0 else current + 1


class ExciterProbeSession(WindowsSnapshotSession):
    """Single-use session: 1 candidate write and at most 1 restoration write."""

    def __init__(self):
        super().__init__()
        self._baseline: tuple[int, ...] | None = None
        self._field_name: str | None = None
        self._field_index: int | None = None
        self._candidate: int | None = None
        self._phase = 0

    def read_exciter(self) -> tuple[int, ...]:
        return exciter_values(self.query(EXCITER_COMMAND))

    def arm_from_fresh_read(
        self, initial: tuple[int, ...], field_name: str, expected_value: int
    ) -> int:
        """Fail closed until the exact firmware and baseline have been verified."""
        if not self._firmware_ok or self._handle is None:
            raise HIDTransportError("verified firmware and open HID session required")
        if self._phase != 0 or self._baseline is not None:
            raise HIDTransportError("session was already armed")
        if field_name not in PROBEABLE_EXCITER_FIELDS:
            raise HIDTransportError(f"Unsupported Exciter probe field: {field_name}")
        if len(initial) != EXCITER_FIELD_COUNT or any(type(v) is not int for v in initial):
            raise HIDTransportError("expected exactly four Exciter integers")
        field_index = PROBEABLE_EXCITER_FIELDS[field_name]
        candidate = plan_exciter_step(field_name, expected_value)
        if initial[field_index] != expected_value:
            raise HIDTransportError(
                f"current {field_name}={initial[field_index]}, "
                f"expected={expected_value}; NO WRITES"
            )
        self._baseline = tuple(initial)
        self._field_name = field_name
        self._field_index = field_index
        self._candidate = candidate
        return candidate

    def _exchange_write(self, field_index: int, value: int) -> None:
        """One real SET_REPORT + GET_REPORT; ACK validation is exact."""
        if field_index not in PROBEABLE_EXCITER_FIELDS.values():
            raise HIDTransportError("unexpected Exciter field index; refusing")
        frame = encode_write(EXCITER_INDEX, field_index, value)
        if len(frame) != 8 or frame[:4] != b"\xA5\x5A\x9D\x03" or frame[4] != field_index:
            raise HIDTransportError("unexpected Exciter write frame; refusing")
        raw = b"\x00" + frame + bytes(WIRE_DATA_SIZE - len(frame))
        outbound = (ctypes.c_ubyte * API_REPORT_SIZE).from_buffer_copy(raw)
        if not self._hiddll.HidD_SetOutputReport(self._handle, outbound, API_REPORT_SIZE):
            raise _win_error(f"HidD_SetOutputReport Exciter field {field_index}")
        incoming = (ctypes.c_ubyte * API_REPORT_SIZE)()
        incoming[0] = 0
        if not self._hiddll.HidD_GetInputReport(self._handle, incoming, API_REPORT_SIZE):
            raise _win_error(f"HidD_GetInputReport Exciter write ACK field {field_index}")
        parse_exciter_ack(bytes(incoming))

    def send_candidate_once(self) -> None:
        if (
            self._baseline is None
            or self._field_index is None
            or self._candidate is None
            or self._phase != 0
        ):
            raise HIDTransportError("not armed or candidate already attempted")
        if not self._firmware_ok or self._handle is None:
            raise HIDTransportError("firmware/device verification required")
        self._phase = 1
        self._exchange_write(self._field_index, self._candidate)

    def send_restoration_once(self) -> None:
        if self._baseline is None or self._field_index is None or self._phase != 1:
            raise HIDTransportError("restoration requires one attempted candidate")
        if not self._firmware_ok or self._handle is None:
            raise HIDTransportError("firmware/device verification required")
        self._phase = 2
        self._exchange_write(self._field_index, self._baseline[self._field_index])


@dataclass(frozen=True)
class ExciterProbeResult:
    status: str
    field_name: str
    field_index: int
    baseline: tuple[int, ...] | None
    candidate: int | None
    candidate_readback: tuple[int, ...] | None
    restoration_readback: tuple[int, ...] | None
    candidate_ack_valid: bool
    restoration_ack_valid: bool
    restoration_verified: bool
    error_messages: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "command": f"0x{EXCITER_COMMAND:02X}",
            "field_name": self.field_name,
            "field_index": self.field_index,
            "baseline": list(self.baseline) if self.baseline is not None else None,
            "candidate_value": self.candidate,
            "candidate_readback": (
                list(self.candidate_readback) if self.candidate_readback is not None else None
            ),
            "restoration_readback": (
                list(self.restoration_readback) if self.restoration_readback is not None else None
            ),
            "candidate_ack_valid": self.candidate_ack_valid,
            "restoration_ack_valid": self.restoration_ack_valid,
            "restoration_verified": self.restoration_verified,
            "errors": list(self.error_messages),
        }


def run_one_exciter_probe(
    session: ExciterProbeSession, field_name: str, expected_value: int
) -> ExciterProbeResult:
    """Run ONE authorized Exciter probe with double preflight and single restore."""
    if field_name not in PROBEABLE_EXCITER_FIELDS:
        raise HIDTransportError(f"Unsupported Exciter probe field: {field_name}")
    field_index = PROBEABLE_EXCITER_FIELDS[field_name]
    initial = None
    candidate = None
    candidate_readback = None
    restoration_readback = None
    candidate_ack = False
    restore_ack = False
    restore_verified = False
    errors: list[str] = []

    session.authorize_after_firmware(session.query(0x00))
    initial = session.read_exciter()
    candidate = session.arm_from_fresh_read(initial, field_name, expected_value)
    if session.read_exciter() != initial:
        raise HIDTransportError("Exciter changed during preflight; NO WRITES")

    try:
        try:
            session.send_candidate_once()
            candidate_ack = True
            candidate_readback = session.read_exciter()
            expected_after = list(initial)
            expected_after[field_index] = candidate
            if candidate_readback != tuple(expected_after):
                raise HIDTransportError(
                    f"candidate readback differs: expected {tuple(expected_after)}, "
                    f"got {candidate_readback}"
                )
        except Exception as exc:
            errors.append(f"candidate: {type(exc).__name__}: {exc}")
    finally:
        try:
            session.send_restoration_once()
            restore_ack = True
        except Exception as exc:
            errors.append(f"restore_ack: {type(exc).__name__}: {exc}")
        try:
            restoration_readback = session.read_exciter()
            restore_verified = restoration_readback == initial
            if not restore_verified:
                errors.append(
                    f"restore_readback: mismatch; expected {initial}, "
                    f"got {restoration_readback}"
                )
        except Exception as exc:
            errors.append(f"restore_readback: {type(exc).__name__}: {exc}")

    if (
        candidate_ack
        and candidate_readback is not None
        and restore_ack
        and restore_verified
        and not errors
    ):
        state = "PASS_RESTORED"
    elif restore_verified:
        state = "ERROR_BUT_RESTORED"
    else:
        state = "STATE_UNCERTAIN"
    return ExciterProbeResult(
        status=state,
        field_name=field_name,
        field_index=field_index,
        baseline=initial,
        candidate=candidate,
        candidate_readback=candidate_readback,
        restoration_readback=restoration_readback,
        candidate_ack_valid=candidate_ack,
        restoration_ack_valid=restore_ack,
        restoration_verified=restore_verified,
        error_messages=tuple(errors),
    )
