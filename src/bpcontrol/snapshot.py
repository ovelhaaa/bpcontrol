"""Pure, offline BP1032 59-instance snapshot model.

The saved INI supplies *hints*, never readback data or authority to write.
Only known and count-matching schema labels are treated as validated mappings.
All values are preserved as both signed and unsigned 16-bit representations.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .acp import ACPError, ACPFrame, effect_command
from .device_info import FirmwareInfo, SystemStatus
from .effects import EFFECTS

CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "effect_instances.json"
EXPECTED_FIRMWARE_TYPE = 0x30
EXPECTED_FIRMWARE = "0.3.0"
EXPECTED_EFFECT_LIBRARY = "2.24.0"
INSTANCE_COUNT = 59
SCHEMA_BY_INDEX = {e.index: e for e in EFFECTS.values()}


def read_catalog(path: Path = CATALOG_PATH) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = raw.get("effects", [])
    if not isinstance(entries, list) or len(entries) != INSTANCE_COUNT:
        raise ACPError("snapshot catalog must contain exactly 59 entries")
    for i, row in enumerate(entries, 1):
        if (row.get("index") != i or row.get("command") != f"0x{effect_command(i):02X}"
                or not isinstance(row.get("name"), str) or not row.get("name")
                or not isinstance(row.get("parameter_hints"), list)):
            raise ACPError(f"catalog mismatch at effect instance {i}")
    return raw


def require_observed_firmware(info: FirmwareInfo) -> None:
    if (info.type_code != EXPECTED_FIRMWARE_TYPE
            or info.firmware_version != EXPECTED_FIRMWARE
            or info.effects_library_version != EXPECTED_EFFECT_LIBRARY):
        raise ACPError(
            f"firmware not on observed allowlist: 0x{info.type_code:02X}, "
            f"{info.firmware_version}, library {info.effects_library_version}; "
            "no effect reads performed"
        )


def effect_record(row: dict, frame: ACPFrame | None = None, *, error: str | None = None) -> dict:
    index = row["index"]
    result = {
        "index": index,
        "command": row["command"],
        "name": row["name"],
        "group": row["group"],
        "type_id": row["type_id"],
        "type_name": row["type_name"],
        "status": "unread" if frame is None and error is None else ("error" if error else "ok"),
        "fields": [],
    }
    if error is not None:
        result["error"] = error
        return result
    if frame is None:
        return result
    if frame.command != effect_command(index):
        raise ACPError(f"effect {index}: wrong response command")
    payload = frame.payload
    if not payload or payload[0] != 0xFF or (len(payload) - 1) % 2:
        raise ACPError(f"effect {index}: expected FF + 16-bit parameter words")
    values = payload[1:]
    schema = SCHEMA_BY_INDEX.get(index)
    names_verified = schema is not None and len(schema.params) == len(values) // 2
    hints = row.get("parameter_hints", [])
    for j in range(0, len(values), 2):
        position = j // 2
        raw = values[j:j + 2]
        field = {
            "index": position,
            "signed": int.from_bytes(raw, "little", signed=True),
            "unsigned": int.from_bytes(raw, "little"),
            "name": f"field_{position:02d}",
            "unit": "raw",
            "mapping": "unknown",
        }
        if position < len(hints):
            field["ini_hint"] = hints[position]
        if names_verified:
            param = schema.params[position]
            field.update(name=param.name, unit=param.unit, mapping=param.evidence)
        result["fields"].append(field)
    result["raw_payload_hex"] = payload.hex(" ").upper()
    result["schema_match"] = bool(names_verified)
    result["ini_hint_count"] = len(hints)
    result["observed_field_count"] = len(result["fields"])
    return result


def build_snapshot(catalog: dict, firmware: FirmwareInfo, status: SystemStatus,
                   captured: dict[int, ACPFrame],
                   *, failed_index: int | None = None, error: str | None = None) -> dict:
    if error is None and len(captured) != INSTANCE_COUNT:
        raise ACPError("cannot mark snapshot complete without all 59 effects")
    records = []
    for row in catalog["effects"]:
        i = row["index"]
        records.append(effect_record(
            row, captured.get(i),
            error=error if i == failed_index else None
        ))
    return {
        "format": "bpcontrol-snapshot-v1",
        "source": "live_windows_hid" if error is None else "partial_live_windows_hid",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "complete": error is None,
        "error": error,
        "error_effect_index": failed_index,
        "device": {
            "manufacturer": "MV-SILICON",
            "product": "mvsilicon B1 usb audio",
            "interface": "MI_04",
            "firmware_type": f"0x{firmware.type_code:02X}",
            "firmware_family": firmware.family,
            "firmware_version": firmware.firmware_version,
            "effects_library_version": firmware.effects_library_version,
        },
        "system": {
            "memory_kb": status.memory_kb,
            "memory_max_kb": status.memory_max_kb,
            "memory_percent": status.memory_percent,
            "cpu_mcps": status.cpu_mcps,
            "cpu_max_mhz": status.cpu_max_mhz,
            "cpu_nominal_max_percent": status.cpu_percent_of_nominal_max,
            "external_parameter_change": status.external_parameter_change,
        },
        "effect_count_expected": INSTANCE_COUNT,
        "effect_count_read": len(captured),
        "effects": records,
        "notice": "Read-only snapshot; names/type/parameter hints from ACPWorkbench INI. "
                  "Only known six schemas have validated field-label mappings. "
                  "No write controls or persistent device operations."
    }
