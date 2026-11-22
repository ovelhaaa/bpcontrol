"""Offline regression tests for the M1J Music FX inspector CLI and UI worker."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from tools.music_inspector_gui import (
    load_snapshot, run_music_worker_once, TIMEOUT_S, MUSIC_WORKER,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = {
    "status": "MUSIC_READ_OK",
    "effects": {
        "23": [1, 35],
        "24": [1, 70],
        "27": [1, 1],
        "29": [1, 2400, 70, 35],
    },
}


class MusicInspectorGuiTests(unittest.TestCase):
    def test_offline_demo_is_structurally_valid(self):
        demo = load_snapshot(ROOT / "data" / "demo_snapshot.json")
        self.assertEqual(len(demo["effects"]), 59)

    def test_bounded_child_reads_only_four_allowed_slots(self):
        child = subprocess.CompletedProcess(
            [], 0, json.dumps(EXAMPLE), ""
        )
        with mock.patch("tools.music_inspector_gui.subprocess.run",
                        return_value=child) as runner:
            observed = run_music_worker_once(python="safe-python")
        self.assertEqual(observed["status"], "MUSIC_READ_OK")
        command = runner.call_args.args[0]
        self.assertEqual(command, ["safe-python", str(MUSIC_WORKER),
                                   "--read-four-music-effects"])
        self.assertEqual(runner.call_args.kwargs["timeout"], TIMEOUT_S)
        self.assertNotIn("--apply", command)
        self.assertNotIn("--enable-live-writes", command)

    def test_read_timeout_does_not_retry(self):
        with mock.patch("tools.music_inspector_gui.subprocess.run",
                        side_effect=subprocess.TimeoutExpired(["worker"], 15)) as runner:
            result = run_music_worker_once()
        self.assertEqual(result["status"], "MUSIC_READ_ERROR")
        self.assertEqual(runner.call_count, 1)

    def test_nonzero_worker_exit_blocks_success_shaped_json(self):
        child = subprocess.CompletedProcess(
            [], 4, json.dumps(EXAMPLE), "fake HID error"
        )
        with mock.patch("tools.music_inspector_gui.subprocess.run",
                        return_value=child):
            result = run_music_worker_once()
        self.assertEqual(result["status"], "MUSIC_READ_ERROR")

    def test_malformed_or_incomplete_reply_never_claims_success(self):
        for payload in (
            "",
            "not-json",
            json.dumps({"status": "MUSIC_READ_OK", "effects": {"23": [1, 80]}}),
            json.dumps({"status": "MUSIC_READ_OK",
                        "effects": {**EXAMPLE["effects"], "29": [1, 2400, 80]}}),
        ):
            with self.subTest(payload=payload), mock.patch(
                "tools.music_inspector_gui.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, payload, ""),
            ):
                result = run_music_worker_once()
            self.assertEqual(result["status"], "MUSIC_READ_ERROR")

    def test_music_gui_never_calls_hardware_on_launch_or_selection(self):
        src = (ROOT / "tools" / "music_inspector_gui.py").read_text()
        self.assertIn("if not enable_live:", src)
        self.assertIn('read_btn.configure(', src)
        self.assertIn("app.after(100, poll)", src)
        self.assertIn('def read_music():', src)
        self.assertIn('def refresh_effect(index: int)', src)
        block = src.split("    def refresh_effect(index: int) -> None:", 1)[1]
        block = block.split("    def on_tree_select", 1)[0]
        for forbidden in ("run_music_worker_once(", "subprocess.run(", "HidD_"):
            self.assertNotIn(forbidden, block)
        for forbidden in ("encode_write", "send_candidate_once", "0xFD", "0xFE"):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
