"""M1I offline evidence tests: manual ranges are NOT write authorization."""
import unittest

from bpcontrol.acp import ACPFrame
from bpcontrol.chorus_evidence import (
    CHORUS_COMMAND, CHORUS_FIELDS, CHORUS_INDEX, CHORUS_PHYSICAL_BASELINE,
    evidence_rows, get_chorus_field, read_only_approximation,
    validate_live_chorus,
)
from bpcontrol.effects import EFFECTS
from bpcontrol.snapshot import effect_record, read_catalog


class ChorusEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = effect_record(
            read_catalog()["effects"][14],
            ACPFrame(0x8F, bytes.fromhex(
                "FF 01 00 14 00 0A 00 C8 00 32 00 50 00 50 00"
            )),
        )

    def test_seven_positions_correct_and_only_one_gui_writable(self):
        self.assertEqual(CHORUS_COMMAND, 0x8F)
        self.assertEqual(CHORUS_INDEX, 15)
        self.assertEqual([x.index for x in CHORUS_FIELDS], list(range(7)))
        self.assertEqual([x.key for x in CHORUS_FIELDS], [
            "enable", "delay_length", "modulation_depth",
            "modulation_rate", "feedback", "dry", "wet",
        ])
        self.assertEqual([x.index for x in CHORUS_FIELDS if x.writable_now], [6])
        for f in CHORUS_FIELDS[:6]:
            self.assertEqual(f.permission_label, "SOMENTE LEITURA")
        self.assertIn("Wet", CHORUS_FIELDS[6].permission_label)

    def test_manual_chorus_ranges_are_explained_not_assumed_proven(self):
        self.assertIn("1–25 ms", CHORUS_FIELDS[1].range_evidence)
        self.assertIn("delay_length−1", CHORUS_FIELDS[2].range_evidence)
        self.assertIn("0–50%", CHORUS_FIELDS[4].range_evidence)
        self.assertIn("0–100%", CHORUS_FIELDS[5].range_evidence)
        self.assertIn("0–100%", CHORUS_FIELDS[6].range_evidence)
        self.assertIn("raw=200", CHORUS_FIELDS[3].scale_evidence)
        self.assertIn("2,00 Hz", CHORUS_FIELDS[3].scale_evidence)
        self.assertIn("raw/100", CHORUS_FIELDS[3].scale_evidence)
        self.assertIn("raw=1000", CHORUS_FIELDS[3].scale_evidence)
        self.assertIn("10,00 Hz", CHORUS_FIELDS[3].scale_evidence)
        self.assertIn("raw/10", CHORUS_FIELDS[3].scale_evidence)
        self.assertIn("raw=200", CHORUS_FIELDS[3].range_evidence)

    def test_sdk_evidence_is_not_physical_writing_authority(self):
        rate = CHORUS_FIELDS[3]
        self.assertIn("SDK BP1048", rate.scale_evidence)
        self.assertIn("Protocolo V2.40", rate.range_evidence)
        self.assertIn("raw=200", rate.range_evidence)
        self.assertIn("raw=1000", rate.range_evidence)
        self.assertIn("10", rate.range_evidence)
        self.assertIn("docs/M1I_PROTOCOL_SDK_CROSSCHECK.md", rate.evidence_sources)
        self.assertIn("docs/M1I_PHYSICAL_RATE_PAIR.md", rate.evidence_sources)
        self.assertFalse(rate.writable_now)
        self.assertEqual(rate.permission_label, "SOMENTE LEITURA")
        self.assertTrue(CHORUS_FIELDS[6].writable_now)

    def test_only_two_operator_observed_rate_pairs_are_displayed_in_hz(self):
        observed = {
            200: "2,00 Hz · ponto observado na BP1032 (raw=200)",
            1000: "10,00 Hz · ponto observado na BP1032 (raw=1000)",
        }
        for raw, expected in observed.items():
            with self.subTest(raw=raw):
                self.assertEqual(read_only_approximation(3, raw), expected)
        for raw in (0, 10, 100, 199, 201, 500, 999, 1001, -1):
            with self.subTest(raw=raw):
                result = read_only_approximation(3, raw)
                self.assertIn("hipótese", result)
                self.assertNotIn(" Hz", result)
        # The two observations support this numerical ratio but not an
        # automatic claim about arbitrary or physical boundary values.
        self.assertEqual(200/2.0, 1000/10.0)
        with self.assertRaises(ValueError):
            read_only_approximation(3, 32768)
        with self.assertRaises(ValueError):
            get_chorus_field(True)

    def test_live_and_snapshot_data_have_explicit_provenance(self):
        saved = evidence_rows(self.record)
        self.assertEqual(len(saved), 7)
        self.assertTrue(all(x["current_origin"] == "Snapshot salvo" for x in saved))
        self.assertEqual(saved[3]["current_raw"], 200)
        self.assertIn("ponto observado", saved[3]["approximation"])
        live_values = (1, 20, 10, 200, 50, 80, 81)
        live = evidence_rows(self.record, live_values)
        self.assertEqual(live[6]["current_raw"], 81)
        self.assertEqual(live[6]["snapshot_raw"], 80)
        self.assertEqual(live[6]["current_origin"], "USB / leitura atual")
        self.assertEqual([x["index"] for x in live if x["writable_now"]], [6])
        high_rate = (1, 20, 10, 1000, 50, 80, 80)
        observed = evidence_rows(self.record, high_rate)
        self.assertEqual(observed[3]["current_raw"], 1000)
        self.assertIn("10,00 Hz", observed[3]["approximation"])
        self.assertEqual(observed[3]["permission"], "SOMENTE LEITURA")
        self.assertEqual(CHORUS_PHYSICAL_BASELINE, (1, 20, 10, 200, 50, 80, 80))

    def test_malformed_or_mismatched_live_data_refused(self):
        with self.assertRaises(ValueError):
            evidence_rows({"index": 16, "command": "0x90", "fields": []})
        with self.assertRaises(ValueError):
            evidence_rows({"index": 15, "command": "0x8F", "fields": [{}]})
        for live in ((1,), [1, 2, 3, 4, 5, 6, 7],
                     (1, 2, 3, 4, 5, 6, True),
                     (1, 2, 3, 4, 5, 6, 70000)):
            with self.subTest(live=live), self.assertRaises(ValueError):
                validate_live_chorus(live)

    def test_effect_schema_cannot_authorize_other_chorus_fields(self):
        chorus = EFFECTS["guitar_chorus"]
        self.assertEqual(
            [f.index for f in chorus.params if f.writable], [6]
        )
        self.assertEqual(chorus.params[3].unit, "raw")
        self.assertFalse(chorus.params[3].writable)


if __name__ == "__main__":
    unittest.main()
