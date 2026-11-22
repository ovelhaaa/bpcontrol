"""Offline M1H presentation regression tests: no tkinter / no USB."""
from __future__ import annotations

from pathlib import Path
import unittest

from bpcontrol.editor_view_model import (
    GROUPS, assess_wet_draft, count_effects_by_group,
    display_value_origin, evidence_label, filter_effect_indices,
    validate_success_reply, stage_wet_step,
)
from bpcontrol.snapshot import read_catalog


CHORUS = (1, 20, 10, 200, 50, 80, 80)


class M1HViewModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.effects = read_catalog()["effects"]

    def test_all_59_browsable_and_groups_are_snapshot_only(self):
        self.assertEqual(filter_effect_indices(self.effects), list(range(1, 60)))
        counts = count_effects_by_group(self.effects)
        self.assertEqual(counts["Todos"], 59)
        self.assertEqual(sum(counts[g] for g in GROUPS if g != "Todos"), 59)
        self.assertEqual(
            filter_effect_indices(self.effects, "chorus", "Guitar"), [15]
        )
        self.assertEqual(
            filter_effect_indices(self.effects, "0x8f", "Guitar"), [15]
        )
        self.assertEqual(
            filter_effect_indices(self.effects, "CHORUS", "Mic"), []
        )
        with self.assertRaises(ValueError):
            filter_effect_indices(self.effects, "", "Invalid")

    def test_read_only_origin_remains_visible_for_58_effects(self):
        self.assertEqual(display_value_origin(15, CHORUS), "USB / leitura atual")
        self.assertEqual(display_value_origin(15, None), "Snapshot salvo")
        for index in range(1, 60):
            if index != 15:
                self.assertEqual(display_value_origin(index, CHORUS), "Snapshot salvo")

    def test_inferred_and_unknown_labels_never_authorize_writes(self):
        self.assertIn("leitura", evidence_label({"mapping":"unknown"}))
        self.assertIn("leitura", evidence_label({"mapping":"inferred"}))
        self.assertIn("leitura", evidence_label({"mapping":"write_readback"}))

    def test_unconfirmed_and_incomplete_drafts_never_apply(self):
        for draft in ("", "8", "80", "80 ", "101", "1.5", "-1", "a"):
            with self.subTest(draft=draft):
                state = assess_wet_draft(draft, 80)
                self.assertFalse(state.can_apply)
        self.assertEqual(assess_wet_draft("8", 80).state, "step_too_large")
        self.assertEqual(assess_wet_draft("80", 80).state, "unchanged")
        self.assertEqual(assess_wet_draft("", 80).state, "empty")
        self.assertEqual(assess_wet_draft("79", None).state, "need_read")

    def test_only_single_unit_edits_are_ready(self):
        for old, new in ((0,1),(1,0),(79,80),(80,79),(80,81),(100,99)):
            with self.subTest(old=old,new=new):
                state = assess_wet_draft(str(new), old)
                self.assertTrue(state.can_apply)
                self.assertEqual(state.target, new)
                self.assertEqual(abs(state.delta), 1)
        for new in (0, 77, 78, 82, 100):
            self.assertFalse(assess_wet_draft(str(new), 80).can_apply)

    def test_plus_minus_buttons_only_prepare_bounded_one_step(self):
        self.assertEqual(stage_wet_step(80, -1), 79)
        self.assertEqual(stage_wet_step(80, 1), 81)
        self.assertEqual(stage_wet_step(0, 1), 1)
        self.assertEqual(stage_wet_step(100, -1), 99)
        for current, direction in (
            (0, -1), (100, 1), (-1, 1), (101, -1),
            (True, 1), (80, 0), (80, 2), (80, True),
        ):
            with self.subTest(current=current, direction=direction):
                with self.assertRaises(ValueError):
                    stage_wet_step(current, direction)
        self.assertEqual(assess_wet_draft(str(stage_wet_step(80, -1)), 80).state,
                         "ready")

    def test_editor_controls_layout_is_above_expanding_table(self):
        source = (
            Path(__file__).resolve().parents[1] /
            "tools" / "chorus_editor_gui.py"
        ).read_text(encoding="utf-8")
        # Contract: old M1H had a notebook expanding before the edit panel,
        # so the Apply button disappeared on small/high-DPI windows.
        self.assertIn('editor.pack(fill="x", pady=(8, 10), before=tablebox)', source)
        self.assertIn('status.pack(anchor="w", pady=(7, 4), before=tablebox)', source)
        self.assertIn('secondary_row, text="APLICAR NA PLACA"', source)
        self.assertIn('editrow, text="−1"', source)
        self.assertIn('editrow, text="+1"', source)
        self.assertIn("stage_wet_step(manual_live[0][6], direction)", source)
        draft_block = source.split("    def stage_clicked(direction: int):", 1)[1].split(
            "    def cancel_clicked():", 1
        )[0]
        for forbidden in ("run_worker_once(", "run_operation(", "HidD_", "subprocess."):
            self.assertNotIn(forbidden, draft_block)

    def test_read_worker_success_needs_real_seven_word_shape(self):
        valid = {"status": "READ_OK", "wet": 80, "fields": list(CHORUS)}
        validate_success_reply("read", valid)
        for field in ("fields", "wet"):
            bad = dict(valid)
            bad[field] = [] if field == "fields" else 81
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_success_reply("read", bad)
        for raw in (None, "80", 101, True):
            bad = {"status":"READ_OK","fields":list(CHORUS)}
            bad["fields"][6] = raw
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_success_reply("read", bad)

    def test_apply_response_requires_ack_exact_target_and_full_parity(self):
        good = {
            "status":"APPLIED_VERIFIED", "initial":list(CHORUS), "target":79,
            "applied_readback":list(CHORUS[:6]) + [79],
            "candidate_ack_valid":True, "errors":[],
        }
        validate_success_reply("apply", good, CHORUS, 79)
        for key, value in (
            ("candidate_ack_valid", False),
            ("errors", ["usb error"]),
            ("target", 78),
            ("initial", list(CHORUS[:6])+[79]),
            ("applied_readback", [1, 20, 10, 201, 50, 80, 79]),
            ("applied_readback", list(CHORUS)),
        ):
            with self.subTest(key=key,value=value):
                bad = dict(good)
                bad[key] = value
                with self.assertRaises(ValueError):
                    validate_success_reply("apply", bad, CHORUS, 79)

    def test_staged_draft_has_no_hid_imports_or_side_effects(self):
        file = Path(__file__).resolve().parents[1] / "src" / "bpcontrol" / "editor_view_model.py"
        source = file.read_text(encoding="utf-8")
        for forbidden in ("HidD_SetOutputReport", "HidD_GetInputReport",
                          "usb_hid", "subprocess.run", "ctypes", "socket"):
            self.assertNotIn(forbidden, source)
        self.assertEqual(assess_wet_draft("79", 80).can_apply, True)


if __name__ == "__main__":
    unittest.main()
