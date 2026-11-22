"""M1G: exact-state single-step Chorus wet editor, with conservative recovery.

Only Guitar Chorus 0x8F field 6 is writable. This module never saves to
flash or exposes generic ACP writes. The graphical UI must request a
fresh manual read, stage numeric drafts locally, and confirm one Apply.

Unlike M1F, a SUCCESSFUL Apply retains the new volatile value until
the user explicitly undoes it. An unsuccessful write is followed by
ONE restoration attempt and verification of all seven Chorus fields.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .usb_chorus_probe import ChorusWetProbeSession, WET_FIELD
from .usb_hid import HIDTransportError


def parse_wet_draft(draft: str) -> int:
    """Only complete ASCII decimal integers 0..100 (no partial, signs, floats)."""
    if type(draft) is not str or re.fullmatch(r"[0-9]{1,3}", draft) is None:
        raise ValueError("Wet must be a complete decimal integer from 0 to 100")
    value = int(draft)
    if not 0 <= value <= 100:
        raise ValueError("Wet must be between 0 and 100")
    return value


def validate_editor_target(expected: tuple[int, ...], target: int) -> None:
    if (type(expected) is not tuple or len(expected) != 7
            or any(type(value) is not int or not -32768 <= value <= 32767
                   for value in expected)):
        raise ValueError("Expected exactly seven signed 16-bit Chorus fields")
    current = expected[WET_FIELD]
    if not 0 <= current <= 100:
        raise ValueError("Current wet outside known 0..100 range")
    if type(target) is not int or not 0 <= target <= 100:
        raise ValueError("Target wet must be an integer 0..100")
    if abs(target - current) != 1:
        raise ValueError("M1G allows exactly ONE-point changes only")


class ChorusEditorSession(ChorusWetProbeSession):
    def arm_editor_target(
        self, initial: tuple[int, ...], expected: tuple[int, ...], target: int
    ) -> None:
        """No device mutation: full-state equality + one-point boundary gate."""
        validate_editor_target(expected, target)
        if initial != expected:
            raise HIDTransportError("Chorus differs from last manual read; NO WRITE")
        self.arm_from_fresh_read(initial, expected[WET_FIELD])
        self._candidate = target  # validated ±1, unlike M1F's fixed decrement


@dataclass(frozen=True)
class EditorResult:
    status: str
    initial: tuple[int, ...] | None
    target: int
    applied_readback: tuple[int, ...] | None
    restoration_readback: tuple[int, ...] | None
    candidate_ack_valid: bool
    restoration_ack_valid: bool
    restoration_verified: bool
    errors: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "initial": list(self.initial) if self.initial is not None else None,
            "target": self.target,
            "applied_readback": (
                list(self.applied_readback) if self.applied_readback is not None else None
            ),
            "restoration_readback": (
                list(self.restoration_readback)
                if self.restoration_readback is not None else None
            ),
            "candidate_ack_valid": self.candidate_ack_valid,
            "restoration_ack_valid": self.restoration_ack_valid,
            "restoration_verified": self.restoration_verified,
            "errors": list(self.errors),
        }


def read_editor_chorus(session: ChorusEditorSession) -> tuple[int, ...]:
    session.authorize_after_firmware(session.query(0x00))
    values = session.read_chorus()
    if len(values) != 7 or not 0 <= values[WET_FIELD] <= 100:
        raise HIDTransportError("Invalid current Chorus wet value; no writes")
    return values


def apply_one_editor_step(
    session: ChorusEditorSession, expected: tuple[int, ...], target: int
) -> EditorResult:
    """Execute one authorized ±1 edit (not M1F's temporary demo).

    Read firmware + full seven-field state twice. If any preflight condition
    differs, raise before the first write. After dispatch, never retry the
    candidate; on error attempt one recovery write and final full readback.
    """
    validate_editor_target(expected, target)

    session.authorize_after_firmware(session.query(0x00))
    current = session.read_chorus()
    session.arm_editor_target(current, expected, target)
    if session.read_chorus() != expected:
        raise HIDTransportError("Chorus state changed during preflight; NO WRITE")

    applied = None
    restored = None
    candidate_ack = False
    restore_ack = False
    restore_verified = False
    errors = []

    try:
        session.send_candidate_once()
        candidate_ack = True
        applied = session.read_chorus()
        should = list(expected)
        should[WET_FIELD] = target
        if applied != tuple(should):
            raise HIDTransportError(
                f"Applied readback mismatch: expected {tuple(should)}, got {applied}"
            )
        return EditorResult(
            status="APPLIED_VERIFIED", initial=expected, target=target,
            applied_readback=applied, restoration_readback=None,
            candidate_ack_valid=True, restoration_ack_valid=False,
            restoration_verified=False, errors=(),
        )
    except Exception as exc:
        errors.append(f"apply: {type(exc).__name__}: {exc}")

    # The candidate might have changed the DSP even if its ACK was lost.
    # Do not perform another candidate write. Restore once, then read once.
    try:
        session.send_restoration_once()
        restore_ack = True
    except Exception as exc:
        errors.append(f"restore: {type(exc).__name__}: {exc}")
    try:
        restored = session.read_chorus()
        restore_verified = restored == expected
        if not restore_verified:
            errors.append(
                f"restore readback mismatch: expected {expected}, got {restored}"
            )
    except Exception as exc:
        errors.append(f"restore readback: {type(exc).__name__}: {exc}")

    return EditorResult(
        status="ERROR_BUT_RESTORED" if restore_verified else "STATE_UNCERTAIN",
        initial=expected, target=target, applied_readback=applied,
        restoration_readback=restored,
        candidate_ack_valid=candidate_ack,
        restoration_ack_valid=restore_ack,
        restoration_verified=restore_verified, errors=tuple(errors),
    )
