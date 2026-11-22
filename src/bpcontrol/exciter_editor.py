"""M1K-A offline-only staged Harmonic Exciter (0x9D) editor prototype.

No HID, USB, tkinter, or flash-save functionality is imported or enabled here.
`EXCITER_LIVE_WRITE_ENABLED` is hardcoded to False. This module only parses
local staged text drafts, validates candidate values against documented/reported
ranges, generates offline ACP preview bytes, and tracks local in-memory
staged history / undo without ever touching hardware.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .acp import ACPFrame
from .exciter_evidence import (
    EXCITER_AUDIT_BY_KEY,
    EXCITER_COMMAND,
    EXCITER_OPERATOR_REPORTED_MIN_CUTOFF_HZ,
    EXCITER_SDK_BP1048_CUTOFF_RANGE,
)

EXCITER_LIVE_WRITE_ENABLED = False

EXCITER_STAGED_BOUNDS: dict[str, tuple[int, int]] = {
    "enable": (0, 1),
    # Reported ACPWorkbench minimum 1000 Hz matches BP1048 SDK exciter.h;
    # V2.40 lists 300 Hz. Prototype uses 1000..10000 Hz conservatively.
    "cutoff_frequency": (
        EXCITER_OPERATOR_REPORTED_MIN_CUTOFF_HZ,
        EXCITER_SDK_BP1048_CUTOFF_RANGE[1],
    ),
    "dry": (0, 100),
    "wet": (0, 100),
}


def parse_exciter_draft(field_key: str, draft: str) -> int:
    """Parse a complete ASCII integer draft locally; reject partials/floats/signs."""
    if field_key not in EXCITER_STAGED_BOUNDS:
        raise ValueError(f"Unsupported Exciter field: {field_key}")
    if type(draft) is not str or re.fullmatch(r"[0-9]{1,5}", draft) is None:
        raise ValueError("Draft must be a complete non-negative decimal integer")
    value = int(draft)
    low, high = EXCITER_STAGED_BOUNDS[field_key]
    if not low <= value <= high:
        raise ValueError(f"{field_key} must be between {low} and {high}")
    return value


def build_exciter_preview_hex(field_key: str, target: int) -> str:
    """Build an offline-only ACP 0x9D write packet hex preview (never sent)."""
    if field_key not in EXCITER_AUDIT_BY_KEY:
        raise ValueError(f"Unsupported Exciter field: {field_key}")
    low, high = EXCITER_STAGED_BOUNDS[field_key]
    if type(target) is not int or not low <= target <= high:
        raise ValueError(f"{field_key} target {target!r} outside {low}..{high}")
    field_index = EXCITER_AUDIT_BY_KEY[field_key].index
    payload = bytes([field_index]) + target.to_bytes(2, "little", signed=True)
    return ACPFrame(EXCITER_COMMAND, payload).to_bytes().hex(" ").upper()


@dataclass(frozen=True)
class ExciterDraftView:
    field_key: str
    state: str
    summary: str
    target: int | None = None
    delta: int | None = None
    can_stage_offline: bool = False
    live_write_blocked: bool = True
    acp_preview_hex: str | None = None


def assess_exciter_draft(
    field_key: str,
    draft: str,
    current_values: tuple[int, int, int, int] | None,
) -> ExciterDraftView:
    """Evaluate a local staged draft without touching USB."""
    if field_key not in EXCITER_AUDIT_BY_KEY:
        return ExciterDraftView(
            field_key=field_key,
            state="unknown_field",
            summary=f"Campo desconhecido: {field_key}",
        )
    if current_values is None or len(current_values) != 4:
        return ExciterDraftView(
            field_key=field_key,
            state="need_baseline",
            summary="Carregue um baseline offline/snapshot antes de preparar rascunho",
        )
    if not isinstance(draft, str) or not draft.strip():
        low, high = EXCITER_STAGED_BOUNDS[field_key]
        return ExciterDraftView(
            field_key=field_key,
            state="empty",
            summary=f"Digite um inteiro completo entre {low} e {high}",
        )
    try:
        target = parse_exciter_draft(field_key, draft.strip())
    except ValueError as exc:
        return ExciterDraftView(
            field_key=field_key,
            state="invalid",
            summary=f"Rascunho inválido: {exc}",
        )
    field_index = EXCITER_AUDIT_BY_KEY[field_key].index
    current = current_values[field_index]
    delta = target - current
    if delta == 0:
        return ExciterDraftView(
            field_key=field_key,
            state="unchanged",
            summary="Sem alteração pendente (offline)",
            target=target,
            delta=0,
        )
    preview_hex = build_exciter_preview_hex(field_key, target)
    return ExciterDraftView(
        field_key=field_key,
        state="ready_offline",
        summary=(
            f"Stage offline pronto: {field_key} {current} → {target} ({delta:+d}) "
            "[USB bloqueado em M1K-A]"
        ),
        target=target,
        delta=delta,
        can_stage_offline=True,
        live_write_blocked=True,
        acp_preview_hex=preview_hex,
    )


class ExciterOfflineSession:
    """In-memory staged Exciter editor prototype. Refuses all live USB writes."""

    def __init__(self, initial_values: tuple[int, int, int, int] = (1, 1000, 80, 50)) -> None:
        if (
            type(initial_values) is not tuple
            or len(initial_values) != 4
            or any(type(v) is not int or not -32768 <= v <= 32767 for v in initial_values)
        ):
            raise ValueError("Exciter baseline must be four signed 16-bit integers")
        self._baseline = initial_values
        self._current = initial_values
        self._history: list[tuple[str, int, int, str]] = []

    @property
    def baseline(self) -> tuple[int, int, int, int]:
        return self._baseline

    @property
    def current(self) -> tuple[int, int, int, int]:
        return self._current

    @property
    def history(self) -> tuple[tuple[str, int, int, str], ...]:
        return tuple(self._history)

    def stage_apply(self, field_key: str, draft: str) -> ExciterDraftView:
        """Apply a validated draft to local in-memory state ONLY (never USB)."""
        view = assess_exciter_draft(field_key, draft, self._current)
        if not view.can_stage_offline or view.target is None or view.acp_preview_hex is None:
            raise ValueError(view.summary)
        idx = EXCITER_AUDIT_BY_KEY[field_key].index
        previous = self._current[idx]
        updated = list(self._current)
        updated[idx] = view.target
        self._current = tuple(updated)  # type: ignore[assignment]
        self._history.append((field_key, previous, view.target, view.acp_preview_hex))
        return view

    def stage_undo(self) -> tuple[str, int, int]:
        """Revert the last local staged edit in memory."""
        if not self._history:
            raise ValueError("Nenhuma alteração staged para desfazer")
        field_key, previous, target, _ = self._history.pop()
        idx = EXCITER_AUDIT_BY_KEY[field_key].index
        updated = list(self._current)
        updated[idx] = previous
        self._current = tuple(updated)  # type: ignore[assignment]
        return field_key, target, previous

    def send_live_write(self, *args, **kwargs) -> None:
        """Fail closed: M1K-A never authorizes live Exciter USB writes."""
        raise PermissionError(
            "M1K-A offline prototype: live USB writes for Exciter (0x9D) are disabled"
        )
