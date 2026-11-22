"""M1D auditor tests: complete/partial snapshots, corrupt values, INI mismatches.

All snapshots in this module are synthetic or clearly labeled demo examples.
No USB device is opened by these tests.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from bpcontrol.acp import ACPFrame
from bpcontrol.device_info import parse_firmware_info, parse_system_status
from bpcontrol.snapshot import build_snapshot, read_catalog
from tools.audit_snapshot import audit_snapshot

ROOT = Path(__file__).resolve().parents[1]


class SnapshotAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = read_catalog()
        cls.firmware = parse_firmware_info(ACPFrame(
            0x00, bytes.fromhex("30 00 03 00 02 18 00")
        ))
        cls.status = parse_system_status(ACPFrame(
            0x02, bytes.fromhex("FF 46 00 1A 00 00 40 01 40 01")
        ))

    def synthetic_complete(self):
        # Test fixture: all zeros, *not* observations from the physical board.
        replies = {}
        for row in self.catalog["effects"]:
            count = len(row["parameter_hints"])
            replies[row["index"]] = ACPFrame(
                int(row["command"], 16), b"\xFF" + bytes(2 * count)
            )
        return build_snapshot(self.catalog, self.firmware, self.status, replies)

    def test_demo_has_one_historical_read_and_58_unread(self):
        demo = json.loads((ROOT / "data" / "demo_snapshot.json").read_text(encoding="utf-8"))
        report = audit_snapshot(demo, self.catalog)
        self.assertFalse(report["complete"])
        self.assertEqual(report["valid_read"], 1)
        self.assertEqual(report["unread"], 58)
        self.assertEqual(report["audit_errors"], 0)

    def test_synthetic_complete_is_structurally_valid(self):
        report = audit_snapshot(self.synthetic_complete(), self.catalog)
        self.assertTrue(report["complete"])
        self.assertEqual(report["valid_read"], 59)
        self.assertEqual(report["schema_mapped_effects"], 6)
        self.assertEqual(report["raw_only_effects"], 53)
        self.assertEqual(report["ini_count_mismatches"], 0)
        self.assertEqual(report["audit_errors"], 0)

    def test_audit_detects_corrupt_signed_word(self):
        snapshot = self.synthetic_complete()
        snapshot["effects"][0]["fields"][0]["signed"] = 100
        report = audit_snapshot(snapshot, self.catalog)
        self.assertIn("signed_unsigned", [f["code"] for f in report["findings"]])
        self.assertGreater(report["audit_errors"], 0)

    def test_audit_detects_raw_payload_word_discrepancy(self):
        snapshot = self.synthetic_complete()
        # Signed and unsigned still agree, but the byte-exact ACP data disagrees.
        snapshot["effects"][0]["fields"][0]["signed"] = 1
        snapshot["effects"][0]["fields"][0]["unsigned"] = 1
        report = audit_snapshot(snapshot, self.catalog)
        self.assertIn("payload_field_mismatch", [f["code"] for f in report["findings"]])
        self.assertGreater(report["audit_errors"], 0)

    def test_audit_detects_wrong_firmware_version(self):
        snapshot = self.synthetic_complete()
        snapshot["device"]["effects_library_version"] = "2.24.1"
        report = audit_snapshot(snapshot, self.catalog)
        self.assertIn("firmware_catalog_mismatch", [f["code"] for f in report["findings"]])
        self.assertGreater(report["audit_errors"], 0)

    def test_audit_reports_label_quality_per_instance(self):
        snapshot = self.synthetic_complete()
        report = audit_snapshot(snapshot, self.catalog)
        self.assertEqual(len(report["instances"]), 59)
        # M1I: Chorus rate scaling is now explicitly marked inferred after
        # ACPWorkbench manual raw/10 conflicted with earlier raw/100
        # and a physical readback of 200. Field count is still known.
        self.assertEqual(report["instances"][14]["mapping_level"],
                         "known_schema_with_inference")
        self.assertEqual(report["instances"][41]["mapping_level"], "raw_only")
        self.assertEqual(report["instances"][12]["mapping_level"],
                         "known_schema_with_inference")

    def test_audit_detects_command_mismatch(self):
        snapshot = self.synthetic_complete()
        snapshot["effects"][10]["command"] = "0xFD"
        report = audit_snapshot(snapshot, self.catalog)
        self.assertIn("command_mismatch", [f["code"] for f in report["findings"]])
        self.assertGreater(report["audit_errors"], 0)

    def test_audit_detects_ini_parameter_count_mismatch_without_approving_write(self):
        snapshot = self.synthetic_complete()
        snapshot["effects"][20]["fields"].pop()
        report = audit_snapshot(snapshot, self.catalog)
        self.assertIn("ini_count_mismatch", [f["code"] for f in report["findings"]])
        self.assertEqual(report["ini_count_mismatches"], 1)
        self.assertGreater(report["audit_warnings"], 0)

    def test_audit_detects_false_complete(self):
        demo = json.loads((ROOT / "data" / "demo_snapshot.json").read_text(encoding="utf-8"))
        demo["complete"] = True
        report = audit_snapshot(demo, self.catalog)
        self.assertIn("incomplete_flag", [f["code"] for f in report["findings"]])

    def test_partial_error_record_preserved(self):
        partial = build_snapshot(self.catalog, self.firmware, self.status, {},
                                 failed_index=1, error="test failure")
        report = audit_snapshot(partial, self.catalog)
        self.assertEqual(report["valid_read"], 0)
        self.assertEqual(report["unread"], 58)
        self.assertEqual(report["errors_in_capture"], 1)
        self.assertGreater(report["audit_warnings"], 0)

    def test_rejects_wrong_effect_array_length(self):
        snapshot = self.synthetic_complete()
        snapshot["effects"].pop()
        with self.assertRaisesRegex(ValueError, "Expected 59"):
            audit_snapshot(snapshot, self.catalog)


if __name__ == "__main__":
    unittest.main()
