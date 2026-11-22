"""Audit one saved BPControl snapshot *offline* before enabling any editor.

Never connects to USB, never sends ACP, and does not write the snapshot.
Provides evidence-graded parameter count checks, schema name mismatches,
signed/unsigned consistency, plus a useful, pasteable summary.

Usage:
  py tools/audit_snapshot.py artifacts/snapshots/bp1032-01.json
  py tools/audit_snapshot.py data/demo_snapshot.json
"""
from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bpcontrol.snapshot import read_catalog, SCHEMA_BY_INDEX


def audit_snapshot(snapshot: dict, catalog: dict) -> dict:
    """Pure, deterministic, no I/O audit; returns summary and detailed findings."""
    entries = snapshot.get("effects")
    if snapshot.get("format") != "bpcontrol-snapshot-v1" or not isinstance(entries, list):
        raise ValueError("Not a BPControl snapshot v1")
    expected = catalog["effects"]
    if len(entries) != len(expected):
        raise ValueError(f"Expected {len(expected)} effect entries, got {len(entries)}")

    findings = []
    statuses = Counter()
    meta = snapshot.get("device") or {}
    expected_versions = (
        catalog.get("firmware_type"),
        catalog.get("firmware_version"),
        catalog.get("effects_library_version"),
    )
    got_versions = (
        meta.get("firmware_type"),
        meta.get("firmware_version"),
        meta.get("effects_library_version"),
    )
    field_count = 0
    schema_mapped = 0
    mismatches = 0
    ambiguous = 0
    seen = set()

    def report(index: int, severity: str, code: str, detail: str) -> None:
        findings.append({
            "index": index, "severity": severity, "code": code, "detail": detail
        })

    if expected_versions != got_versions:
        report(0, "error", "firmware_catalog_mismatch",
               f"catalog versions {expected_versions}, snapshot versions {got_versions}; "
               "cannot safely associate field names")
    if snapshot.get("effect_count_expected") != len(expected):
        report(0, "error", "expected_count",
               f"effect_count_expected={snapshot.get('effect_count_expected')}; "
               f"catalog={len(expected)}")
    for expected_row, effect in zip(expected, entries):
        index = effect.get("index")
        if index != expected_row["index"] or index in seen:
            report(expected_row["index"], "error", "instance_order",
                   f"expected {expected_row['index']}; got {index}")
        seen.add(index)
        if effect.get("command") != expected_row["command"]:
            report(expected_row["index"], "error", "command_mismatch",
                   f"expected {expected_row['command']}; got {effect.get('command')}")
        if effect.get("name") != expected_row["name"]:
            report(expected_row["index"], "warning", "catalog_name",
                   "saved snapshot uses a different effect name than INI catalog")

        status = effect.get("status")
        statuses[status] += 1
        if status not in ("ok", "error", "unread"):
            report(expected_row["index"], "error", "unknown_status", repr(status))
            continue
        fields = effect.get("fields", [])
        if not isinstance(fields, list):
            report(expected_row["index"], "error", "invalid_fields", "fields must be an array")
            continue
        if status != "ok":
            if fields:
                report(expected_row["index"], "error", "unexpected_fields",
                       "unread/failed effect contains field values")
            if status == "error":
                report(expected_row["index"], "warning", "read_failure",
                       str(effect.get("error", "unknown error")))
            continue

        field_count += len(fields)
        hint_count = len(expected_row.get("parameter_hints", []))
        if len(fields) != hint_count:
            mismatches += 1
            report(expected_row["index"], "warning", "ini_count_mismatch",
                   f"readback={len(fields)} fields; INI has {hint_count} hints; "
                   "INI is only a reference, not a proven field schema")
        schema = SCHEMA_BY_INDEX.get(index)
        if schema is not None:
            if len(fields) != len(schema.params):
                report(expected_row["index"], "warning", "known_schema_count",
                       f"readback={len(fields)} fields; evidence-graded schema has "
                       f"{len(schema.params)}")
            elif effect.get("schema_match") is not True:
                report(expected_row["index"], "warning", "schema_flag",
                       "field count matches known schema but schema_match is not true")
            else:
                schema_mapped += 1
        else:
            ambiguous += 1
        if len(fields) > 125:
            report(expected_row["index"], "error", "hid_capacity",
                   "more than 125 signed 16-bit words cannot fit one 256-byte ACP report")
        for position, field in enumerate(fields):
            if field.get("index") != position:
                report(expected_row["index"], "error", "field_index",
                       f"field {position} has index {field.get('index')}")
            signed, unsigned = field.get("signed"), field.get("unsigned")
            if type(signed) is not int or type(unsigned) is not int or not (0 <= unsigned <= 65535):
                report(expected_row["index"], "error", "raw_16bit",
                       f"invalid raw signed/u16 value at field {position}")
            elif signed != (unsigned if unsigned < 32768 else unsigned - 65536):
                report(expected_row["index"], "error", "signed_unsigned",
                       f"field {position}: signed={signed}, unsigned={unsigned}")

        # Confirm the JSON fields correspond exactly to the saved, byte-exact ACP payload.
        # Valid bytes do not, by themselves, prove an INI hint or field range.
        raw_hex = effect.get("raw_payload_hex")
        if not isinstance(raw_hex, str):
            report(expected_row["index"], "error", "missing_raw_payload",
                   "successful read has no raw ACP payload")
        else:
            try:
                payload = bytes.fromhex(raw_hex)
            except ValueError:
                report(expected_row["index"], "error", "invalid_raw_payload",
                       "raw_payload_hex is not hexadecimal")
            else:
                if (not payload or payload[0] != 0xFF or
                        len(payload) != 1 + 2 * len(fields) or
                        len(payload) > 251):
                    report(expected_row["index"], "error", "raw_payload_length",
                           f"payload bytes={len(payload)}; fields={len(fields)}")
                else:
                    for position, field in enumerate(fields):
                        word = field.get("unsigned")
                        if (type(word) is int and 0 <= word <= 65535
                                and payload[1 + position * 2:3 + position * 2]
                                    != word.to_bytes(2, "little")):
                            report(expected_row["index"], "error", "payload_field_mismatch",
                                   f"field {position} differs from captured ACP bytes")

    per_instance = []
    for expected_row, effect in zip(expected, entries):
        fields = effect.get("fields")
        schema = SCHEMA_BY_INDEX.get(expected_row["index"])
        status = effect.get("status")
        observed_count = len(fields) if isinstance(fields, list) else None
        ini_count = len(expected_row.get("parameter_hints", []))
        confirmed_mapping = (
            status == "ok" and schema is not None and
            observed_count == len(schema.params) and
            effect.get("schema_match") is True
        )
        inferred_fields = (
            sum(p.evidence == "inferred" for p in schema.params)
            if confirmed_mapping else 0
        )
        per_instance.append({
            "index": expected_row["index"],
            "command": expected_row["command"],
            "name": expected_row["name"],
            "type_name": expected_row["type_name"],
            "status": status,
            "observed_fields": observed_count,
            "ini_hints": ini_count,
            "known_schema": schema is not None,
            "schema_matched": confirmed_mapping,
            "inferred_fields": inferred_fields,
            "mapping_level": (
                "not_read" if status != "ok" else
                "known_schema_with_inference" if confirmed_mapping and inferred_fields else
                "known_schema" if confirmed_mapping else
                "raw_only"
            ),
        })

    count_ok = statuses["ok"]
    declared_read = snapshot.get("effect_count_read")
    if declared_read != count_ok:
        report(0, "error", "read_count",
               f"effect_count_read={declared_read}, but ok={count_ok}")
    if snapshot.get("complete") and count_ok != 59:
        report(0, "error", "incomplete_flag", "complete=true while fewer than 59 read successfully")
    if not snapshot.get("complete") and count_ok == 59:
        report(0, "warning", "all_read_but_partial",
               "59 successful reads but snapshot says complete=false; review its error state")
    return {
        "complete": snapshot.get("complete") is True,
        "declared_read": declared_read,
        "valid_read": count_ok,
        "unread": statuses["unread"],
        "errors_in_capture": statuses["error"],
        "total_raw_fields": field_count,
        "schema_mapped_effects": schema_mapped,
        "raw_only_effects": ambiguous,
        "ini_count_mismatches": mismatches,
        "audit_errors": sum(f["severity"] == "error" for f in findings),
        "audit_warnings": sum(f["severity"] == "warning" for f in findings),
        "findings": findings,
        "instances": per_instance,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit BP1032 read-only snapshot JSON (NO USB)")
    parser.add_argument("snapshot", type=Path)
    format_group = parser.add_mutually_exclusive_group()
    format_group.add_argument("--json", action="store_true",
                              help="print machine-readable audit report")
    format_group.add_argument("--table", action="store_true",
                              help="print one summary line for each of the 59 instances")
    args = parser.parse_args()
    try:
        obj = json.loads(args.snapshot.read_text(encoding="utf-8"))
        report = audit_snapshot(obj, read_catalog())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Cannot audit snapshot: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.table:
        print("BPCONTROL M1D — PARAMETER COUNTS (offline, never writes to DSP)")
        print(" ID  ACP   LIVE   INI  LABEL QUALITY                  EFFECT")
        print(" --  ----  -----  ---  -----------------------------  --------------------------------")
        for row in report["instances"]:
            count = str(row["observed_fields"]) if row["observed_fields"] is not None else "—"
            print(f" {row['index']:02d}  {row['command']:4}  {count:>5}  "
                  f"{row['ini_hints']:>3}  {row['mapping_level']:<29}  "
                  f"{row['name'][:38]}")
        print(f"Audit errors={report['audit_errors']}, warnings={report['audit_warnings']}; "
              "see --json for details. None of these labels authorizes writes.")
    else:
        print("BPCONTROL M1D — OFFLINE AUDIT (no USB / no writes)")
        print(f"Snapshot marked complete: {report['complete']}")
        print(f"Read successfully: {report['valid_read']}/59"
              f"  (declared: {report['declared_read']})")
        print(f"Unread: {report['unread']}  capture errors: {report['errors_in_capture']}")
        print(f"Raw signed/unsigned fields: {report['total_raw_fields']}")
        print(f"Known evidence-graded schema mappings: {report['schema_mapped_effects']}/6")
        print(f"Instances with raw-only labels: {report['raw_only_effects']}")
        print(f"Count mismatches vs INI hints: {report['ini_count_mismatches']}")
        print(f"Audit errors: {report['audit_errors']}  warnings: {report['audit_warnings']}")
        for item in report["findings"][:30]:
            print(f"  [{item['severity'].upper()}] "
                  f"effect {item['index']:02d}: {item['code']} — {item['detail']}")
        if len(report["findings"]) > 30:
            print(f"... plus {len(report['findings']) - 30} further findings; "
                  "use --json for the complete report")
        print("WARNING: INI names are hints. No field range, musical meaning or write "
              "permission is inferred from readback.")
    return 1 if report["audit_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
