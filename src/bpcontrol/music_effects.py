"""M1J Music-chain inspector: four *read-only* physical effects.

The official MVSilicon V2.40.0 protocol supplies parameter positions and
nominal ranges (§§5.20.13, 5.20.26, 5.20.29, 5.20.31). The ACPWorkbench
manual and BP1048 SDK provide corroboration, but the BP1032's observed
effects library is 2.24.0 and nominal ranges are NOT verified limits.

This module does not import HID, expose writes, or authorize parameters.
Only the existing firmware-gated WindowsSnapshotSession may query hardware.
"""
from __future__ import annotations

from dataclasses import dataclass

from .acp import ACPFrame
from .usb_hid import HIDTransportError

MUSIC_EFFECT_INDICES = (23, 24, 27, 29)
MUSIC_COMMANDS = (0x97, 0x98, 0x9B, 0x9D)
EXCITER_CUTOFF_CONFLICT = (
    "Corte: protocolo V2.40 = 300–10000 Hz; "
    "header BP1048 exciter.h = 1000–10000 Hz. "
    "Operador relatou mínimo aparente de 1000 Hz no ACPWorkbench (BP1032 fw 0.3.0 / lib 2.24.0); "
    "evidência reportada, faixa completa ainda não validada."
)


@dataclass(frozen=True)
class MusicParameter:
    position: int
    key: str
    label: str
    unit: str
    nominal_range: str
    evidence: str


@dataclass(frozen=True)
class MusicEffect:
    index: int
    name: str
    command: int
    type_id: int
    parameters: tuple[MusicParameter, ...]
    listening_note: str

    @property
    def word_count(self) -> int:
        return len(self.parameters)


def param(position, key, label, unit, nominal_range, evidence):
    return MusicParameter(position, key, label, unit, nominal_range, evidence)


MUSIC_EFFECTS: tuple[MusicEffect, ...] = (
    MusicEffect(
        23, "Music 3D", 0x97, 12,
        (
            param(0, "enable", "Ativação", "flag", "0 / 1",
                  "V2.40 §5.20.13; documento, não ensaio físico"),
            param(1, "intensity", "Intensidade", "%", "0–100",
                  "V2.40 §5.20.13; ACPWorkbench §6.1.13"),
        ),
        "Avaliar sensação de profundidade e estabilidade do centro; comparar em estéreo e mono.",
    ),
    MusicEffect(
        24, "Music 3D Plus", 0x98, 30,
        (
            param(0, "enable", "Ativação", "flag", "0 / 1",
                  "V2.40 §5.20.31; documento, não ensaio físico"),
            param(1, "intensity", "Intensidade", "%", "0–100",
                  "V2.40 §5.20.31; ACPWorkbench §6.1.31"),
        ),
        "Comparar ao Music 3D com o mesmo WAV/volume; o algoritmo não está descrito no protocolo.",
    ),
    MusicEffect(
        27, "Music Stereo Widener", 0x9B, 28,
        (
            param(0, "enable", "Ativação", "flag", "0 / 1",
                  "V2.40 §5.20.29; documento, não ensaio físico"),
            param(1, "shaping", "Shaping", "flag", "0 = off; 1 = on",
                  "V2.40 §5.20.29; SDK stereo_widener.h v1.2.0"),
        ),
        "Teste com material estéreo e depois mono: Shaping é binário, não um controle contínuo de largura.",
    ),
    MusicEffect(
        29, "Music Harmonic Exciter", 0x9D, 25,
        (
            param(0, "enable", "Ativação", "flag", "0 / 1",
                  "V2.40 §5.20.26; documento, não ensaio físico"),
            param(1, "cutoff_frequency", "Cutoff", "Hz",
                  "300–10000 (V2.40); 1000–10000 (SDK)",
                  EXCITER_CUTOFF_CONFLICT),
            param(2, "dry", "Dry", "%", "0–100",
                  "V2.40 §5.20.26; SDK exciter_apply()"),
            param(3, "wet", "Wet", "%", "0–100",
                  "V2.40 §5.20.26; SDK exciter_apply()"),
        ),
        "Ouvir harmônicos/agudos em volume baixo; comparar mesma passagem e evitar confundir aumento de nível com melhora.",
    ),
)
MUSIC_BY_INDEX = {effect.index: effect for effect in MUSIC_EFFECTS}
MUSIC_BY_COMMAND = {effect.command: effect for effect in MUSIC_EFFECTS}


def decode_music_frame(frame: ACPFrame, index: int) -> tuple[int, ...]:
    """Strict whole-effect read: FF plus exact little-endian signed 16-bit words."""
    if type(index) is not int or index not in MUSIC_BY_INDEX:
        raise ValueError("Unsupported Music effect index")
    effect = MUSIC_BY_INDEX[index]
    if frame.command != effect.command:
        raise HIDTransportError("Wrong Music effect command in readback")
    data = frame.payload
    if len(data) != 1 + 2 * effect.word_count or data[:1] != b"\xff":
        raise HIDTransportError(
            f"{effect.name}: expected FF plus exactly {effect.word_count} raw fields"
        )
    return tuple(int.from_bytes(data[i:i + 2], "little", signed=True)
                 for i in range(1, len(data), 2))


def read_music_live(session) -> dict[int, tuple[int, ...]]:
    """Exactly four reads after exact firmware gate; NEVER send any write."""
    session.authorize_after_firmware(session.query(0x00))
    return {
        effect.index: decode_music_frame(session.query(effect.command), effect.index)
        for effect in MUSIC_EFFECTS
    }


def normalize_music_values(values: dict) -> dict[int, tuple[int, ...]]:
    """Fail closed if the child process reply is incomplete, extra or malformed."""
    if type(values) is not dict or set(values) != set(MUSIC_EFFECT_INDICES):
        raise ValueError("Music readback must contain exactly four effect instances")
    clean = {}
    for index, words in values.items():
        effect = MUSIC_BY_INDEX[index]
        if (type(words) not in (tuple, list) or len(words) != effect.word_count
                or any(type(v) is not int or not -32768 <= v <= 32767 for v in words)):
            raise ValueError(f"{effect.name}: invalid raw field count/type")
        clean[index] = tuple(words)
    return clean


def validate_music_worker_reply(payload: dict) -> dict[int, tuple[int, ...]]:
    if type(payload) is not dict or payload.get("status") != "MUSIC_READ_OK":
        raise ValueError("Not a successful read-only Music worker reply")
    data = payload.get("effects")
    if type(data) is not dict or set(data) != {str(x) for x in MUSIC_EFFECT_INDICES}:
        raise ValueError("Music worker must return exactly four named effects")
    return normalize_music_values({int(index): raw for index, raw in data.items()})


def make_music_rows(snapshot_effects: list[dict], live: dict | None = None) -> list[dict]:
    """Show snapshot or live read without granting *any* write authority.

    A saved snapshot is not proof of the present device state. Empty/unread
    snapshots are explicitly shown as unknown, never invented defaults.
    """
    if type(snapshot_effects) is not list or len(snapshot_effects) < max(MUSIC_EFFECT_INDICES):
        raise ValueError("Missing Music snapshot catalog")
    clean_live = normalize_music_values(live) if live is not None else {}
    rows: list[dict] = []
    for effect in MUSIC_EFFECTS:
        record = snapshot_effects[effect.index - 1]
        if (record.get("index") != effect.index or record.get("command") !=
                f"0x{effect.command:02X}" or record.get("type_id") != effect.type_id):
            raise ValueError(f"{effect.name}: instance or type differs from verified catalog")
        raw_fields = record.get("fields", [])
        if type(raw_fields) is not list or len(raw_fields) not in (0, effect.word_count):
            raise ValueError(f"{effect.name}: invalid snapshot field count")
        if raw_fields:
            for j, field in enumerate(raw_fields):
                if (type(field) is not dict or field.get("index") != j
                        or type(field.get("signed")) is not int):
                    raise ValueError(f"{effect.name}: invalid saved field")
        live_words = clean_live.get(effect.index)
        for p in effect.parameters:
            saved = raw_fields[p.position]["signed"] if raw_fields else None
            current = live_words[p.position] if live_words is not None else saved
            rows.append({
                "effect_index": effect.index,
                "effect_name": effect.name,
                "command": effect.command,
                "field_index": p.position,
                "field_name": p.key,
                "field_label": p.label,
                "value": current,
                "snapshot": saved,
                "origin": "USB atual" if live_words is not None else
                          "Snapshot salvo" if saved is not None else "Sem leitura",
                "unit": p.unit,
                "nominal_range": p.nominal_range,
                "evidence": p.evidence,
                "writable": False,
                "listening_note": effect.listening_note,
            })
    return rows
