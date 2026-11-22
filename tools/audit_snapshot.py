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
    field_count = 0
    schema_mapped = 0
    mismatches = 0
    ambiguous = 0
    seen = set()

    def report(index: int, severity: str, code: str, detail: str) -> None:
        findings.append({
            "index": index, "severity": severity, "code": code, "detail": detail
        })

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

    count_ok = statuses["ok"]
    declared_read = snapshot.get("effect_count_read")
    if declared_read != count_ok:
        report(0, "error", "read_count",
               f"effect_count_read={declared_read}, but ok={count_ok}")
    if snapshot.get("complete") and count_ok != 59:
        report(0, "error", "incomplete_flag", "complete=true while fewer than 59 read successfully")
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
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit BP1032 read-only snapshot JSON (NO USB)")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--json", action="store_true", help="print machine-readable audit report")
    args = parser.parse_args()
    try:
        obj = json.loads(args.snapshot.read_text(encoding="utf-8"))
        report = audit_snapshot(obj, read_catalog())
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Cannot audit snapshot: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
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
