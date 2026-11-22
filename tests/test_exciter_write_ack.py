"""Tests for passive M1K-A Exciter (0x9D) HID ACK & readback analysis.

All captures are synthetic; no hardware, no USB, no writes.
"""
from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest

from bpcontrol.acp import ACPFrame
from tools.analyze_exciter_write_ack import (
    ack_shape,
    classify_invalid_exciter_out,
    decode_exciter_write,
    inspect,
    select_board,
)
from tools.analyze_usb_capture import USB, analyze, packets


def hid_transfer(
    records: list,
    frame: bytes,
    response: bytes,
    irp_base: int,
    *,
    pad_out: bool = True,
    pad_in: bool = True,
) -> None:
    out = frame + bytes(256 - len(frame)) if pad_out else frame
    inp = response + bytes(256 - len(response)) if pad_in else response
    out_setup = struct.pack("<BBHHH", 0x21, 9, 0x0200, 4, 256)
    in_setup = struct.pack("<BBHHH", 0xA1, 1, 0x0100, 4, 256)
    records.extend([
        (0, False, 0, irp_base, out_setup + out),
        (0, True, 3, irp_base, b""),
        (0x80, False, 0, irp_base + 1, in_setup),
        (0x80, True, 3, irp_base + 1, inp),
    ])


def exciter_readback(enable: int, cutoff: int, dry: int, wet: int) -> bytes:
    words = (enable, cutoff, dry, wet)
    return ACPFrame(
        0x9D,
        b"\xFF" + b"".join(x.to_bytes(2, "little", signed=True) for x in words),
    ).to_bytes()


def exciter_write_frame(field_index: int, value: int) -> bytes:
    return ACPFrame(
        0x9D,
        bytes([field_index]) + value.to_bytes(2, "little", signed=True),
    ).to_bytes()


def write_pcap(path: Path, recs: list[tuple[int, bool, int, int, bytes]]) -> None:
    with path.open("wb") as stream:
        stream.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 249))
        for n, (ep, done, stage, irp, data) in enumerate(recs):
            urb = (
                USB.pack(
                    28, irp, 0, 8 if done else 27, int(done),
                    2, 1, ep, 2, len(data),
                )
                + bytes([stage])
                + data
            )
            stream.write(struct.pack("<IIII", 1234567890, n * 1000, len(urb), len(urb)))
            stream.write(urb)


class ExciterWriteAckTests(unittest.TestCase):
    def test_isolated_cutoff_dry_wet_changes_and_full_restoration(self):
        recs: list = []
        read_cmd = ACPFrame(0x9D, b"").to_bytes()
        # Baseline: enable=1, cutoff=1500, dry=80, wet=50
        hid_transfer(recs, read_cmd, exciter_readback(1, 1500, 80, 50), 1)
        # Cutoff: 1500 -> 2000 -> 1500
        hid_transfer(recs, exciter_write_frame(1, 2000), b"\x9d", 3)
        hid_transfer(recs, read_cmd, exciter_readback(1, 2000, 80, 50), 5)
        hid_transfer(recs, exciter_write_frame(1, 1500), b"\x9d", 7)
        hid_transfer(recs, read_cmd, exciter_readback(1, 1500, 80, 50), 9)
        # Dry: 80 -> 75 -> 80
        hid_transfer(recs, exciter_write_frame(2, 75), b"\x9d", 11)
        hid_transfer(recs, read_cmd, exciter_readback(1, 1500, 75, 50), 13)
        hid_transfer(recs, exciter_write_frame(2, 80), b"\x9d", 15)
        hid_transfer(recs, read_cmd, exciter_readback(1, 1500, 80, 50), 17)
        # Wet: 50 -> 55 -> 50
        hid_transfer(recs, exciter_write_frame(3, 55), b"\x9d", 19)
        hid_transfer(recs, read_cmd, exciter_readback(1, 1500, 80, 55), 21)
        hid_transfer(recs, exciter_write_frame(3, 50), b"\x9d", 23)
        hid_transfer(recs, read_cmd, exciter_readback(1, 1500, 80, 50), 25)

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "exciter_ok.pcap"
            write_pcap(path, recs)
            records = list(packets(path))
            self.assertEqual(select_board(records, None, None), (2, 1))
            result = inspect(analyze(path, 2, 1))

        self.assertEqual(result["write_count"], 6)
        self.assertEqual(result["recognized_bare_ack_count"], 6)
        self.assertEqual(result["duplicate_write_count"], 0)
        self.assertEqual(result["unpaired_set_report_packets"], [])
        self.assertEqual(result["invalid_packets"], [])
        self.assertEqual(result["out_of_order_packets"], [])
        self.assertEqual(
            result["baseline_from_prewrite_readback"],
            {"enable": 1, "cutoff": 1500, "dry": 80, "wet": 50},
        )
        self.assertTrue(result["final_writes_match_prewrite_baseline"])
        self.assertTrue(result["post_restore_readback_confirmed"])
        self.assertEqual(result["restoration_status"], "confirmed")
        self.assertTrue(all(w["readback_matches_written_value"] for w in result["writes"]))
        self.assertTrue(result["per_field"]["cutoff"]["post_restore_readback_confirmed"])
        self.assertTrue(result["per_field"]["dry"]["post_restore_readback_confirmed"])
        self.assertTrue(result["per_field"]["wet"]["post_restore_readback_confirmed"])

    def test_missing_ack_is_flagged_unpaired(self):
        recs: list = []
        read_cmd = ACPFrame(0x9D, b"").to_bytes()
        hid_transfer(recs, read_cmd, exciter_readback(1, 1000, 80, 40), 1)
        # SET_REPORT submit/complete without GET_REPORT ACK
        out_setup = struct.pack("<BBHHH", 0x21, 9, 0x0200, 4, 256)
        out = exciter_write_frame(1, 1200)
        out_padded = out + bytes(256 - len(out))
        recs.extend([
            (0, False, 0, 3, out_setup + out_padded),
            (0, True, 3, 3, b""),
        ])

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "missing_ack.pcap"
            write_pcap(path, recs)
            result = inspect(analyze(path, 2, 1))

        self.assertEqual(result["write_count"], 1)
        self.assertEqual(result["recognized_bare_ack_count"], 0)
        self.assertEqual(len(result["unpaired_set_report_packets"]), 1)
        self.assertEqual(result["writes"][0]["ack_classification"], "no_matching_ack")
        self.assertFalse(result["post_restore_readback_confirmed"])

    def test_invalid_packets_are_rejected_and_reported(self):
        recs: list = []
        read_cmd = ACPFrame(0x9D, b"").to_bytes()
        hid_transfer(recs, read_cmd, exciter_readback(1, 1000, 80, 40), 1)
        # 1. Unsupported field index 4
        bad_field = ACPFrame(0x9D, b"\x04\x01\x00").to_bytes()
        hid_transfer(recs, bad_field, b"\x9d", 3)
        # 2. Bad ACP footer (0x17 instead of 0x16)
        bad_footer = bytearray(exciter_write_frame(2, 70))
        bad_footer[-1] = 0x17
        hid_transfer(recs, bytes(bad_footer), b"\x9d", 5)
        # 3. Nonzero HID padding
        nonzero_pad = exciter_write_frame(3, 50) + b"\x01" + bytes(256 - 9)
        hid_transfer(recs, nonzero_pad, b"\x9d", 7, pad_out=False)
        # 4. Valid write so select_board finds the device
        hid_transfer(recs, exciter_write_frame(3, 40), b"\x9d", 9)

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "invalid.pcap"
            write_pcap(path, recs)
            records = list(packets(path))
            reasons = [classify_invalid_exciter_out(p) for p in records]
            self.assertIn("unsupported_field_index_4", reasons)
            self.assertIn("invalid_acp_footer", reasons)
            self.assertIn("nonzero_hid_padding", reasons)
            self.assertEqual(sum(decode_exciter_write(p) is not None for p in records), 1)
            result = inspect(analyze(path, 2, 1))

        self.assertEqual(result["write_count"], 1)
        self.assertEqual(
            [item["reason"] for item in result["invalid_packets"]],
            ["unsupported_field_index_4", "invalid_acp_footer", "nonzero_hid_padding"],
        )

    def test_out_of_order_responses_are_not_falsely_paired(self):
        recs: list = []
        out_setup = struct.pack("<BBHHH", 0x21, 9, 0x0200, 4, 256)
        in_setup = struct.pack("<BBHHH", 0xA1, 1, 0x0100, 4, 256)
        out = exciter_write_frame(2, 90)
        out_padded = out + bytes(256 - len(out))
        ack_padded = b"\x9d" + bytes(255)
        # Interleaved: SET submit (irp 1), GET submit (irp 2), SET complete (irp 1), GET complete (irp 2)
        recs.extend([
            (0, False, 0, 1, out_setup + out_padded),
            (0x80, False, 0, 2, in_setup),
            (0, True, 3, 1, b""),
            (0x80, True, 3, 2, ack_padded),
        ])

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out_of_order.pcap"
            write_pcap(path, recs)
            result = inspect(analyze(path, 2, 1))

        self.assertEqual(result["write_count"], 1)
        self.assertEqual(result["recognized_bare_ack_count"], 0)
        self.assertEqual(result["out_of_order_packets"], [1])
        self.assertEqual(result["writes"][0]["ack_classification"], "out_of_order_or_interleaved")

    def test_duplicate_writes_are_flagged(self):
        recs: list = []
        read_cmd = ACPFrame(0x9D, b"").to_bytes()
        hid_transfer(recs, read_cmd, exciter_readback(1, 1000, 80, 50), 1)
        hid_transfer(recs, exciter_write_frame(1, 1500), b"\x9d", 3)
        hid_transfer(recs, exciter_write_frame(1, 1500), b"\x9d", 5)
        hid_transfer(recs, exciter_write_frame(1, 1000), b"\x9d", 7)
        hid_transfer(recs, read_cmd, exciter_readback(1, 1000, 80, 50), 9)

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "duplicates.pcap"
            write_pcap(path, recs)
            result = inspect(analyze(path, 2, 1))

        self.assertEqual(result["write_count"], 3)
        self.assertEqual(result["duplicate_write_count"], 1)
        self.assertFalse(result["writes"][0]["is_duplicate"])
        self.assertTrue(result["writes"][1]["is_duplicate"])
        self.assertFalse(result["writes"][2]["is_duplicate"])
        self.assertEqual(result["per_field"]["cutoff"]["duplicate_write_count"], 1)

    def test_unconfirmed_restoration_scenarios(self):
        read_cmd = ACPFrame(0x9D, b"").to_bytes()

        # Case A: missing pre-write baseline
        recs_no_base: list = []
        hid_transfer(recs_no_base, exciter_write_frame(3, 60), b"\x9d", 1)
        hid_transfer(recs_no_base, exciter_write_frame(3, 50), b"\x9d", 3)
        hid_transfer(recs_no_base, read_cmd, exciter_readback(1, 1000, 80, 50), 5)

        # Case B: missing trailing post-restore readback
        recs_no_trail: list = []
        hid_transfer(recs_no_trail, read_cmd, exciter_readback(1, 1000, 80, 50), 1)
        hid_transfer(recs_no_trail, exciter_write_frame(3, 60), b"\x9d", 3)
        hid_transfer(recs_no_trail, exciter_write_frame(3, 50), b"\x9d", 5)

        # Case C: trailing readback does not match baseline
        recs_mismatch: list = []
        hid_transfer(recs_mismatch, read_cmd, exciter_readback(1, 1000, 80, 50), 1)
        hid_transfer(recs_mismatch, exciter_write_frame(3, 60), b"\x9d", 3)
        hid_transfer(recs_mismatch, exciter_write_frame(3, 50), b"\x9d", 5)
        hid_transfer(recs_mismatch, read_cmd, exciter_readback(1, 1000, 80, 51), 7)

        with tempfile.TemporaryDirectory() as d:
            for name, recs, expected_status in (
                ("no_base.pcap", recs_no_base, "missing_prewrite_baseline"),
                ("no_trail.pcap", recs_no_trail, "missing_post_restore_readback"),
                ("mismatch.pcap", recs_mismatch, "readback_mismatch"),
            ):
                p = Path(d) / name
                write_pcap(p, recs)
                res = inspect(analyze(p, 2, 1))
                self.assertFalse(res["post_restore_readback_confirmed"])
                self.assertEqual(res["restoration_status"], expected_status)

    def test_ack_shape_variants(self):
        self.assertEqual(ack_shape(b"\x9d" + bytes(255)), "bare_9d_zero_padded")
        self.assertEqual(ack_shape(b"\x9d\x01" + bytes(254)), "unknown")
        self.assertEqual(ack_shape(b"\x9d"), "nonstandard_report_length")


if __name__ == "__main__":
    unittest.main()
