"""M1I read-only Chorus field evidence and scaling inspector.

The current writing authorization is NOT inferred from ACPWorkbench SDK
schema flags. Hardware writing remains ONLY 0x8F/field 6 (wet), with the
existing separate explicit-Apply ±1 guard. This module has no USB I/O,
no device writes, and no dependence on a GUI framework.
"""
from __future__ import annotations

from dataclasses import dataclass

CHORUS_COMMAND = 0x8F
CHORUS_INDEX = 15
CHORUS_FIELD_COUNT = 7
CHORUS_PHYSICAL_BASELINE = (1, 20, 10, 200, 50, 80, 80)

# The words below distinguish independently evidenced *identity*, live
# readback, scale inference, range information and write permission.
#
# Field labels/units: data/effect_instances.json / data/effects.json /
# src/bpcontrol/effects.py, based on previously supplied ACPWorkbench logs.
# Protocol: docs/ACP_PROTOCOL.md observes only raw 100 = 1.00 Hz for rate.
# Physical baseline: docs/M1F_FIRST_LIVE_WRITE.md, complete 7-word read.
# M1H write: docs/M1H_INSPECTOR_UX.md, wet 80 -> 81 -> 80.
#
# No independently verified full operating limits for fields 0..5 are
# shipped. For wet, 0..100 is the guard used by current BPControl, NOT a
# measured complete device range.
@dataclass(frozen=True)
class ChorusField:
    index: int
    key: str
    label: str
    unit_hint: str
    scale_evidence: str
    range_evidence: str
    raw_observation: str
    evidence_sources: tuple[str, ...]
    writable_now: bool = False

    @property
    def permission_label(self) -> str:
        return "Wet ±1 · autorização explícita" if self.writable_now else "SOMENTE LEITURA"


CHORUS_FIELDS: tuple[ChorusField, ...] = (
    ChorusField(
        0, "enable", "Ativação", "flag 0/1 (mapeamento)",
        "Rótulo/flag provenientes do mapeamento ACPWorkbench; domínio completo não ensaiado",
        "Não validada experimentalmente em BPControl",
        "1 no baseline físico M1F",
        ("data/effect_instances.json", "data/effects.json", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        1, "delay_length", "Delay length", "ms (rótulo do schema)",
        "Unidade ms indicada pelo mapeamento; conversão independente pendente",
        "Não determinada nesta firmware",
        "20 bruto no baseline físico M1F",
        ("src/bpcontrol/effects.py", "docs/OBSERVATIONS.md", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        2, "modulation_depth", "Profundidade", "ms (rótulo do schema)",
        "Unidade ms indicada pelo mapeamento; conversão independente pendente",
        "Não determinada nesta firmware",
        "10 bruto no baseline físico M1F",
        ("src/bpcontrol/effects.py", "docs/OBSERVATIONS.md", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        3, "modulation_rate", "Velocidade LFO", "Hz (raw/100, hipótese fora da amostra)",
        "Observação documentada: raw 100 = 1,00 Hz; linearidade fora desse ponto pendente",
        "Não determinada nesta firmware",
        "200 bruto no baseline físico M1F",
        ("docs/ACP_PROTOCOL.md", "data/effects.json", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        4, "feedback", "Feedback", "% (rótulo do schema)",
        "Unidade % indicada pelo mapeamento; limites pendentes",
        "Não determinada nesta firmware",
        "50 bruto no baseline físico M1F",
        ("src/bpcontrol/effects.py", "docs/OBSERVATIONS.md", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        5, "dry", "Nível dry", "% (rótulo do schema)",
        "Unidade % indicada pelo mapeamento; limites pendentes",
        "Não determinada nesta firmware",
        "80 bruto no baseline físico M1F",
        ("src/bpcontrol/effects.py", "docs/OBSERVATIONS.md", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        6, "wet", "Nível wet", "% (rótulo do schema)",
        "Raw=80/81 com escrita, ACK e readback físico. Não prova toda a escala.",
        "0..100 é limite preventivo do software; faixa física completa não comprovada",
        "80→79→80 M1F; 80→81→80 M1H, todos por readback",
        ("docs/M1F_FIRST_LIVE_WRITE.md", "docs/M1H_INSPECTOR_UX.md"),
        writable_now=True,
    ),
)


def get_chorus_field(index: int) -> ChorusField:
    if type(index) is not int or not 0 <= index < CHORUS_FIELD_COUNT:
        raise ValueError("Chorus field must be one of the seven observed positions")
    return CHORUS_FIELDS[index]


def read_only_approximation(index: int, raw: int) -> str:
    """Never present extrapolations as proven parameter scaling."""
    get_chorus_field(index)
    if type(raw) is not int or not -32768 <= raw <= 32767:
        raise ValueError("Expected a signed 16-bit raw Chorus word")
    if index == 3:
        if raw == 100:
            return "1,00 Hz · ponto documentado"
        return f"≈{raw/100:.2f} Hz · extrapolação NÃO validada"
    return "Sem conversão independente validada"


def validate_live_chorus(live: tuple[int, ...] | None) -> tuple[int, ...] | None:
    if live is None:
        return None
    if (type(live) is not tuple or len(live) != CHORUS_FIELD_COUNT
            or any(type(v) is not int or not -32768 <= v <= 32767 for v in live)):
        raise ValueError("live Chorus must have exactly seven raw signed 16-bit words")
    return live


def evidence_rows(snapshot_effect: dict, live: tuple[int, ...] | None = None) -> list[dict]:
    """Return one row per mapped Chorus field, with explicit data provenance.

    Passing a snapshot can never grant any writable permission: the locked
    registry owns the flags. Live readbacks override visible *current* values
    but the saved baseline remains available for comparison.
    """
    if not isinstance(snapshot_effect, dict):
        raise ValueError("Missing Chorus snapshot")
    if (snapshot_effect.get("index") != CHORUS_INDEX
            or snapshot_effect.get("command") != f"0x{CHORUS_COMMAND:02X}"):
        raise ValueError("Not the known Guitar Chorus instance")
    fields = snapshot_effect.get("fields")
    if not isinstance(fields, list):
        raise ValueError("Snapshot fields must be a list")
    if len(fields) not in (0, CHORUS_FIELD_COUNT):
        raise ValueError("Unexpected Chorus field count in snapshot")
    if fields:
        for i, field in enumerate(fields):
            if (not isinstance(field, dict) or field.get("index") != i
                    or type(field.get("signed")) is not int
                    or not -32768 <= field["signed"] <= 32767):
                raise ValueError("Invalid snapshot raw Chorus field")
    live = validate_live_chorus(live)
    rows = []
    for meta in CHORUS_FIELDS:
        saved = fields[meta.index]["signed"] if fields else None
        current = live[meta.index] if live is not None else saved
        rows.append({
            "index": meta.index,
            "name": meta.key,
            "label": meta.label,
            "snapshot_raw": saved,
            "current_raw": current,
            "current_origin": (
                "USB / leitura atual" if live is not None else
                "Snapshot salvo" if saved is not None else "Sem leitura"
            ),
            "unit_hint": meta.unit_hint,
            "scale_evidence": meta.scale_evidence,
            "range_evidence": meta.range_evidence,
            "raw_observation": meta.raw_observation,
            "approximation": (
                read_only_approximation(meta.index, current)
                if current is not None else "Sem dado atual"
            ),
            "permission": meta.permission_label,
            "writable_now": meta.writable_now,
            "evidence_sources": list(meta.evidence_sources),
        })
    return rows
