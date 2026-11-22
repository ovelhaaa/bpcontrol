"""Evidence-graded effect schemas for BP1032 firmware HunXiang_F.

Never assume these indexes are universal across board firmware versions.
"""
from dataclasses import dataclass
from math import log10

from .acp import effect_command


@dataclass(frozen=True)
class Param:
    index: int
    name: str
    unit: str = "raw"
    evidence: str = "write_readback"
    writable: bool = True


@dataclass(frozen=True)
class Effect:
    index: int
    name: str
    params: tuple[Param, ...]

    @property
    def command(self) -> int:
        return effect_command(self.index)

    def get_param(self, name: str) -> Param:
        for param in self.params:
            if param.name == name:
                return param
        raise KeyError(f"unknown parameter: {name}")


def P(index: int, name: str, unit: str = "raw",
      evidence: str = "write_readback", writable: bool = True) -> Param:
    return Param(index, name, unit, evidence, writable)


EFFECTS = {
    "guitar_chorus": Effect(15, "Guitar Chorus", (
        # ACPWorkbench §6.1.27 documents nominal ranges for these
        # parameters. Those ranges alone do NOT authorize hardware writes.
        P(0, "enable", "bool", writable=False),
        P(1, "delay_length", "ms", writable=False),
        P(2, "modulation_depth", "ms", writable=False),
        # Scale conflict: ACPWorkbench manual raw/10 Hz; prior BPControl
        # observation raw/100 Hz; physical 200 exceeds manual 0..100.
        # Preserve the RAW integer; do not falsely label centiHz.
        P(3, "modulation_rate", "raw", "inferred", False),
        P(4, "feedback", "%", writable=False),
        P(5, "dry", "%", writable=False),
        P(6, "wet", "%"),
    )),
    "mic_echo": Effect(10, "Mic Echo", (
        P(0, "enable", "bool"), P(1, "cutoff", "Hz"),
        P(2, "attenuation", "Q15"), P(3, "delay", "ms"),
        P(4, "unknown_04", evidence="readback_ui", writable=False),
        P(5, "max_delay", "ms", "readback_ui", False),
        P(6, "quality_mode", "bool"), P(7, "dry", "%"), P(8, "wet", "%"),
    )),
    "guitar_pingpong": Effect(14, "Guitar PingPong", (
        P(0, "enable", "bool"), P(1, "attenuation", "Q15"),
        P(2, "delay", "ms"), P(3, "high_quality", "bool"),
        P(4, "wet_dry_mix", "%"),
        P(5, "max_delay", "ms", "readback_ui", False),
    )),
    "music_delay": Effect(28, "Music Delay", (
        P(0, "enable", "bool"), P(1, "delay", "ms"),
        P(2, "max_delay", "ms", "readback_ui", False),
        P(3, "high_quality", "bool"),
    )),
    "pitch_shifter_pro": Effect(20, "Music Pitch Shifter Pro", (
        P(0, "enable", "bool"), P(1, "pitch", "deci-semitones"),
    )),
    "pro_reverb": Effect(13, "Mic Pro Reverb", (
        P(0, "enable", "bool"),
        P(1, "dry", evidence="inferred", writable=False),
        P(2, "wet", evidence="inferred", writable=False),
        P(3, "erwet"),
        P(4, "erfactor", evidence="inferred", writable=False),
        P(5, "erwidth", evidence="inferred", writable=False),
        P(6, "ertolate", evidence="inferred", writable=False),
        P(7, "rt60", "ms", "inferred", False),
        P(8, "delay", "ms", "inferred", False),
        P(9, "width", "%", "inferred", False),
        P(10, "wander", evidence="inferred", writable=False),
        P(11, "spin", evidence="inferred", writable=False),
        P(12, "input_lpf", "Hz", "inferred", False),
        P(13, "damp_lpf", "Hz", "inferred", False),
        P(14, "bass_lpf", "Hz", "inferred", False),
        P(15, "bassb", evidence="inferred", writable=False),
        P(16, "output_lpf", "Hz", "inferred", False),
    )),
}


def q15_from_db(db: float) -> int:
    """Observed for -6/-7/-8 dB: truncation of gain*32768."""
    if db > 0:
        raise ValueError("positive dB conversion not validated")
    return max(0, min(32767, int(32768 * 10 ** (db / 20))))


def db_from_q15(value: int) -> float:
    if not 0 <= value <= 32767:
        raise ValueError("invalid Q15 gain")
    return float("-inf") if value == 0 else 20 * log10(value / 32768)
