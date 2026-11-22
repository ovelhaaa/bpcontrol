"""Propose a *DRY RUN ONLY* one-step reversible Chorus wet change.

No HID, USB, serial, GPIO, subprocess, or device access exists in this file.
The script only reads the existing JSON snapshot, validates the M1D audit,
and prints ACP frames for a future supervised experiment (NOT execution).

Usage:
  py tools/plan_chorus_probe.py artifacts/snapshots/bp1032-01.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from bpcontrol.acp import encode_read, encode_write
from bpcontrol.snapshot import read_catalog
from tools.audit_snapshot import audit_snapshot

CHORUS_INDEX = 15
WET_FIELD_INDEX = 6
EXPECTED_NAME = "wet"
MAX_STEP = 1


def plan(snapshot: dict) -> dict:
    catalog = read_catalog()
    report = audit_snapshot(snapshot, catalog)
    if report["audit_errors"] or report["audit_warnings"]:
        raise ValueError("Snapshot audit is not clean; no proposal generated")
    if not snapshot.get("complete") or report["valid_read"] != 59:
        raise ValueError("A complete, verified 59-effect live snapshot is required")
    if snapshot.get("source") != "live_windows_hid":
        raise ValueError("Must use a real saved Windows HID read, not demo data")
    chorus = snapshot["effects"][CHORUS_INDEX - 1]
    if (chorus.get("index") != CHORUS_INDEX or chorus.get("command") != "0x8F"
            or chorus.get("name") != "Guitar:Chorus"
            or chorus.get("status") != "ok"
            or chorus.get("schema_match") is not True
            or len(chorus.get("fields", [])) != 7):
        raise ValueError("Chorus field mapping does not match verified schema")
    wet = chorus["fields"][WET_FIELD_INDEX]
    if (wet.get("index") != WET_FIELD_INDEX or wet.get("name") != EXPECTED_NAME
            or wet.get("mapping") != "write_readback"
            or wet.get("unit") != "%"):
        raise ValueError("Chorus wet field is not individually mapped")
    current = wet.get("signed")
    if type(current) is not int or not (0 <= current <= 100):
        raise ValueError("Chorus wet current value is outside 0..100")
    # Maximum raw delta 1; if zero, take the reversible upward step.
    proposed = current - MAX_STEP if current > 0 else current + MAX_STEP
    snapshot_values = tuple(f["signed"] for f in chorus["fields"])
    if any(type(v) is not int for v in snapshot_values):
        raise ValueError("Chorus values must all be signed 16-bit integers")

    return {
        "mode": "OFFLINE_PLAN_ONLY",
        "device_access": False,
        "effect": "Guitar:Chorus",
        "effect_index": CHORUS_INDEX,
        "command": "0x8F",
        "field_index": WET_FIELD_INDEX,
        "field_name": EXPECTED_NAME,
        "snapshot_wet": current,
        "proposed_wet": proposed,
        "step_raw": abs(proposed - current),
        "snapshot_chorus_fields": list(snapshot_values),
        "read_acp_frame": encode_read(CHORUS_INDEX).hex(" ").upper(),
        "candidate_write_acp_frame": encode_write(
            CHORUS_INDEX, WET_FIELD_INDEX, proposed
        ).hex(" ").upper(),
        "rollback_acp_frame": encode_write(
            CHORUS_INDEX, WET_FIELD_INDEX, current
        ).hex(" ").upper(),
        "warnings": [
            "These are only printable ACP frames. The program CANNOT access or change the BP1032.",
            "The JSON is a snapshot and may no longer match the current live device state.",
            "Do not send a write until a physical USBPcap SET_REPORT/GET_REPORT ACK capture is reviewed.",
            "Future live code must reread current state, verify identity, perform one write, "
            "read back, restore the original value, and verify the restoration.",
            "A failed transfer may still have altered the device; rollback cannot be guaranteed "
            "if connection is lost. Never use ACP 0xFD/0xFE.",
        ]
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan a one-step Chorus wet write/rollback, OFFLINE ONLY"
    )
    parser.add_argument("snapshot", type=Path, help="complete 59/59 live snapshot JSON")
    parser.add_argument("--json", action="store_true", help="machine-readable proposal")
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        proposal = plan(snapshot)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(proposal, indent=2, ensure_ascii=False))
    else:
        print("BPCONTROL M1E — OFFLINE PROPOSAL ONLY (NO HARDWARE ACCESS)")
        print("Effect: Guitar:Chorus / ACP 0x8F / field 6: wet")
        print(f"Saved wet value: {proposal['snapshot_wet']}%")
        print(f"Candidate value: {proposal['proposed_wet']}% (delta 1)")
        print("Read ACP:       " + proposal["read_acp_frame"])
        print("Proposed write: " + proposal["candidate_write_acp_frame"])
        print("Rollback:       " + proposal["rollback_acp_frame"])
        for note in proposal["warnings"]:
            print("CAUTION: " + note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
