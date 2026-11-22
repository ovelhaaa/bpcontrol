"""M1K-A Harmonic Exciter (0x9D) schema audit and protocol evidence.

Cross-checks BP1032 instance 29 (0x9D, Harmonic_Exciter) against:
- MVSilicon ACP V2.40.0 §5.20.26
- BP1048 SDK v0.1.12 (exciter.h, communication.c, audio_effect.c)
- Operator-reported physical observations on BP1032 (fw 0.3.0 / lib 2.24.0)

This module has NO USB/HID I/O and grants NO live write permissions.
All four Exciter fields remain strictly read-only until passive USBPcap
write/ACK/readback evidence is captured and reviewed.
"""
from __future__ import annotations

from dataclasses import dataclass

EXCITER_COMMAND = 0x9D
EXCITER_INDEX = 29
EXCITER_TYPE_ID = 25
EXCITER_TYPE_NAME = "Harmonic_Exciter"
EXCITER_FIELD_COUNT = 4
EXCITER_LIVE_WRITES_AUTHORIZED = False

EXCITER_ACP_V240_CUTOFF_RANGE = (300, 10000)
EXCITER_SDK_BP1048_CUTOFF_RANGE = (1000, 10000)
EXCITER_OPERATOR_REPORTED_MIN_CUTOFF_HZ = 1000


@dataclass(frozen=True)
class ExciterFieldAudit:
    index: int
    key: str
    label: str
    unit: str
    v240_range: str
    sdk_range: str
    operator_observation: str
    discrepancy_note: str
    evidence_sources: tuple[str, ...]
    writable_now: bool = False

    @property
    def permission_label(self) -> str:
        return "SOMENTE LEITURA (M1K-A)" if not self.writable_now else "AUTORIZADO"


EXCITER_AUDIT_FIELDS: tuple[ExciterFieldAudit, ...] = (
    ExciterFieldAudit(
        index=0,
        key="enable",
        label="Ativação",
        unit="flag",
        v240_range="0 / 1 (V2.40 §5.20.26)",
        sdk_range="0 / 1 (audio_effect.c / communication.c)",
        operator_observation="Leitura física M1J validada em BP1032 fw 0.3.0 / lib 2.24.0.",
        discrepancy_note="Sem divergência nominal documentada; escrita ainda não capturada.",
        evidence_sources=(
            "data/effect_instances.json",
            "ACP V2.40.0 §5.20.26",
            "bp1048_sdk_v0.1.12: audio_effect.c",
            "docs/M1J_MUSIC_FX_INSPECTOR.md",
        ),
        writable_now=False,
    ),
    ExciterFieldAudit(
        index=1,
        key="cutoff_frequency",
        label="Cutoff",
        unit="Hz",
        v240_range="300–10000 Hz (V2.40 §5.20.26)",
        sdk_range="1000–10000 Hz (exciter.h)",
        operator_observation=(
            "Operador observou no ACPWorkbench que o mínimo aparente é 1000 Hz "
            "(evidência física reportada; não comprova todos os limites ou firmwares)."
        ),
        discrepancy_note=(
            "DIVERGÊNCIA DE MÍNIMO: V2.40 especifica 300 Hz, enquanto SDK BP1048 "
            "exciter.h e observação reportada no ACPWorkbench indicam mínimo 1000 Hz."
        ),
        evidence_sources=(
            "ACP V2.40.0 §5.20.26",
            "bp1048_sdk_v0.1.12: exciter.h",
            "docs/M1J_MUSIC_FX_INSPECTOR.md",
            "docs/M1K_A_EXCITER_PROTOCOL_EVIDENCE.md",
        ),
        writable_now=False,
    ),
    ExciterFieldAudit(
        index=2,
        key="dry",
        label="Dry",
        unit="%",
        v240_range="0–100 % (V2.40 §5.20.26)",
        sdk_range="0–100 % (exciter.h: exciter_apply)",
        operator_observation="Leitura física M1J validada em BP1032 fw 0.3.0 / lib 2.24.0.",
        discrepancy_note="Faixas nominais concordantes; escrita/ACK/readback ainda não capturados.",
        evidence_sources=(
            "ACP V2.40.0 §5.20.26",
            "bp1048_sdk_v0.1.12: exciter.h",
            "docs/M1J_MUSIC_FX_INSPECTOR.md",
        ),
        writable_now=False,
    ),
    ExciterFieldAudit(
        index=3,
        key="wet",
        label="Wet",
        unit="%",
        v240_range="0–100 % (V2.40 §5.20.26)",
        sdk_range="0–100 % (exciter.h: exciter_apply)",
        operator_observation="Leitura física M1J validada em BP1032 fw 0.3.0 / lib 2.24.0.",
        discrepancy_note="Faixas nominais concordantes; escrita/ACK/readback ainda não capturados.",
        evidence_sources=(
            "ACP V2.40.0 §5.20.26",
            "bp1048_sdk_v0.1.12: exciter.h",
            "docs/M1J_MUSIC_FX_INSPECTOR.md",
        ),
        writable_now=False,
    ),
)

EXCITER_AUDIT_BY_KEY = {field.key: field for field in EXCITER_AUDIT_FIELDS}
EXCITER_AUDIT_BY_INDEX = {field.index: field for field in EXCITER_AUDIT_FIELDS}


def exciter_audit_summary() -> dict:
    """Return structured offline audit metadata for Harmonic Exciter 0x9D."""
    return {
        "effect_index": EXCITER_INDEX,
        "command": f"0x{EXCITER_COMMAND:02X}",
        "type_id": EXCITER_TYPE_ID,
        "type_name": EXCITER_TYPE_NAME,
        "field_count": EXCITER_FIELD_COUNT,
        "live_writes_authorized": EXCITER_LIVE_WRITES_AUTHORIZED,
        "cutoff_discrepancy": {
            "acp_v240_min_hz": EXCITER_ACP_V240_CUTOFF_RANGE[0],
            "sdk_bp1048_min_hz": EXCITER_SDK_BP1048_CUTOFF_RANGE[0],
            "operator_reported_acpworkbench_min_hz": EXCITER_OPERATOR_REPORTED_MIN_CUTOFF_HZ,
            "max_hz": EXCITER_SDK_BP1048_CUTOFF_RANGE[1],
            "status": "reported_physical_observation_not_full_bounds_proof",
        },
        "fields": [
            {
                "index": f.index,
                "key": f.key,
                "label": f.label,
                "unit": f.unit,
                "v240_range": f.v240_range,
                "sdk_range": f.sdk_range,
                "writable_now": f.writable_now,
            }
            for f in EXCITER_AUDIT_FIELDS
        ],
    }
