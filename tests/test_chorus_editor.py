"""M1G offline editor tests — simulated HID only, no device writes."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from bpcontrol.acp import ACPFrame
from bpcontrol.chorus_editor import (
    ChorusEditorSession, apply_one_editor_step, parse_wet_draft,
    read_editor_chorus, validate_editor_target,
)
from bpcontrol.usb_hid import HIDTransportError
from tools.chorus_editor_gui import (
    run_worker_once, validate_snapshot_for_viewing, WORKER_TIMEOUT_SECONDS,
)


BASE = (1, 20, 10, 200, 50, 80, 80)
ROOT = Path(__file__).resolve().parents[1]


class FakeEditorSession(ChorusEditorSession):
    def __init__(self, initial=BASE, *, bad_ack=False, fail_restore=False,
                 drift=False, modify_other=False):
        super().__init__()
        self._handle = 9001  # artificial, never calls __enter__ / actual USB
        self.values = list(initial)
        self.writes = []
        self.read_calls = 0
        self.bad_ack = bad_ack
        self.fail_restore = fail_restore
        self.drift = drift
        self.modify_other = modify_other

    def query(self, command):
        if command == 0:
            return ACPFrame(0, bytes.fromhex("30 00 03 00 02 18 00"))
        if command != 0x8F:
            raise HIDTransportError("fake only supports Chorus + firmware")
        self.read_calls += 1
        if self.drift and self.read_calls == 2:
            self.values[3] += 1
        payload = b"\xff" + b"".join(
            value.to_bytes(2, "little", signed=True)
            for value in self.values
        )
        return ACPFrame(0x8F, payload)

    def _exchange_write(self, value: int):
        self.writes.append(value)
        if self._phase == 1:
            self.values[6] = value
            if self.modify_other:
                self.values[3] += 1
            if self.bad_ack:
                raise HIDTransportError("synthetic missing candidate ACK")
        elif self._phase == 2:
            if self.fail_restore:
                raise HIDTransportError("synthetic lost restoration")
            self.values[6] = value
            if self.modify_other:
                self.values[3] -= 1
        else:
            raise AssertionError("write in unexpected phase")


class M1GEditorTests(unittest.TestCase):
    def test_text_input_is_pure_and_requires_complete_decimal(self):
        for draft, answer in (("0", 0), ("8", 8), ("80", 80),
                              ("081", 81), ("100", 100)):
            self.assertEqual(parse_wet_draft(draft), answer)
        for draft in ("", " ", "80 ", "-1", "1.0", "+1", "1000",
                      "101", "abc", "\u0665", None, 81):
            with self.subTest(draft=draft), self.assertRaises(ValueError):
                parse_wet_draft(draft)

    def test_one_step_only_and_full_snapshot_required(self):
        validate_editor_target(BASE, 79)
        validate_editor_target(BASE, 81)
        for target in (78, 82, 8, 80, 1000, True):
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_editor_target(BASE, target)
        with self.assertRaises(ValueError):
            validate_editor_target(BASE[:6], 79)
        with self.assertRaises(ValueError):
            validate_editor_target(tuple(BASE[:5])+(50, 101), 100)

    def test_manual_read_does_not_write(self):
        fake = FakeEditorSession()
        self.assertEqual(read_editor_chorus(fake), BASE)
        self.assertEqual(fake.writes, [])
        self.assertEqual(fake.read_calls, 1)

    def test_apply_upward_and_explicit_separate_undo(self):
        fake = FakeEditorSession()
        r = apply_one_editor_step(fake, BASE, 81)
        self.assertEqual(r.status, "APPLIED_VERIFIED")
        self.assertEqual(r.applied_readback[-1], 81)
        self.assertEqual(r.initial, BASE)
        self.assertFalse(r.restoration_verified)
        self.assertIsNone(r.restoration_readback)
        self.assertEqual(fake.writes, [81])
        self.assertEqual(fake.read_calls, 3)  # twice preflight, once after write
        self.assertEqual(fake.values[-1], 81)
        # Undo is a distinct, explicitly authorized click/new HID session.
        undo_session = FakeEditorSession(tuple(fake.values))
        previous = tuple(fake.values)
        undo = apply_one_editor_step(undo_session, previous, 80)
        self.assertEqual(undo.status, "APPLIED_VERIFIED")
        self.assertEqual(undo_session.writes, [80])
        self.assertEqual(undo.applied_readback, BASE)

    def test_decrease_and_no_unwanted_restore_after_success(self):
        fake = FakeEditorSession()
        result = apply_one_editor_step(fake, BASE, 79)
        self.assertEqual(result.status, "APPLIED_VERIFIED")
        self.assertEqual(fake.writes, [79])
        self.assertEqual(fake.values[6], 79)

    def test_full_state_mismatch_refuses_without_write(self):
        fake = FakeEditorSession()
        mismatched = tuple([0] + list(BASE[1:]))
        with self.assertRaisesRegex(HIDTransportError, "NO WRITE"):
            apply_one_editor_step(fake, mismatched, 81)
        self.assertEqual(fake.writes, [])

    def test_preflight_drift_refuses_before_write(self):
        fake = FakeEditorSession(drift=True)
        with self.assertRaisesRegex(HIDTransportError, "NO WRITE"):
            apply_one_editor_step(fake, BASE, 79)
        self.assertEqual(fake.writes, [])

    def test_missing_ack_must_restore_once(self):
        fake = FakeEditorSession(bad_ack=True)
        result = apply_one_editor_step(fake, BASE, 79)
        self.assertEqual(result.status, "ERROR_BUT_RESTORED")
        self.assertEqual(fake.writes, [79, 80])
        self.assertFalse(result.candidate_ack_valid)
        self.assertTrue(result.restoration_verified)
        self.assertEqual(result.restoration_readback, BASE)

    def test_failed_restoration_is_uncertain(self):
        fake = FakeEditorSession(bad_ack=True, fail_restore=True)
        result = apply_one_editor_step(fake, BASE, 79)
        self.assertEqual(result.status, "STATE_UNCERTAIN")
        self.assertEqual(fake.writes, [79, 80])
        self.assertFalse(result.restoration_verified)
        self.assertEqual(fake.values[-1], 79)

    def test_wrong_field_change_triggers_recovery(self):
        fake = FakeEditorSession(modify_other=True)
        result = apply_one_editor_step(fake, BASE, 79)
        self.assertEqual(result.status, "ERROR_BUT_RESTORED")
        self.assertTrue(result.restoration_verified)
        self.assertEqual(fake.writes, [79, 80])
        self.assertTrue(any("mismatch" in e for e in result.errors))

    def test_read_only_snapshot_does_not_authorize_write(self):
        demo = json.loads((ROOT/"data"/"demo_snapshot.json").read_text())
        validate_snapshot_for_viewing(demo)
        self.assertEqual(demo["effect_count_read"], 1)

    def test_subprocess_worker_argv_strict_and_bounded(self):
        fake_result = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({
                "status": "APPLIED_VERIFIED",
                "initial": list(BASE),
                "applied_readback": list(BASE[:6]) + [79],
            }), stderr=""
        )
        with mock.patch("tools.chorus_editor_gui.subprocess.run",
                        return_value=fake_result) as run:
            r = run_worker_once("apply", BASE, 79, python="fake-python")
        self.assertEqual(r["status"], "APPLIED_VERIFIED")
        argv = run.call_args.args[0]
        self.assertEqual(argv[0], "fake-python")
        self.assertEqual(argv[-1], "--authorize-one-apply")
        self.assertIn("--expected-fields", argv)
        self.assertEqual(run.call_args.kwargs["timeout"], WORKER_TIMEOUT_SECONDS)
        with mock.patch("tools.chorus_editor_gui.subprocess.run") as forbidden:
            with self.assertRaises(ValueError):
                run_worker_once("apply", BASE, 8)
            forbidden.assert_not_called()

    def test_worker_timeout_never_retries_and_fails_closed(self):
        with mock.patch("tools.chorus_editor_gui.subprocess.run",
                        side_effect=subprocess.TimeoutExpired(["x"], 15)) as run:
            result = run_worker_once("apply", BASE, 79)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result["status"], "STATE_UNCERTAIN")

    def test_bad_worker_output_fails_closed(self):
        with mock.patch("tools.chorus_editor_gui.subprocess.run",
                        return_value=subprocess.CompletedProcess(
                            [], 4, "not JSON", "bad"
                        )):
            result = run_worker_once("apply", BASE, 79)
        self.assertEqual(result["status"], "STATE_UNCERTAIN")

    def test_read_worker_is_never_given_write_flags(self):
        output = subprocess.CompletedProcess([], 0,
                                             json.dumps({"status":"READ_OK",
                                                         "fields":list(BASE)}), "")
        with mock.patch("tools.chorus_editor_gui.subprocess.run",
                        return_value=output) as run:
            result = run_worker_once("read")
        self.assertEqual(result["status"], "READ_OK")
        argv = run.call_args.args[0]
        self.assertIn("--read", argv)
        self.assertNotIn("--authorize-one-apply", argv)


if __name__ == "__main__":
    unittest.main()
