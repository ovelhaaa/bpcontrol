"""Offline tests for M1K-A Exciter schema audit and staged editor prototype."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from bpcontrol.acp import decode_frame
from bpcontrol.exciter_editor import (
    EXCITER_LIVE_WRITE_ENABLED,
    ExciterOfflineSession,
    assess_exciter_draft,
    build_exciter_preview_hex,
    parse_exciter_draft,
)
from bpcontrol.exciter_evidence import (
    EXCITER_AUDIT_FIELDS,
    EXCITER_COMMAND,
    EXCITER_INDEX,
    EXCITER_LIVE_WRITES_AUTHORIZED,
    exciter_audit_summary,
)
from tools.exciter_editor_gui import DEFAULT_OFFLINE_BASELINE, load_exciter_baseline


class ExciterEvidenceTests(unittest.TestCase):
    def test_schema_audit_preserves_cutoff_discrepancy_and_read_only_gate(self):
        self.assertEqual(EXCITER_COMMAND, 0x9D)
        self.assertEqual(EXCITER_INDEX, 29)
        self.assertFalse(EXCITER_LIVE_WRITES_AUTHORIZED)
        self.assertEqual(len(EXCITER_AUDIT_FIELDS), 4)
        self.assertTrue(all(not f.writable_now for f in EXCITER_AUDIT_FIELDS))

        summary = exciter_audit_summary()
        self.assertFalse(summary["live_writes_authorized"])
        disc = summary["cutoff_discrepancy"]
        self.assertEqual(disc["acp_v240_min_hz"], 300)
        self.assertEqual(disc["sdk_bp1048_min_hz"], 1000)
        self.assertEqual(disc["operator_reported_acpworkbench_min_hz"], 1000)
        self.assertEqual(disc["max_hz"], 10000)
        self.assertEqual(disc["status"], "reported_physical_observation_not_full_bounds_proof")


class ExciterOfflineEditorTests(unittest.TestCase):
    def test_live_writes_are_strictly_disabled(self):
        self.assertFalse(EXCITER_LIVE_WRITE_ENABLED)
        session = ExciterOfflineSession()
        with self.assertRaises(PermissionError):
            session.send_live_write("cutoff_frequency", 1500)

    def test_draft_parsing_and_bounds(self):
        self.assertEqual(parse_exciter_draft("enable", "1"), 1)
        self.assertEqual(parse_exciter_draft("cutoff_frequency", "1000"), 1000)
        self.assertEqual(parse_exciter_draft("cutoff_frequency", "10000"), 10000)
        self.assertEqual(parse_exciter_draft("dry", "0"), 0)
        self.assertEqual(parse_exciter_draft("wet", "100"), 100)

        for bad_field, bad_val in (
            ("enable", "2"),
            ("cutoff_frequency", "300"),
            ("cutoff_frequency", "999"),
            ("cutoff_frequency", "10001"),
            ("cutoff_frequency", "1500.5"),
            ("dry", "-1"),
            ("wet", "101"),
            ("wet", ""),
            ("unknown", "1"),
        ):
            with self.assertRaises(ValueError):
                parse_exciter_draft(bad_field, bad_val)

    def test_preview_hex_and_offline_stage_undo(self):
        preview = build_exciter_preview_hex("cutoff_frequency", 2000)
        frame = decode_frame(bytes.fromhex(preview))
        self.assertEqual(frame.command, 0x9D)
        self.assertEqual(frame.payload[0], 1)
        self.assertEqual(int.from_bytes(frame.payload[1:3], "little", signed=True), 2000)

        view = assess_exciter_draft("dry", "75", (1, 1000, 80, 50))
        self.assertEqual(view.state, "ready_offline")
        self.assertTrue(view.can_stage_offline)
        self.assertTrue(view.live_write_blocked)
        self.assertEqual(view.delta, -5)

        session = ExciterOfflineSession((1, 1000, 80, 50))
        session.stage_apply("cutoff_frequency", "2000")
        self.assertEqual(session.current, (1, 2000, 80, 50))
        session.stage_apply("wet", "60")
        self.assertEqual(session.current, (1, 2000, 80, 60))

        undone = session.stage_undo()
        self.assertEqual(undone, ("wet", 60, 50))
        self.assertEqual(session.current, (1, 2000, 80, 50))
        undone2 = session.stage_undo()
        self.assertEqual(undone2, ("cutoff_frequency", 2000, 1000))
        self.assertEqual(session.current, (1, 1000, 80, 50))
        with self.assertRaises(ValueError):
            session.stage_undo()

    def test_snapshot_loader_falls_back_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "missing.json"
            vals, origin = load_exciter_baseline(missing)
            self.assertEqual(vals, DEFAULT_OFFLINE_BASELINE)
            self.assertIn("sintético", origin.lower())

            snap = Path(d) / "snap.json"
            snap.write_text(
                json.dumps({
                    "effects": [{
                        "index": 29,
                        "status": "ok",
                        "fields": [{"signed": 1}, {"signed": 1200}, {"signed": 70}, {"signed": 45}],
                    }]
                }),
                encoding="utf-8",
            )
            vals2, origin2 = load_exciter_baseline(snap)
            self.assertEqual(vals2, (1, 1200, 70, 45))
            self.assertIn("snap.json", origin2)

    def test_no_usb_modules_imported_by_exciter_offline_prototype(self):
        import ast

        root = Path(__file__).resolve().parents[1]
        forbidden = ("usb_hid", "usb_read_only", "usb_chorus_probe", "usb_snapshot", "ctypes")
        for rel in (
            "src/bpcontrol/exciter_evidence.py",
            "src/bpcontrol/exciter_editor.py",
            "tools/exciter_editor_gui.py",
        ):
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
            for mod in imported:
                for bad in forbidden:
                    self.assertNotIn(bad, mod, f"{rel} must not import {mod}")


if __name__ == "__main__":
    unittest.main()
