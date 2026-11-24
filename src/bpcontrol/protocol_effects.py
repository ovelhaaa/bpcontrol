"""Read-only catalog of all 45 MVSilicon ACP V2.40.0 audio effect schemas.

Cross-referenced against:
- MVSilicon Firmware-Application Communication Protocol V2.40.0 (§5.19, §5.20.1–5.20.45)
- ACPWorkbench User Manual V2.25.0 (§6.1.1–6.1.33)

All definitions here are strictly READ-ONLY protocol documentation schemas.
They NEVER authorize USB writes, flash saves, or firmware modifications.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import log10
from typing import Any, Sequence


EQ_FILTER_TYPES: dict[int, str] = {
    0: "PEAKING",
    1: "LOW_SHELF",
    2: "HIGH_SHELF",
    3: "LOW_PASS",
    4: "HIGH_PASS",
    5: "BAND_PASS",
    6: "NOTCH",
    7: "LOW_PASS_ORDER1",
    8: "HIGH_PASS_ORDER1",
}

DRC_MODES: dict[int, str] = {
    0: "full band",
    1: "2-band",
    2: "2-band + full band",
    3: "3-band",
    4: "3-band + full band",
}

DRC_CF_TYPES: dict[int, str] = {
    1: "B1",
    2: "LR2",
    3: "LR4",
    4: "Q4",
}

AUTO_TUNE_KEYS: dict[int, str] = {
    ord("a"): "A-flat major",
    ord("A"): "A major",
    ord("b"): "B-flat major",
    ord("B"): "B major",
    ord("C"): "C major",
    ord("d"): "D-flat major",
    ord("D"): "D major",
    ord("e"): "E-flat major",
    ord("E"): "E major",
    ord("F"): "F major",
    ord("g"): "G-flat major",
    ord("G"): "G major",
    ord("X"): "chromatic scale",
}

AUTO_TUNE_SNAPS: dict[int, str] = {
    ord("n"): "near snap",
    ord("u"): "upper snap",
    ord("l"): "lower snap",
}

AUTO_TUNE_ACCURACY: dict[int, str] = {
    0: "normal accuracy",
    1: "better accuracy",
    2: "best accuracy",
}

FREQUENCY_SHIFTER_DELTAS: dict[int, str] = {
    0: "-7 Hz",
    1: "-5 Hz",
    2: "-3 Hz",
    3: "+3 Hz",
    4: "+5 Hz",
    5: "+7 Hz",
}

HOWLING_MODES: dict[int, str] = {
    0: "No suppression",
    1: "Precise suppression",
}

PHASE_DIFFERENCES: dict[int, str] = {
    0: "0°",
    1: "180°",
}

SINE_CHANNELS: dict[int, str] = {
    0: "both disable",
    1: "left channel enable",
    2: "right channel enable",
    3: "both enable",
}


@dataclass(frozen=True)
class ProtocolParam:
    """One 16-bit parameter word within a V2.40.0 effect payload."""

    index: int
    param_code: int
    name: str
    kind: str = "int"
    unit: str = "raw"
    min_value: int | None = None
    max_value: int | None = None
    default_value: int | None = None
    scale_divisor: float | None = None
    q_format: str | None = None
    enum_options: dict[int, str] | None = None
    note: str = ""
    writable: bool = False


@dataclass(frozen=True)
class ProtocolEffect:
    """Protocol schema for one effect type_id (0..44) in ACP V2.40.0."""

    type_id: int
    type_name: str
    doc_ref: str
    params: tuple[ProtocolParam, ...]
    note: str = ""

    @property
    def word_count(self) -> int:
        return len(self.params)

    def get_param(self, name: str) -> ProtocolParam:
        for param in self.params:
            if param.name == name:
                return param
        raise KeyError(f"unknown parameter {name!r} for {self.type_name}")


def _p(
    index: int,
    name: str,
    kind: str = "int",
    unit: str = "raw",
    min_value: int | None = None,
    max_value: int | None = None,
    default_value: int | None = None,
    *,
    param_code: int | None = None,
    scale_divisor: float | None = None,
    q_format: str | None = None,
    enum_options: dict[int, str] | None = None,
    note: str = "",
) -> ProtocolParam:
    return ProtocolParam(
        index=index,
        param_code=index if param_code is None else param_code,
        name=name,
        kind=kind,
        unit=unit,
        min_value=min_value,
        max_value=max_value,
        default_value=default_value,
        scale_divisor=scale_divisor,
        q_format=q_format,
        enum_options=enum_options,
        note=note,
        writable=False,
    )


def _enable(default: int = 0) -> ProtocolParam:
    return _p(0, "enable", "bool", "flag", 0, 1, default, enum_options={0: "off", 1: "on"})


def _eq_filter_params(start_index: int, start_code: int) -> list[ProtocolParam]:
    items: list[ProtocolParam] = []
    idx = start_index
    code = start_code
    for band in range(1, 11):
        items.append(_p(idx, f"filter{band}_enable", "bool", "flag", 0, 1, 0,
                        param_code=code, enum_options={0: "off", 1: "on"}))
        items.append(_p(idx + 1, f"filter{band}_type", "enum", "enum", 0, 8, 0,
                        param_code=code + 1, enum_options=EQ_FILTER_TYPES))
        items.append(_p(idx + 2, f"filter{band}_f0", "int", "Hz", 0, 24000, 200,
                        param_code=code + 2))
        items.append(_p(idx + 3, f"filter{band}_Q", "q_format", "Q6.10", 0, 32767, 724,
                        param_code=code + 3, scale_divisor=1024.0, q_format="Q6.10"))
        items.append(_p(idx + 4, f"filter{band}_gain", "q_format", "dB (Q8.8)", -32768, 32767, 0,
                        param_code=code + 4, scale_divisor=256.0, q_format="Q8.8"))
        idx += 5
        code += 5
    return items


def _drc_v4_band_params(start_index: int, start_code: int) -> list[ProtocolParam]:
    items: list[ProtocolParam] = [
        _p(start_index, "drc_mode", "enum", "enum", 0, 4, 0,
           param_code=start_code, enum_options=DRC_MODES),
        _p(start_index + 1, "cf_type", "enum", "enum", 1, 4, 3,
           param_code=start_code + 1, enum_options=DRC_CF_TYPES),
        _p(start_index + 2, "q_l", "q_format", "Q6.10", 0, 32767, 724,
           param_code=start_code + 2, scale_divisor=1024.0, q_format="Q6.10"),
        _p(start_index + 3, "q_h", "q_format", "Q6.10", 0, 32767, 724,
           param_code=start_code + 3, scale_divisor=1024.0, q_format="Q6.10"),
        _p(start_index + 4, "fc_1", "int", "Hz", 20, 20000, 300,
           param_code=start_code + 4, note="fc[0]; must satisfy fc2 > fc1"),
        _p(start_index + 5, "fc_2", "int", "Hz", 20, 20000, 3000,
           param_code=start_code + 4, note="fc[1]; must satisfy fc2 > fc1"),
    ]
    idx = start_index + 6
    arrays = (
        ("threshold", start_code + 5, "int", "0.01 dB", -9000, 0, 0, 100.0, None),
        ("ratio", start_code + 6, "int", "ratio", 1, 1000, 100, None, None),
        ("attack", start_code + 7, "int", "ms", 0, 7500, 1, None, None),
        ("release", start_code + 8, "int", "ms", 0, 7500, 1000, None, None),
        ("pregain", start_code + 9, "q_format", "Q4.12", 1, 32767, 4096, 4096.0, "Q4.12"),
    )
    for prefix, code, kind, unit, lo, hi, default, divisor, qfmt in arrays:
        for band in range(1, 5):
            items.append(_p(
                idx, f"{prefix}_{band}", kind, unit, lo, hi, default,
                param_code=code, scale_divisor=divisor, q_format=qfmt,
            ))
            idx += 1
    return items


PROTOCOL_EFFECTS: dict[int, ProtocolEffect] = {
    0: ProtocolEffect(
        0, "Auto Tune", "V2.40 §5.20.1 / Manual §6.1.1",
        (
            _enable(),
            _p(1, "key", "ascii_char", "char", 65, 103, ord("C"), enum_options=AUTO_TUNE_KEYS),
            _p(2, "snap", "ascii_char", "char", 108, 117, ord("n"), enum_options=AUTO_TUNE_SNAPS),
            _p(3, "pitch_accuracy", "enum", "enum", 0, 2, 2, enum_options=AUTO_TUNE_ACCURACY),
        ),
    ),
    1: ProtocolEffect(
        1, "DC Blocker", "V2.40 §5.20.2 / Manual §6.1.2",
        (_enable(),),
    ),
    2: ProtocolEffect(
        2, "Dynamic Range Compressor", "V2.40 §5.20.3 (V4.0.0+) / Manual §6.1.3",
        tuple([_enable()] + _drc_v4_band_params(1, 1)),
        note="V4.0.0+ layout (27 words). Legacy V3.x uses 16 words.",
    ),
    3: ProtocolEffect(
        3, "Echo", "V2.40 §5.20.4 / Manual §6.1.4",
        (
            _enable(),
            _p(1, "cutoff_frequency", "int", "Hz", 0, 24000, 7500, note="0 disables LPF"),
            _p(2, "attenuation", "q_format", "Q1.15", 0, 32767, 11627, scale_divisor=32768.0, q_format="Q1.15"),
            _p(3, "delay", "int", "ms", 0, 3000, 400, note="0..max_delay ms"),
            _p(4, "reserved", "reserved", "raw", None, None, 0),
            _p(5, "max_delay", "int", "ms", 0, 3000, 1000, note="Configure before enabling"),
            _p(6, "quality_mode", "int", "mode", 0, 2, 0, note="Configure before enabling"),
            _p(7, "dry", "int", "%", 0, 100, 100),
            _p(8, "wet", "int", "%", 0, 100, 100),
        ),
    ),
    4: ProtocolEffect(
        4, "EQ", "V2.40 §5.20.5 / Manual §6.1.5",
        tuple(
            [
                _enable(),
                _p(1, "pregain", "q_format", "dB (Q8.8)", -32768, 32767, 0,
                   scale_divisor=256.0, q_format="Q8.8"),
                _p(2, "calculation_type", "enum", "flag", 0, 1, 0,
                   enum_options={0: "fixed-point", 1: "floating-point"}),
            ]
            + _eq_filter_params(3, 3)
        ),
    ),
    5: ProtocolEffect(
        5, "Noise Suppressor Expander", "V2.40 §5.20.6 / Manual §6.1.6",
        (
            _enable(),
            _p(1, "threshold", "int", "0.01 dB", -9000, 0, -4500, scale_divisor=100.0),
            _p(2, "ratio", "int", "ratio", 1, 1000, 3),
            _p(3, "attack", "int", "ms", 0, 32767, 5),
            _p(4, "release", "int", "ms", 0, 32767, 500),
        ),
    ),
    6: ProtocolEffect(
        6, "Frequency Shifter", "V2.40 §5.20.7 / Manual §6.1.7",
        (
            _enable(),
            _p(1, "deltaf", "enum", "enum", 0, 5, 4, enum_options=FREQUENCY_SHIFTER_DELTAS),
        ),
    ),
    7: ProtocolEffect(
        7, "Howling Control", "V2.40 §5.20.8 / Manual §6.1.8",
        (
            _enable(),
            _p(1, "suppression_mode", "enum", "enum", 0, 1, 1, enum_options=HOWLING_MODES),
        ),
    ),
    8: ProtocolEffect(
        8, "Noise Gate", "V2.40 §5.20.9 / Manual §6.1.9",
        (
            _enable(),
            _p(1, "lower", "int", "dB", -90, 0, -45),
            _p(2, "upper", "int", "dB", -90, 0, -43),
            _p(3, "attack", "int", "ms", 0, 7500, 5),
            _p(4, "release", "int", "ms", 0, 7500, 100),
            _p(5, "hold", "int", "ms", 0, 7500, 500),
        ),
    ),
    9: ProtocolEffect(
        9, "Pitch Shifter", "V2.40 §5.20.10 / Manual §6.1.10",
        (
            _enable(),
            _p(1, "key", "int", "0.1 semitone", -120, 120, 0, scale_divisor=10.0),
        ),
    ),
    10: ProtocolEffect(
        10, "Reverb", "V2.40 §5.20.11 / Manual §6.1.11",
        (
            _enable(),
            _p(1, "dry", "int", "%", 0, 200, 50),
            _p(2, "wet", "int", "%", 0, 300, 100),
            _p(3, "width", "int", "%", 0, 100, 100),
            _p(4, "room", "int", "%", 0, 100, 60),
            _p(5, "damping", "int", "%", 0, 100, 50),
            _p(6, "mono", "bool", "flag", 0, 1, 0, enum_options={0: "stereo", 1: "mono"}),
        ),
    ),
    11: ProtocolEffect(
        11, "Silence Detector", "V2.40 §5.20.12 / Manual §6.1.12",
        (
            _enable(),
            _p(1, "pcm_amplitude", "int", "raw", 0, 32768, None, note="Read-only energy level"),
        ),
    ),
    12: ProtocolEffect(
        12, "MV3D", "V2.40 §5.20.13 / Manual §6.1.13",
        (
            _enable(),
            _p(1, "intensity", "int", "%", 0, 100, 50),
        ),
    ),
    13: ProtocolEffect(
        13, "MVBass", "V2.40 §5.20.14 / Manual §6.1.14",
        (
            _enable(),
            _p(1, "cutoff_frequency", "int", "Hz", 30, 300, 100),
            _p(2, "intensity", "int", "%", 0, 100, 35),
            _p(3, "enhanced", "bool", "flag", 0, 1, 1, enum_options={0: "off", 1: "on"}),
        ),
    ),
    14: ProtocolEffect(
        14, "Voice Changer", "V2.40 §5.20.15 / Manual §6.1.15",
        (
            _enable(),
            _p(1, "pitch", "int", "%", 50, 300, 200),
            _p(2, "formant", "int", "%", 66, 200, 130),
        ),
    ),
    15: ProtocolEffect(
        15, "Gain Control", "V2.40 §5.20.16 / Manual §6.1.16",
        (
            _enable(),
            _p(1, "mute", "bool", "flag", 0, 1, 0, enum_options={0: "unmute", 1: "mute"}),
            _p(2, "gain", "q_format", "Q3.12", 0, 0x3FFF, 0x1000,
               scale_divisor=4096.0, q_format="Q3.12"),
        ),
    ),
    16: ProtocolEffect(
        16, "Vocal Cut", "V2.40 §5.20.17 / Manual §6.1.17",
        (
            _enable(),
            _p(1, "wetdrymix", "int", "%", 0, 100, 100),
        ),
    ),
    17: ProtocolEffect(
        17, "Reverb Plate", "V2.40 §5.20.18 / Manual §6.1.18",
        (
            _enable(),
            _p(1, "high_cutoff_frequency", "int", "Hz", 0, 24000, 20000,
               note="0..sample_rate/2"),
            _p(2, "modulation", "bool", "flag", 0, 1, 1, enum_options={0: "off", 1: "on"}),
            _p(3, "predelay", "int", "samples", 0, 4410, 40),
            _p(4, "diffusion", "int", "%", 0, 100, 50),
            _p(5, "decay", "int", "%", 0, 100, 50),
            _p(6, "damping", "int", "0.01%", 0, 10000, 5, scale_divisor=100.0),
            _p(7, "wetdrymix", "int", "%", 0, 100, 80),
        ),
    ),
    18: ProtocolEffect(
        18, "Reverb Pro", "V2.40 §5.20.19 / Manual §6.1.19",
        (
            _enable(),
            _p(1, "dry", "int", "dB", -70, 10, -10),
            _p(2, "wet", "int", "dB", -70, 10, 0),
            _p(3, "erwet", "int", "dB", -70, 10, -9),
            _p(4, "erfactor", "int", "%", 50, 250, 160),
            _p(5, "erwidth", "int", "%", -100, 100, 70),
            _p(6, "ertolate", "int", "%", 0, 100, 40),
            _p(7, "rt60", "int", "ms", 100, 15000, 3200),
            _p(8, "delay", "int", "ms", 0, 100, 20),
            _p(9, "width", "int", "%", 0, 100, 100),
            _p(10, "wander", "int", "%", 10, 60, 35),
            _p(11, "spin", "int", "%", 0, 1000, 70),
            _p(12, "inputlpf", "int", "Hz", 200, 18000, 17000),
            _p(13, "damplpf", "int", "Hz", 200, 18000, 7000),
            _p(14, "basslpf", "int", "Hz", 50, 1050, 500),
            _p(15, "bassb", "int", "%", 0, 50, 15),
            _p(16, "outputlpf", "int", "Hz", 200, 18000, 10000),
        ),
    ),
    19: ProtocolEffect(
        19, "Voice Changer Pro", "V2.40 §5.20.20 / Manual §6.1.20",
        (
            _enable(),
            _p(1, "pitch", "int", "%", 50, 300, 200),
            _p(2, "formant", "int", "%", 66, 200, 130),
        ),
    ),
    20: ProtocolEffect(
        20, "Phase Control", "V2.40 §5.20.21 / Manual §6.1.21",
        (
            _enable(),
            _p(1, "phase_difference", "enum", "enum", 0, 1, 0, enum_options=PHASE_DIFFERENCES),
        ),
    ),
    21: ProtocolEffect(
        21, "Vocal Remover", "V2.40 §5.20.22 / Manual §6.1.22",
        (
            _enable(),
            _p(1, "lower_frequency", "int", "Hz", 20, 20000, 200),
            _p(2, "higher_frequency", "int", "Hz", 20, 20000, 15000),
        ),
    ),
    22: ProtocolEffect(
        22, "Pitch Shifter Pro", "V2.40 §5.20.23 / Manual §6.1.23",
        (
            _enable(),
            _p(1, "key", "int", "0.1 semitone", -120, 120, 0, scale_divisor=10.0),
        ),
    ),
    23: ProtocolEffect(
        23, "MVBass Classic", "V2.40 §5.20.24 / Manual §6.1.24",
        (
            _enable(),
            _p(1, "cutoff_frequency", "int", "Hz", 30, 300, 100),
            _p(2, "intensity", "int", "%", 0, 100, 35),
        ),
    ),
    24: ProtocolEffect(
        24, "PCM Delay", "V2.40 §5.20.25 / Manual §6.1.25",
        (
            _enable(),
            _p(1, "delay", "int", "ms", 0, 3000, 40, note="0..max_delay ms"),
            _p(2, "max_delay", "int", "ms", 0, 3000, 50, note="Configure before enabling"),
            _p(3, "high_quality_enable", "bool", "flag", 0, 1, 1,
               enum_options={0: "off", 1: "on"}, note="Configure before enabling"),
        ),
    ),
    25: ProtocolEffect(
        25, "Harmonic Exciter", "V2.40 §5.20.26 / Manual §6.1.26",
        (
            _enable(),
            _p(1, "cutoff_frequency", "int", "Hz", 300, 10000, 1000,
               note="V2.40: 300..10000 Hz; Manual/BP1048 SDK/BP1032 UI: 1000..10000 Hz"),
            _p(2, "dry", "int", "%", 0, 100, 80),
            _p(3, "wet", "int", "%", 0, 100, 80),
        ),
    ),
    26: ProtocolEffect(
        26, "Chorus", "V2.40 §5.20.27 / Manual §6.1.27",
        (
            _enable(),
            _p(1, "delay_length", "int", "ms", 1, 25, 13),
            _p(2, "modulation_depth", "int", "ms", 0, 24, 3, note="0..(delay_length-1) ms"),
            _p(3, "modulation_rate", "int", "raw", 0, 100, 10,
               note="V2.40: 0..100; BP1032 observed 200/500/1000 for 2/5/10 Hz"),
            _p(4, "feedback", "int", "%", 0, 50, 30),
            _p(5, "dry", "int", "%", 0, 100, 90),
            _p(6, "wet", "int", "%", 0, 100, 60),
        ),
    ),
    27: ProtocolEffect(
        27, "Auto Wah", "V2.40 §5.20.28 / Manual §6.1.28",
        (
            _enable(),
            _p(1, "modulation_rate", "int", "0.1 Hz", 0, 100, 10, scale_divisor=10.0),
            _p(2, "minimum_frequency", "int", "Hz", 100, 500, 200),
            _p(3, "maximum_frequency", "int", "Hz", 500, 5000, 2000),
            _p(4, "depth", "int", "raw", 1, 100, 20),
            _p(5, "dry", "int", "%", 0, 100, 0),
            _p(6, "wet", "int", "%", 0, 100, 100),
        ),
    ),
    28: ProtocolEffect(
        28, "Stereo Widener", "V2.40 §5.20.29 / Manual §6.1.29",
        (
            _enable(),
            _p(1, "shaping", "bool", "flag", 0, 1, 0,
               enum_options={0: "no shaping", 1: "shaping"}),
        ),
    ),
    29: ProtocolEffect(
        29, "Ping Pong", "V2.40 §5.20.30 / Manual §6.1.30",
        (
            _enable(),
            _p(1, "attenuation", "q_format", "Q1.15", 0, 32767, 19661,
               scale_divisor=32768.0, q_format="Q1.15"),
            _p(2, "delay", "int", "ms/samples", 0, 3000, 250,
               note="V2.40: ms; Manual §6.1.30: samples"),
            _p(3, "high_quality_enable", "bool", "flag", 0, 1, 0,
               enum_options={0: "off", 1: "on"}, note="Configure before enabling"),
            _p(4, "wetdrymix", "int", "%", 0, 100, 50),
            _p(5, "max_delay", "int", "ms", 1, 3000, 1000, note="Configure before enabling"),
        ),
    ),
    30: ProtocolEffect(
        30, "MV3D Plus", "V2.40 §5.20.31 / Manual §6.1.31",
        (
            _enable(),
            _p(1, "intensity", "int", "%", 0, 100, 50),
        ),
    ),
    31: ProtocolEffect(
        31, "Sine Generator", "V2.40 §5.20.32 / Manual §6.1.32",
        (
            _enable(),
            _p(1, "channel_enable", "enum", "enum", 0, 3, 3, enum_options=SINE_CHANNELS),
            _p(2, "left_frequency", "int", "Hz", 1, 24000, 1000, note="1..SampleRate/2"),
            _p(3, "right_frequency", "int", "Hz", 1, 24000, 1000, note="1..SampleRate/2"),
            _p(4, "left_amplitude", "int", "0.1 dB", -960, 0, 0, scale_divisor=10.0),
            _p(5, "right_amplitude", "int", "0.1 dB", -960, 0, 0, scale_divisor=10.0),
        ),
    ),
    32: ProtocolEffect(
        32, "Noise Suppressor Blue", "V2.40 §5.20.33 / Manual §6.1.33",
        (
            _enable(),
            _p(1, "level", "int", "level", 0, 9, 5, note="V2.40: 0..9; Manual: 0..5"),
        ),
    ),
    33: ProtocolEffect(
        33, "Flanger", "V2.40 §5.20.34",
        (
            _enable(),
            _p(1, "delay_length", "int", "ms", 1, 15, 1),
            _p(2, "modulation_depth", "int", "ms", 0, 15, 1, note="0..delay_length"),
            _p(3, "modulation_rate", "int", "0.01 Hz", 0, 1000, 100, scale_divisor=100.0),
            _p(4, "feedback", "int", "%", 0, 100, 70),
            _p(5, "dry", "int", "%", 0, 100, 59),
            _p(6, "wet", "int", "%", 0, 100, 100),
        ),
    ),
    34: ProtocolEffect(
        34, "Frequency Shifter Fine", "V2.40 §5.20.35",
        (
            _enable(),
            _p(1, "deltaf", "int", "0.01 Hz", -1000, 1000, 500, scale_divisor=100.0),
        ),
    ),
    35: ProtocolEffect(
        35, "Overdrive", "V2.40 §5.20.36",
        (
            _enable(),
            _p(1, "threshold_compression", "q_format", "Q1.15", 4096, 10923, 10923,
               scale_divisor=32768.0, q_format="Q1.15"),
        ),
    ),
    36: ProtocolEffect(
        36, "Distortion", "V2.40 §5.20.37",
        (
            _enable(),
            _p(1, "gain", "int", "dB", 0, 48, 18),
            _p(2, "dry", "int", "%", 0, 100, 0),
            _p(3, "wet", "int", "%", 0, 100, 100),
        ),
    ),
    37: ProtocolEffect(
        37, "EQ_DRC", "V2.40 §5.20.38",
        tuple(
            [
                _enable(),
                _p(1, "reserved_1", "reserved", "raw", None, None, 0,
                   note="Reserved in V2.40 §5.20.38; INI hint: pregain"),
                _p(2, "reserved_2", "reserved", "raw", None, None, 0,
                   note="Reserved in V2.40 §5.20.38; INI hint: calculation_type"),
            ]
            + _eq_filter_params(3, 3)
            + _drc_v4_band_params(53, 53)
        ),
    ),
    38: ProtocolEffect(
        38, "AEC", "V2.40 §5.20.39",
        (
            _enable(),
            _p(1, "echo_suppression_level", "int", "level", 0, 15, 0,
               note="0: off; 1..5: echo suppression; 11..15: duplex suppression"),
            _p(2, "noise_suppression_level", "int", "level", 0, 9, 0),
        ),
    ),
    39: ProtocolEffect(
        39, "Distortion DS1", "V2.40 §5.20.40",
        (
            _enable(),
            _p(1, "distortion_level", "int", "%", 0, 100, 0),
            _p(2, "out_level", "int", "%", 0, 100, 0),
        ),
    ),
    40: ProtocolEffect(
        40, "Overdrive Poly", "V2.40 §5.20.41",
        (
            _enable(),
            _p(1, "gain", "int", "dB", 0, 48, 0),
            _p(2, "out_level", "int", "%", 0, 100, 0),
        ),
    ),
    41: ProtocolEffect(
        41, "Compander", "V2.40 §5.20.42",
        (
            _enable(),
            _p(1, "threshold", "int", "0.01 dB", -9000, 0, -4000, scale_divisor=100.0),
            _p(2, "ratio_below", "int", "0.01", 1, 10000, 100, scale_divisor=100.0),
            _p(3, "ratio_above", "int", "0.01", 1, 10000, 100, scale_divisor=100.0),
            _p(4, "attack_time", "int", "ms", 0, 32767, 5),
            _p(5, "release_time", "int", "ms", 0, 32767, 100),
            _p(6, "pregain", "int", "0.01 dB", -7200, 1800, 0, scale_divisor=100.0),
        ),
    ),
    42: ProtocolEffect(
        42, "Low Level Compressor", "V2.40 §5.20.43",
        (
            _enable(),
            _p(1, "threshold", "int", "0.01 dB", -9600, 0, -6400, scale_divisor=100.0),
            _p(2, "gain", "int", "0.01 dB", 0, 4800, 2140, scale_divisor=100.0),
            _p(3, "attack_time", "int", "ms", 0, 32767, 10),
            _p(4, "release_time", "int", "ms", 0, 32767, 1000),
        ),
    ),
    43: ProtocolEffect(
        43, "Howling Suppressor Fine", "V2.40 §5.20.44",
        (
            _enable(),
            _p(1, "minimum_q_factor", "q_format", "Q6.10", 0, 32767, 512,
               scale_divisor=1024.0, q_format="Q6.10", note="Min Q <= Max Q"),
            _p(2, "maximum_q_factor", "q_format", "Q6.10", 0, 32767, 5120,
               scale_divisor=1024.0, q_format="Q6.10"),
        ),
    ),
    44: ProtocolEffect(
        44, "Biquad", "V2.40 §5.20.45",
        (
            _enable(),
            _p(1, "reserved_1", "reserved", "raw", None, None, 0),
            _p(2, "flags", "bitfield", "bitfield", 0, 65535, 0,
               note="15~8 bits: use float; 7~0 bits: output saturation"),
            _p(3, "reserved_3", "reserved", "raw", None, None, 0),
            _p(4, "filter_type", "enum", "enum", 0, 8, 0, enum_options=EQ_FILTER_TYPES),
            _p(5, "filter_f0", "int", "Hz", 0, 24000, 200),
            _p(6, "filter_q", "q_format", "Q6.10", 0, 32767, 724,
               scale_divisor=1024.0, q_format="Q6.10"),
            _p(7, "filter_gain", "q_format", "dB (Q8.8)", -32768, 32767, 0,
               scale_divisor=256.0, q_format="Q8.8"),
        ),
    ),
}

PROTOCOL_EFFECTS_BY_NAME: dict[str, ProtocolEffect] = {
    effect.type_name: effect for effect in PROTOCOL_EFFECTS.values()
}


def format_param_value(param: ProtocolParam, raw_signed: int) -> str:
    """Format a signed 16-bit raw parameter word according to its V2.40.0 type."""
    if param.enum_options is not None:
        label = param.enum_options.get(raw_signed)
        if param.kind == "ascii_char":
            ch = chr(raw_signed) if 32 <= raw_signed <= 126 else f"0x{raw_signed:02X}"
            return f"'{ch}' ({label})" if label else f"'{ch}' ({raw_signed})"
        return f"{raw_signed} ({label})" if label else str(raw_signed)

    if param.kind == "bitfield":
        hi = (raw_signed >> 8) & 0xFF
        lo = raw_signed & 0xFF
        return f"0x{raw_signed & 0xFFFF:04X} (hi={hi}, lo={lo})"

    if param.q_format == "Q1.15":
        if raw_signed <= 0:
            return f"{raw_signed} (-inf dB)"
        db = 20.0 * log10(raw_signed / 32768.0)
        return f"{raw_signed} ({db:.2f} dB)"

    if param.q_format in ("Q3.12", "Q4.12"):
        if raw_signed <= 0:
            return f"{raw_signed} (-inf dB)"
        db = 20.0 * log10(raw_signed / 4096.0)
        return f"{raw_signed} ({db:.2f} dB)"

    if param.scale_divisor is not None:
        scaled = raw_signed / param.scale_divisor
        unit = param.unit.replace(" (Q8.8)", "")
        if unit in ("Q6.10",):
            return f"{scaled:.3f}"
        if unit == "0.01":
            return f"{scaled:.2f}"
        if unit == "0.01 dB":
            return f"{scaled:.2f} dB"
        if unit == "0.1 dB":
            return f"{scaled:.1f} dB"
        if unit == "0.1 semitone":
            return f"{scaled:.1f} semitone"
        if unit == "0.01 Hz":
            return f"{scaled:.2f} Hz"
        if unit == "0.1 Hz":
            return f"{scaled:.1f} Hz"
        if unit == "0.01%":
            return f"{scaled:.2f}%"
        return f"{scaled:.2f} {unit}".strip()

    if param.unit in ("Hz", "ms", "%", "dB", "samples"):
        return f"{raw_signed} {param.unit}"
    return str(raw_signed)


def decode_protocol_effect(type_id: int, words: Sequence[int]) -> list[dict[str, Any]]:
    """Decode a sequence of signed 16-bit words for a given V2.40.0 type_id."""
    if type_id not in PROTOCOL_EFFECTS:
        raise KeyError(f"unknown protocol effect type_id: {type_id}")
    schema = PROTOCOL_EFFECTS[type_id]
    if len(words) != schema.word_count:
        raise ValueError(
            f"{schema.type_name} (type_id={type_id}) expects {schema.word_count} words, "
            f"got {len(words)}"
        )
    decoded: list[dict[str, Any]] = []
    for param, raw in zip(schema.params, words):
        decoded.append({
            "index": param.index,
            "param_code": param.param_code,
            "name": param.name,
            "kind": param.kind,
            "unit": param.unit,
            "raw": raw,
            "formatted": format_param_value(param, raw),
            "min_value": param.min_value,
            "max_value": param.max_value,
            "default_value": param.default_value,
            "doc_ref": schema.doc_ref,
            "writable": False,
        })
    return decoded


def decode_snapshot_instance(record: dict[str, Any]) -> dict[str, Any]:
    """Decode one effect entry from a bpcontrol-snapshot-v1 dict (read-only)."""
    type_id = record.get("type_id")
    if type(type_id) is not int or type_id not in PROTOCOL_EFFECTS:
        raise KeyError(f"unsupported type_id in snapshot record: {type_id!r}")
    fields = record.get("fields", [])
    words = [f["signed"] for f in fields]
    schema = PROTOCOL_EFFECTS[type_id]
    return {
        "index": record.get("index"),
        "command": record.get("command"),
        "name": record.get("name"),
        "type_id": type_id,
        "type_name": schema.type_name,
        "doc_ref": schema.doc_ref,
        "writable": False,
        "parameters": decode_protocol_effect(type_id, words),
    }
