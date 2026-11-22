"""Offline tests for first reversible write *proposal*, never a live write."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from bpcontrol.acp import ACPFrame
from bpcontrol.device_info import parse_firmware_info, parse_system_status
from bpcontrol.snapshot import build_snapshot, read_catalog
from tools.plan_chorus_probe import plan


ROOT = Path(__file__).resolve().parents[1]


class OfflineChorusProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = read_catalog()
        cls.firmware = parse_firmware_info(ACPFrame(
            0, bytes.fromhex("30 00 03 00 02 18 00")
        ))
        cls.status = parse_system_status(ACPFrame(
            2, bytes.fromhex("FF 46 00 1A 00 00 40 01 40 01")
        ))

    def fixture(self):
        # Fully synthetic instance data; format matches a live snapshot, but
        # NO physical hardware was contacted. Never publish as real BP1032 state.
        replies = {}
        for row in self.catalog["effects"]:
            index = row["index"]
            payload = b"\xFF" + bytes(2 * len(row["parameter_hints"]))
            if index == 15:
                payload = bytes.fromhex(
                    "FF 01 00 14 00 0A 00 C8 00 32 00 50 00 50 00"
                )
            replies[index] = ACPFrame(int(row["command"], 16), payload)
        return build_snapshot(self.catalog, self.firmware, self.status, replies)

    def test_proposal_is_one_step_only_and_byte_exact(self):
        p = plan(self.fixture())
        self.assertEqual(p["mode"], "OFFLINE_PLAN_ONLY")
        self.assertFalse(p["device_access"])
        self.assertEqual(p["snapshot_wet"], 80)
        self.assertEqual(p["proposed_wet"], 79)
        self.assertEqual(p["step_raw"], 1)
        self.assertEqual(p["read_acp_frame"], "A5 5A 8F 00 16")
        self.assertEqual(p["candidate_write_acp_frame"], "A5 5A 8F 03 06 4F 00 16")
        self.assertEqual(p["rollback_acp_frame"], "A5 5A 8F 03 06 50 00 16")

    def test_demo_is_refused(self):
        demo = json.loads((ROOT / "data" / "demo_snapshot.json").read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            plan(demo)

    def test_modified_firmware_is_refused(self):
        obj = self.fixture()
        obj["device"]["effects_library_version"] = "2.25.0"
        with self.assertRaisesRegex(ValueError, "audit"):
            plan(obj)

    def test_corrupt_raw_bytes_refused(self):
        obj = self.fixture()
        obj["effects"][14]["fields"][6]["signed"] = 79
        obj["effects"][14]["fields"][6]["unsigned"] = 79
        with self.assertRaisesRegex(ValueError, "audit"):
            plan(obj)

    def test_out_of_range_wet_refused_even_when_structural_audit_passes(self):
        obj = self.fixture()
        obj["effects"][14]["fields"][6]["signed"] = 120
        obj["effects"][14]["fields"][6]["unsigned"] = 120
        obj["effects"][14]["raw_payload_hex"] = (
            obj["effects"][14]["raw_payload_hex"][:-5] + "78 00"
        )
        # Set a fully-consistent payload for range checking.
        payload = bytes.fromhex(obj["effects"][14]["raw_payload_hex"])
        self.assertEqual(int.from_bytes(payload[-2:], "little"), 120)
        with self.assertRaisesRegex(ValueError, "outside 0..100"):
            plan(obj)

    def test_zero_wet_proposes_upward_step(self):
        obj = self.fixture()
        obj["effects"][14]["fields"][6]["signed"] = 0
        obj["effects"][14]["fields"][6]["unsigned"] = 0
        payload = bytearray.fromhex(obj["effects"][14]["raw_payload_hex"])
        payload[-2:] = b"\x00\x00"
        obj["effects"][14]["raw_payload_hex"] = bytes(payload).hex(" ").upper()
        result = plan(obj)
        self.assertEqual(result["proposed_wet"], 1)
        self.assertEqual(result["rollback_acp_frame"], "A5 5A 8F 03 06 00 00 16")

    def test_effect_mapping_must_match_evidence(self):
        obj = self.fixture()
        obj["effects"][14]["fields"][6]["mapping"] = "unknown"
        with self.assertRaisesRegex(ValueError, "individually mapped"):
            plan(obj)


if __name__ == "__main__":
    unittest.main()
