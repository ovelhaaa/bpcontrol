"""M1J Music-only readback, evidence and subprocess safety tests (no hardware)."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from bpcontrol.acp import ACPFrame
from bpcontrol.music_effects import (
    MUSIC_COMMANDS, MUSIC_EFFECTS, MUSIC_EFFECT_INDICES,
    EXCITER_CUTOFF_CONFLICT, decode_music_frame, make_music_rows,
    normalize_music_values, read_music_live, validate_music_worker_reply,
)
from bpcontrol.snapshot import read_catalog
from bpcontrol.usb_hid import HIDTransportError


OBSERVED = {
    23: (1, 35),
    24: (1, 70),
    27: (1, 1),
    29: (1, 2400, 70, 35),
}


def frame_for(effect_index: int, values: tuple[int, ...]) -> ACPFrame:
    command = MUSIC_EFFECTS[MUSIC_EFFECT_INDICES.index(effect_index)].command
    return ACPFrame(
        command, b"\xff" +
        b"".join(v.to_bytes(2, "little", signed=True) for v in values)
    )


class FakeReadOnlySession:
    """A deliberately minimal fake: no SET_REPORT/write method exists."""
    def __init__(self, fail=None):
        self.queries = []
        self.authorized = False
        self.fail = fail

    def query(self, command):
        self.queries.append(command)
        if command == 0x00:
            return ACPFrame(0x00, b"\x30\x00\x03\x00\x02\x18\x00")
        if not self.authorized:
            raise HIDTransportError("firmware first")
        if command == self.fail:
            raise HIDTransportError("synthetic disconnected USB")
        effect = next(e for e in MUSIC_EFFECTS if e.command == command)
        return frame_for(effect.index, OBSERVED[effect.index])

    def authorize_after_firmware(self, frame):
        if frame.command != 0x00:
            raise HIDTransportError("wrong firmware response")
        self.authorized = True


class MusicEffectTests(unittest.TestCase):
    def test_four_exact_firmware_slot_type_and_field_counts(self):
        self.assertEqual(MUSIC_EFFECT_INDICES, (23, 24, 27, 29))
        self.assertEqual(MUSIC_COMMANDS, (0x97, 0x98, 0x9B, 0x9D))
        self.assertEqual(
            [(e.type_id, e.word_count) for e in MUSIC_EFFECTS],
            [(12, 2), (30, 2), (28, 2), (25, 4)]
        )
        self.assertTrue(all(not hasattr(p, "writable")
                            for e in MUSIC_EFFECTS for p in e.parameters))

    def test_widener_shaping_is_boolean_not_a_width_knob(self):
        widener = MUSIC_EFFECTS[2]
        self.assertEqual([p.key for p in widener.parameters],
                         ["enable", "shaping"])
        self.assertIn("0 = off; 1 = on", widener.parameters[1].nominal_range)

    def test_exciter_cutoff_document_conflict_kept_visible(self):
        exciter = MUSIC_EFFECTS[3]
        self.assertEqual(exciter.parameters[1].key, "cutoff_frequency")
        self.assertIn("300–10000", exciter.parameters[1].nominal_range)
        self.assertIn("1000–10000", exciter.parameters[1].nominal_range)
        self.assertIn("BP1032", EXCITER_CUTOFF_CONFLICT)

    def test_exact_acp_frame_parsing(self):
        for effect in MUSIC_EFFECTS:
            with self.subTest(effect=effect.name):
                values = OBSERVED[effect.index]
                self.assertEqual(decode_music_frame(
                    frame_for(effect.index, values), effect.index
                ), values)
                with self.assertRaises(HIDTransportError):
                    decode_music_frame(
                        ACPFrame(effect.command, b"\xff\x01\x00"), effect.index
                    )
                with self.assertRaises(HIDTransportError):
                    decode_music_frame(
                        ACPFrame(effect.command, b"\x00" +
                                 b"\x00\x00" * effect.word_count),
                        effect.index,
                    )
                with self.assertRaises(HIDTransportError):
                    decode_music_frame(
                        ACPFrame(0x8F, frame_for(effect.index, values).payload),
                        effect.index,
                    )
        with self.assertRaises(ValueError):
            decode_music_frame(frame_for(23, OBSERVED[23]), 15)

    def test_strict_read_order_and_exact_allowlist(self):
        fake = FakeReadOnlySession()
        self.assertEqual(read_music_live(fake), OBSERVED)
        self.assertEqual(fake.queries, [0, 0x97, 0x98, 0x9B, 0x9D])

    def test_failed_mid_read_never_retries(self):
        fake = FakeReadOnlySession(fail=0x9B)
        with self.assertRaises(HIDTransportError):
            read_music_live(fake)
        self.assertEqual(fake.queries, [0, 0x97, 0x98, 0x9B])

    def test_omitted_malformed_or_extra_worker_readback_is_refused(self):
        good = {"status": "MUSIC_READ_OK",
                "effects": {str(k): list(v) for k, v in OBSERVED.items()}}
        self.assertEqual(validate_music_worker_reply(good), OBSERVED)
        bad_cases = [
            {"status": "MUSIC_READ_ERROR", "effects": good["effects"]},
            {"status": "MUSIC_READ_OK", "effects": {"23": [1, 35]}},
            {"status": "MUSIC_READ_OK", "effects": {**good["effects"], "15": [80]}},
            {"status": "MUSIC_READ_OK", "effects": {**good["effects"], "23": [1, True]}},
            {"status": "MUSIC_READ_OK", "effects": {**good["effects"], "27": [1, 1, 2]}},
            {"status": "MUSIC_READ_OK", "effects": {**good["effects"], "23": [-32769, 50]}},
        ]
        for i, case in enumerate(bad_cases):
            with self.subTest(case=i), self.assertRaises(ValueError):
                validate_music_worker_reply(case)

    def test_saved_snapshot_is_not_confused_with_real_usb(self):
        catalog = read_catalog()
        snapshot = [dict(row, fields=[]) for row in catalog["effects"]]
        rows = make_music_rows(snapshot)
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(row["origin"] == "Sem leitura" for row in rows))
        self.assertTrue(all(not row["writable"] for row in rows))

        snapshot[22]["fields"] = [
            {"index": 0, "signed": 0}, {"index": 1, "signed": 75}
        ]
        local = make_music_rows(snapshot)
        self.assertEqual(local[1]["value"], 75)
        self.assertEqual(local[1]["origin"], "Snapshot salvo")
        real = make_music_rows(snapshot, OBSERVED)
        self.assertEqual(real[1]["value"], 35)
        self.assertEqual(real[1]["snapshot"], 75)
        self.assertEqual(real[1]["origin"], "USB atual")
        self.assertTrue(all(not row["writable"] for row in real))
        snapshot[22]["type_id"] = 99
        with self.assertRaises(ValueError):
            make_music_rows(snapshot, OBSERVED)

    def test_schema_is_data_only_no_permission_escalation(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "src" / "bpcontrol" / "music_effects.py").read_text()
        worker = (root / "tools" / "music_read_worker.py").read_text()
        for forbidden in ("encode_write", "send_candidate_once",
                          "send_restoration_once", "HidD_SetOutputReport",
                          "0xFD", "0xFE"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("encode_write", worker)
        self.assertNotIn("HidD_SetOutputReport", worker)
        self.assertIn("session.query(effect.command)", source)
        self.assertIn("WindowsSnapshotSession", worker)


if __name__ == "__main__":
    unittest.main()
