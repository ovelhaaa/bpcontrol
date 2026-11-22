"""Experimental M1F Chorus wet write-verify-restore, opt-in only.

No generic device writing is exposed: the sole writable ACP parameter is
Guitar Chorus instance 15 / command 0x8F / field 6, for a ONE-step change.
The Windows HID input ACK is based on physical USBPcap evidence:
256 report data bytes = 0x8F followed by 255 zero bytes.

The caller must run in a supervised worker process (see tools/probe_chorus_windows.py)
because Windows HidD_GetInputReport is synchronous and may block.
Never send ACP 0xFD/0xFE; never save to flash or retry a failed write.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass

from .acp import ACPError, encode_write
from .usb_hid import API_REPORT_SIZE, WIRE_DATA_SIZE, HIDTransportError, _win_error
from .usb_snapshot import WindowsSnapshotSession

CHORUS_COMMAND = 0x8F
CHORUS_INDEX = 15
WET_FIELD = 6
ACK_REPORT = b"\x00\x8F" + bytes(255)  # Windows HID API: ID=0 + 256 wire bytes.


def parse_wet_ack(report: bytes) -> None:
    """Reject any other report ID, effect ACK, report size, or nonzero padding."""
    if not isinstance(report, bytes) or report != ACK_REPORT:
        raise HIDTransportError(
            "wrong or malformed Chorus write ACK (expected ID0 + 0x8F + 255 zero bytes)"
        )


def chorus_values(frame) -> tuple[int, ...]:
    """Strictly decode the seven observed signed little-endian Chorus words."""
    if frame.command != CHORUS_COMMAND or len(frame.payload) != 15:
        raise HIDTransportError("Chorus reply must contain seven 16-bit fields")
    if frame.payload[0] != 0xFF:
        raise HIDTransportError("Chorus reply lacks 0xFF readback marker")
    p = frame.payload[1:]
    return tuple(
        int.from_bytes(p[i:i + 2], "little", signed=True)
        for i in range(0, len(p), 2)
    )


def plan_wet_step(wet: int) -> int:
    if type(wet) is not int or not 0 <= wet <= 100:
        raise HIDTransportError("Chorus wet must be integer 0..100")
    return wet - 1 if wet > 0 else wet + 1


class ChorusWetProbeSession(WindowsSnapshotSession):
    """Single-use session: 1 candidate write and at most 1 restoration write."""

    def __init__(self):
        super().__init__()
        self._baseline: tuple[int, ...] | None = None
        self._candidate: int | None = None
        self._phase = 0

    def read_chorus(self) -> tuple[int, ...]:
        return chorus_values(self.query(CHORUS_COMMAND))

    def arm_from_fresh_read(self, initial: tuple[int, ...], expected_wet: int) -> int:
        """Fail closed until the exact firmware and baseline have been verified."""
        if not self._firmware_ok or self._handle is None:
            raise HIDTransportError("verified firmware and open HID session required")
        if self._phase != 0 or self._baseline is not None:
            raise HIDTransportError("session was already armed")
        if type(expected_wet) is not int or not 0 <= expected_wet <= 100:
            raise HIDTransportError("expected wet must be an integer 0..100")
        if len(initial) != 7 or any(type(v) is not int for v in initial):
            raise HIDTransportError("expected exactly seven Chorus integers")
        if initial[WET_FIELD] != expected_wet:
            raise HIDTransportError(
                f"current wet={initial[WET_FIELD]}, expected={expected_wet}; NO WRITES"
            )
        self._baseline = tuple(initial)
        self._candidate = plan_wet_step(expected_wet)
        return self._candidate

    def _exchange_write(self, value: int) -> None:
        """One real SET_REPORT + GET_REPORT; ACK validation is exact."""
        frame = encode_write(CHORUS_INDEX, WET_FIELD, value)
        if len(frame) != 8 or frame[:5] != b"\xA5\x5A\x8F\x03\x06":
            raise HIDTransportError("unexpected Chorus write frame; refusing")
        raw = b"\x00" + frame + bytes(WIRE_DATA_SIZE - len(frame))
        outbound = (ctypes.c_ubyte * API_REPORT_SIZE).from_buffer_copy(raw)
        if not self._hiddll.HidD_SetOutputReport(self._handle, outbound, API_REPORT_SIZE):
            raise _win_error("HidD_SetOutputReport Chorus wet")
        incoming = (ctypes.c_ubyte * API_REPORT_SIZE)()
        incoming[0] = 0
        if not self._hiddll.HidD_GetInputReport(self._handle, incoming, API_REPORT_SIZE):
            raise _win_error("HidD_GetInputReport Chorus write ACK")
        parse_wet_ack(bytes(incoming))

    def send_candidate_once(self) -> None:
        if self._baseline is None or self._candidate is None or self._phase != 0:
            raise HIDTransportError("not armed or candidate already attempted")
        if not self._firmware_ok or self._handle is None:
            raise HIDTransportError("firmware/device verification required")
        # Mark before sending: even if SET_REPORT or ACK fails, device state
        # may already have changed; caller will attempt ONE restoration.
        self._phase = 1
        self._exchange_write(self._candidate)

    def send_restoration_once(self) -> None:
        if self._baseline is None or self._phase != 1:
            raise HIDTransportError("restoration requires one attempted candidate")
        if not self._firmware_ok or self._handle is None:
            raise HIDTransportError("firmware/device verification required")
        # At most one restoration write, even if the HID operation fails.
        self._phase = 2
        self._exchange_write(self._baseline[WET_FIELD])


@dataclass(frozen=True)
class ProbeResult:
    status: str
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
            "baseline": list(self.baseline) if self.baseline is not None else None,
            "candidate_wet": self.candidate,
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


def run_one_probe(session: ChorusWetProbeSession, expected_wet: int) -> ProbeResult:
    """Run ONE authorized probe. Caller owns the bounded HID session.

    On any error after candidate dispatch begins, attempt exactly ONE restore,
    then read back all seven fields. If recovery is unavailable, make no
    'restoration succeeded' claim.
    """
    initial = None
    candidate = None
    candidate_readback = None
    restoration_readback = None
    candidate_ack = False
    restore_ack = False
    restore_verified = False
    errors: list[str] = []

    # All preflight must complete BEFORE any mutating ACP frame.
    session.authorize_after_firmware(session.query(0x00))
    initial = session.read_chorus()
    candidate = session.arm_from_fresh_read(initial, expected_wet)
    # Minimize chances of another app or control changing Chorus before write.
    if session.read_chorus() != initial:
        raise HIDTransportError("Chorus changed during preflight; NO WRITES")

    try:
        try:
            session.send_candidate_once()
            candidate_ack = True
            candidate_readback = session.read_chorus()
            expected_after = list(initial)
            expected_after[WET_FIELD] = candidate
            if candidate_readback != tuple(expected_after):
                raise HIDTransportError(
                    f"candidate readback differs: expected {tuple(expected_after)}, "
                    f"got {candidate_readback}"
                )
        except Exception as exc:
            errors.append(f"candidate: {type(exc).__name__}: {exc}")
    finally:
        # A failed HID SET_REPORT or ACK does not prove no change occurred.
        # Attempt one restoration, never more than one; verify by fresh read.
        try:
            session.send_restoration_once()
            restore_ack = True
        except Exception as exc:
            errors.append(f"restore_ack: {type(exc).__name__}: {exc}")
        try:
            restoration_readback = session.read_chorus()
            restore_verified = restoration_readback == initial
            if not restore_verified:
                errors.append(
                    f"restore_readback: mismatch; expected {initial}, "
                    f"got {restoration_readback}"
                )
        except Exception as exc:
            errors.append(f"restore_readback: {type(exc).__name__}: {exc}")

    if candidate_ack and candidate_readback is not None and restore_ack and restore_verified and not errors:
        state = "PASS_RESTORED"
    elif restore_verified:
        state = "ERROR_BUT_RESTORED"
    else:
        state = "STATE_UNCERTAIN"
    return ProbeResult(
        status=state, baseline=initial, candidate=candidate,
        candidate_readback=candidate_readback,
        restoration_readback=restoration_readback,
        candidate_ack_valid=candidate_ack,
        restoration_ack_valid=restore_ack,
        restoration_verified=restore_verified,
        error_messages=tuple(errors),
    )
