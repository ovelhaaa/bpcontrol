"""Offline tests for the 45 ACP V2.40.0 read-only protocol effect schemas."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from bpcontrol.acp import encode_read
from bpcontrol.cli import main as cli_main
from bpcontrol.editor_view_model import present_effect_fields
from bpcontrol.protocol_effects import (
    PROTOCOL_EFFECTS,
    PROTOCOL_EFFECTS_BY_NAME,
    decode_protocol_effect,
    decode_snapshot_instance,
    format_param_value,
)
from tools.render_snapshot import enrich_snapshot_for_display

ROOT = Path(__file__).resolve().parents[1]


class TestProtocolEffects(unittest.TestCase):
    def test_all_45_protocol_types_present_and_read_only(self):
        self.assertEqual(sorted(PROTOCOL_EFFECTS.keys()), list(range(45)))
        self.assertEqual(len(PROTOCOL_EFFECTS_BY_NAME), 45)
        for tid, effect in PROTOCOL_EFFECTS.items():
            self.assertEqual(effect.type_id, tid)
            self.assertGreaterEqual(effect.word_count, 1)
            self.assertEqual([p.index for p in effect.params], list(range(effect.word_count)))
            for param in effect.params:
                self.assertFalse(param.writable, f"{effect.type_name}.{param.name} must be read-only")

    def test_expected_word_counts(self):
        expected = {
            0: 4,    # Auto Tune
            1: 1,    # DC Blocker
            2: 27,   # DRC V4.0.0+
            3: 9,    # Echo
            4: 53,   # EQ
            5: 5,    # Noise Suppressor Expander
            6: 2,    # Frequency Shifter
            7: 2,    # Howling Control
            8: 6,    # Noise Gate
            9: 2,    # Pitch Shifter
            10: 7,   # Reverb
            11: 2,   # Silence Detector
            12: 2,   # MV3D
            13: 4,   # MVBass
            14: 3,   # Voice Changer
            15: 3,   # Gain Control
            16: 2,   # Vocal Cut
            17: 8,   # Reverb Plate
            18: 17,  # Reverb Pro
            19: 3,   # Voice Changer Pro
            20: 2,   # Phase Control
            21: 3,   # Vocal Remover
            22: 2,   # Pitch Shifter Pro
            23: 3,   # MVBass Classic
            24: 4,   # PCM Delay
            25: 4,   # Harmonic Exciter
            26: 7,   # Chorus
            27: 7,   # Auto Wah
            28: 2,   # Stereo Widener
            29: 6,   # Ping Pong
            30: 2,   # MV3D Plus
            31: 6,   # Sine Generator
            32: 2,   # Noise Suppressor Blue
            33: 7,   # Flanger
            34: 2,   # Frequency Shifter Fine
            35: 2,   # Overdrive
            36: 4,   # Distortion
            37: 79,  # EQ_DRC
            38: 3,   # AEC
            39: 3,   # Distortion DS1
            40: 3,   # Overdrive Poly
            41: 7,   # Compander
            42: 5,   # Low Level Compressor
            43: 3,   # Howling Suppressor Fine
            44: 8,   # Biquad
        }
        for tid, count in expected.items():
            self.assertEqual(PROTOCOL_EFFECTS[tid].word_count, count, f"type_id={tid}")

    def test_all_59_catalog_instances_match_protocol_word_counts(self):
        catalog = json.loads((ROOT / "data" / "effect_instances.json").read_text(encoding="utf-8"))
        for entry in catalog["effects"]:
            tid = entry["type_id"]
            self.assertIn(tid, PROTOCOL_EFFECTS)
            self.assertEqual(
                len(entry["parameter_hints"]),
                PROTOCOL_EFFECTS[tid].word_count,
                f"instance {entry['index']} ({entry['name']}) hint count mismatch",
            )

    def test_formatting_and_decoding(self):
        auto_tune = decode_protocol_effect(0, [1, ord("C"), ord("n"), 2])
        self.assertEqual(auto_tune[0]["formatted"], "1 (on)")
        self.assertEqual(auto_tune[1]["formatted"], "'C' (C major)")
        self.assertEqual(auto_tune[2]["formatted"], "'n' (near snap)")
        self.assertEqual(auto_tune[3]["formatted"], "2 (best accuracy)")

        compander = decode_protocol_effect(41, [0, -4000, 100, 250, 5, 100, -1200])
        self.assertEqual(compander[1]["formatted"], "-40.00 dB")
        self.assertEqual(compander[2]["formatted"], "1.00")
        self.assertEqual(compander[3]["formatted"], "2.50")
        self.assertEqual(compander[6]["formatted"], "-12.00 dB")

        gain_ctrl = decode_protocol_effect(15, [1, 0, 4096])
        self.assertEqual(gain_ctrl[2]["formatted"], "4096 (0.00 dB)")

        eq_words = [0, 256, 0] + [1, 0, 1000, 724, -512] * 10
        eq_dec = decode_protocol_effect(4, eq_words)
        self.assertEqual(eq_dec[1]["formatted"], "1.00 dB")
        self.assertEqual(eq_dec[2]["formatted"], "0 (fixed-point)")
        self.assertEqual(eq_dec[4]["formatted"], "0 (PEAKING)")
        self.assertEqual(eq_dec[6]["formatted"], "0.707")
        self.assertEqual(eq_dec[7]["formatted"], "-2.00 dB")

        biquad = decode_protocol_effect(44, [1, 0, 0x0100, 0, 6, 60, 1024, 0])
        self.assertEqual(biquad[2]["formatted"], "0x0100 (hi=1, lo=0)")
        self.assertEqual(biquad[4]["formatted"], "6 (NOTCH)")

        self.assertEqual(format_param_value(PROTOCOL_EFFECTS[3].get_param("attenuation"), 0), "0 (-inf dB)")

    def test_decode_errors(self):
        with self.assertRaises(KeyError):
            decode_protocol_effect(99, [0])
        with self.assertRaises(ValueError):
            decode_protocol_effect(0, [0, 0])
        with self.assertRaises(KeyError):
            decode_snapshot_instance({"type_id": 99, "fields": []})

    def test_cli_protocol_list_and_decode(self):
        self.assertEqual(cli_main(["protocol-list"]), 0)
        # Auto Tune: FF 01 00 43 00 6E 00 02 00
        pkt = "A5 5A 87 09 FF 01 00 43 00 6E 00 02 00 16"
        self.assertEqual(cli_main(["protocol-decode", "0", pkt]), 0)
        # Ensure write CLI still rejects unmapped/read-only things cleanly
        _ = encode_read(1)

    def test_editor_view_model_and_html_enrichment(self):
        auto_tune_record = {
            "index": 7,
            "type_id": 0,
            "fields": [
                {"index": 0, "signed": 1, "unsigned": 1, "name": "field_00", "unit": "raw", "mapping": "unknown"},
                {"index": 1, "signed": 67, "unsigned": 67, "name": "field_01", "unit": "raw", "mapping": "unknown"},
                {"index": 2, "signed": 110, "unsigned": 110, "name": "field_02", "unit": "raw", "mapping": "unknown"},
                {"index": 3, "signed": 2, "unsigned": 2, "name": "field_03", "unit": "raw", "mapping": "unknown"},
            ],
        }
        rows = present_effect_fields(auto_tune_record)
        self.assertEqual([r["name"] for r in rows], ["enable", "key", "snap", "pitch_accuracy"])
        self.assertEqual(rows[1]["value_display"], "'C' (C major)")
        self.assertEqual(rows[0]["evidence"], "Protocolo V2.40 · leitura")

        enriched = enrich_snapshot_for_display({"effects": [auto_tune_record]})
        self.assertEqual(enriched["effects"][0]["fields"][1]["protocol_name"], "key")
        self.assertEqual(enriched["effects"][0]["fields"][1]["protocol_formatted"], "'C' (C major)")
        # Original dict must not be mutated
        self.assertNotIn("protocol_name", auto_tune_record["fields"][1])


if __name__ == "__main__":
    unittest.main()
