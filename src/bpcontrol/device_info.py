"""Strict ACP firmware and system-status decoders (application layer, no USB I/O).

Grounded in MVSilicon communication protocol V2.40.0:
- 0x00 response: firmware family (u8), firmware semantic version (u8*3),
  effects library semantic version (u8*3).
- 0x02 response: FF marker + memory usage (u16 LE, KB) + CPU usage (u16 LE,
  unit shown as MCPS by ACPWorkbench manual, section 8.1) + external-change flag (u8) +
  max CPU frequency (u16 LE, MHz) + max memory (u16 LE, KB).
"""
from __future__ import annotations

from dataclasses import dataclass

from .acp import ACPError, ACPFrame

_FIRMWARE_TYPES = {
    0x30: "BPxx AudioPlay SDK",
    0x31: "BPxx Karaoke SDK",
}


@dataclass(frozen=True)
class FirmwareInfo:
    type_code: int
    family: str
    firmware_version: str
    effects_library_version: str


@dataclass(frozen=True)
class SystemStatus:
    memory_kb: int
    cpu_usage_raw: int
    external_parameter_change: bool
    cpu_max_mhz: int
    memory_max_kb: int

    @property
    def memory_percent(self) -> float | None:
        return 100.0 * self.memory_kb / self.memory_max_kb if self.memory_max_kb else None

    @property
    def cpu_mcps(self) -> int:
        """ACPWorkbench manual 2.25.0 §8.1: mega cycles/second (NOT MIPS)."""
        return self.cpu_usage_raw

    @property
    def cpu_percent_of_nominal_max(self) -> float | None:
        """Ratio to max MHz, not guaranteed instant CPU utilization."""
        return 100.0 * self.cpu_mcps / self.cpu_max_mhz if self.cpu_max_mhz else None


def parse_firmware_info(frame: ACPFrame) -> FirmwareInfo:
    if frame.command != 0x00 or len(frame.payload) != 7:
        raise ACPError("expected firmware (0x00) reply with 7-byte payload")
    p = frame.payload
    return FirmwareInfo(
        type_code=p[0],
        family=_FIRMWARE_TYPES.get(p[0], f"Unrecognized firmware type 0x{p[0]:02X}"),
        firmware_version=f"{p[1]}.{p[2]}.{p[3]}",
        effects_library_version=f"{p[4]}.{p[5]}.{p[6]}",
    )


def parse_system_status(frame: ACPFrame) -> SystemStatus:
    if frame.command != 0x02 or len(frame.payload) != 10:
        raise ACPError("expected status (0x02) reply with 10-byte payload")
    p = frame.payload
    if p[0] != 0xFF:
        raise ACPError("system-status reply must start with 0xFF marker")
    if p[5] not in (0, 1):
        raise ACPError("system-status external change flag must be 0 or 1")
    return SystemStatus(
        memory_kb=int.from_bytes(p[1:3], "little"),
        cpu_usage_raw=int.from_bytes(p[3:5], "little"),
        external_parameter_change=bool(p[5]),
        cpu_max_mhz=int.from_bytes(p[6:8], "little"),
        memory_max_kb=int.from_bytes(p[8:10], "little"),
    )
