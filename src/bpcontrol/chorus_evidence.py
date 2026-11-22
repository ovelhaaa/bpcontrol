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
# ACPWorkbench English manual §6.1.27 AND BP1048 SDK chorus.h v1.1.1
# both document Chorus rate in TENTHS of Hz (raw 10=1.0 Hz).
# The V2.40.0 host communication protocol §5.20.27 describes raw 0..100
# and the BP1048 sample communication.c bounds a write >100 to raw=10.
# Earlier BPControl documentation claimed raw100=1.0 Hz without
# sufficient corroboration. Physical BP1032 M1F readback raw=200
# falls outside those nominal limits; this does NOT prove that
# physical firmware uses the same SDK implementation or converter.
# Physical baseline: docs/M1F_FIRST_LIVE_WRITE.md, complete 7-word read.
# M1H write: docs/M1H_INSPECTOR_UX.md, wet 80 -> 81 -> 80.
#
# ACPWorkbench manual ranges are documentation, not proven limits on
# this firmware. M1I does not grant hardware write permission from docs.
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
        "Flag enable observada como 1 no readback; não é ensaio de limites",
        "Flag de habilitação tipicamente 0/1; manual não fornece faixa no §6.1.27",
        "1 no baseline físico M1F",
        ("data/effect_instances.json", "data/effects.json", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        1, "delay_length", "Delay length", "ms (rótulo do schema)",
        "Manual ACPWorkbench-ENG §6.1.27: Delay Length medido em milissegundos",
        "Faixa do manual: 1–25 ms; ainda não validada nos limites físicos",
        "20 bruto no baseline físico M1F",
        ("src/bpcontrol/effects.py", "docs/OBSERVATIONS.md", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        2, "modulation_depth", "Profundidade", "ms (rótulo do schema)",
        "Manual ACPWorkbench-ENG §6.1.27: Modulation Depth em milissegundos",
        "Faixa do manual: 0 até (delay_length−1) ms; dependência não testada",
        "10 bruto no baseline físico M1F",
        ("src/bpcontrol/effects.py", "docs/OBSERVATIONS.md", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        3, "modulation_rate", "Velocidade LFO", "Hz: escala divergente",
        "Manual ACPWorkbench + SDK BP1048 chorus.h v1.1.1: raw 10=1,0Hz, raw 100=10,0Hz (raw/10). Nota antiga: raw 100=1,0Hz (raw/100), sem confirmação. CONFLITO com placa.",
        "Protocolo V2.40 §5.20.27: raw 0–100; exemplo SDK reseta escrita >100 para 10. BP1032 lê raw=200. Escala/limite do firmware físico NÃO comprovados.",
        "INI raw=10; log ACPWorkbench escreve raw=100; BP1032 M1F lê raw=200; sem comparação de Hz de UI",
        ("docs/M1I_PROTOCOL_SDK_CROSSCHECK.md", "ACPWorkbench-ENG.pdf §6.1.27", "Protocolo V2.40.0 §5.20.27", "bp1048_sdk_v0.1.12: chorus.h / communication.c", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        4, "feedback", "Feedback", "% (rótulo do schema)",
        "Manual ACPWorkbench §6.1.27 indica porcentagem",
        "Faixa do manual: 0–50%; ainda não testada nos extremos",
        "50 bruto no baseline físico M1F",
        ("src/bpcontrol/effects.py", "docs/OBSERVATIONS.md", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        5, "dry", "Nível dry", "% (rótulo do schema)",
        "Manual ACPWorkbench §6.1.27 indica porcentagem",
        "Faixa do manual: 0–100%; ainda não testada nos extremos",
        "80 bruto no baseline físico M1F",
        ("src/bpcontrol/effects.py", "docs/OBSERVATIONS.md", "docs/M1F_FIRST_LIVE_WRITE.md"),
    ),
    ChorusField(
        6, "wet", "Nível wet", "% (rótulo do schema)",
        "Manual ACPWorkbench §6.1.27 indica porcentagem; raw 80/81 confirmado fisicamente",
        "Faixa do manual: 0–100%; BPControl aceita apenas mudanças ±1 (wet)",
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
        # raw/10 is backed by the manual, protocol nominal range and
        # BP1048 SDK chorus.h, but raw=200 on the physical BP1032
        # exceeds those specified limits; never extrapolate to 20Hz.
        return "CONFLITO DE ESCALA · frequência em Hz não confirmada"
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
