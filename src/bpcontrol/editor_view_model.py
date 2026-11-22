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
