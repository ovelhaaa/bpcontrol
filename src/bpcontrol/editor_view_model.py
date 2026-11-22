"""M1H pure presentation model for the BPControl desktop inspector.

No HID, USB, tkinter or file access. All data here is read-only presentation
or a local text draft. Returning "ready" authorizes only UI confirmation,
NEVER hardware writes.
"""
from __future__ import annotations

from dataclasses import dataclass

from .chorus_editor import parse_wet_draft

GROUPS = ("Todos", "Music", "Mic", "Guitar", "Rec", "Other")
GROUP_LABELS = {
    "Todos": "Todos",
    "Music": "Música",
    "Mic": "Microfone",
    "Guitar": "Guitarra",
    "Rec": "Gravação",
    "Other": "Outros",
}

EVIDENCE_LABELS = {
    "unknown": "Não validado · leitura",
    "inferred": "Inferido · leitura",
    "readback_ui": "UI + leitura",
    "write_readback": "Mapeado · leitura",
}


def filter_effect_indices(effects: list[dict], query: str = "",
                          group: str = "Todos") -> list[int]:
    """Find effects using only the captured catalog. Never query hardware."""
    if group not in GROUPS:
        raise ValueError(f"unknown catalog group: {group}")
    term = str(query).strip().casefold()
    return [
        e["index"]
        for e in effects
        if (group == "Todos" or e.get("group") == group)
        and term in " ".join(
            str(e.get(k) or "") for k in ("name", "command", "type_name", "group")
        ).casefold()
    ]


def count_effects_by_group(effects: list[dict]) -> dict[str, int]:
    return {
        group: (len(effects) if group == "Todos"
                else sum(e.get("group") == group for e in effects))
        for group in GROUPS
    }


def evidence_label(field: dict) -> str:
    """INI names never grant permission to write."""
    return EVIDENCE_LABELS.get(field.get("mapping", "unknown"),
                               "Indefinido · leitura")


@dataclass(frozen=True)
class DraftView:
    state: str
    summary: str
    target: int | None = None
    delta: int | None = None
    can_apply: bool = False


def assess_wet_draft(draft: str, live_wet: int | None) -> DraftView:
    """Inspect draft *without* sending ACP. Live wet must come from fresh read."""
    if live_wet is not None and (
        type(live_wet) is not int or not 0 <= live_wet <= 100
    ):
        return DraftView("unverified", "Leitura USB não validada")
    if live_wet is None:
        return DraftView("need_read", "Consulte o Chorus antes de editar")
    if not isinstance(draft, str) or not draft.strip():
        return DraftView("empty", "Digite um inteiro entre 0 e 100")
    try:
        target = parse_wet_draft(draft)
    except ValueError:
        return DraftView("invalid", "Valor inválido: use somente 0–100")
    delta = target - live_wet
    if delta == 0:
        return DraftView("unchanged", "Sem alteração pendente", target, 0)
    if abs(delta) != 1:
        return DraftView(
            "step_too_large",
            f"Variação {delta:+d}: M1H permite apenas ±1 por Aplicar",
            target, delta
        )
    return DraftView(
        "ready", f"Alteração pendente: {live_wet} → {target} ({delta:+d})",
        target, delta, True
    )


def display_value_origin(effect_index: int, live_values: tuple[int, ...] | None) -> str:
    """Never imply the 59-effect snapshot is real-time live data."""
    return "USB / leitura atual" if effect_index == 15 and live_values else "Snapshot salvo"



def stage_wet_step(live_wet: int, direction: int) -> int:
    """Prepare exactly one safe candidate locally; NEVER send a USB command.

    The +/- buttons always derive from last confirmed live wet, not from
    half-edited text, so a stale draft cannot accumulate accidental steps.
    """
    if type(live_wet) is not int or not 0 <= live_wet <= 100:
        raise ValueError("A confirmed live wet 0..100 is required")
    if type(direction) is not int or direction not in (-1, 1):
        raise ValueError("Direction must be -1 or +1")
    target = live_wet + direction
    if not 0 <= target <= 100:
        raise ValueError("Candidate would exceed wet 0..100")
    return target


def validate_success_reply(
    mode: str, payload: dict, expected: tuple[int, ...] | None = None,
    target: int | None = None,
) -> None:
    """Fail closed on malformed or self-contradictory HID success replies.

    All seven fields are checked for single-step Apply. This is a *UI
    validation*, not independent hardware proof; the physical backend
    remains responsible for ACK and readback.
    """
    from .chorus_editor import validate_editor_target

    if not isinstance(payload, dict):
        raise ValueError("worker reply must be a JSON object")
    kind = payload.get("status")
    if mode == "read":
        if kind != "READ_OK":
            raise ValueError("expected READ_OK")
        fields = payload.get("fields")
        if not isinstance(fields, list) or len(fields) != 7:
            raise ValueError("read reply requires exactly seven fields")
        if any(type(v) is not int or not -32768 <= v <= 32767 for v in fields):
            raise ValueError("read reply contains non-integer field")
        if not 0 <= fields[6] <= 100:
            raise ValueError("wet readback outside 0..100")
        if payload.get("wet") is not None and payload.get("wet") != fields[6]:
            raise ValueError("wet summary contradicts full readback")
    elif mode == "apply":
        if kind != "APPLIED_VERIFIED":
            raise ValueError("expected APPLIED_VERIFIED")
        validate_editor_target(expected, target)
        baseline = payload.get("initial")
        final = payload.get("applied_readback")
        if (not isinstance(baseline, list) or not isinstance(final, list)
                or len(baseline) != 7 or len(final) != 7):
            raise ValueError("apply reply requires seven-field initial/final")
        if tuple(baseline) != expected:
            raise ValueError("apply reply baseline differs from requested state")
        intended = list(expected)
        intended[6] = target
        if final != intended:
            raise ValueError("apply reply differs from requested one-point target")
        if (payload.get("target") != target
                or payload.get("candidate_ack_valid") is not True
                or payload.get("errors") not in ([], ())):
            raise ValueError("apply reply lacks a clean ACK or matching target")
    else:
        raise ValueError("unknown worker operation")
