"""Tests for passive M1E HID ACK analysis. No hardware, no writes."""
from __future__ import annotations

import struct
import tempfile
from pathlib import Path
import unittest

from bpcontrol.acp import ACPFrame
from tools.analyze_chorus_write_ack import (
    ack_shape, decode_wet_write, inspect, select_board,
)
from tools.analyze_usb_capture import USB, analyze, packets


def hid_transfer(records: list, frame: bytes, response: bytes, irp_base: int,
                 *, command_type="write"):
    assert len(frame) <= 256 and len(response) <= 256
    out = frame + bytes(256 - len(frame))
    inp = response + bytes(256 - len(response))
    out_setup = struct.pack("<BBHHH", 0x21, 9, 0x0200, 4, 256)
    in_setup = struct.pack("<BBHHH", 0xA1, 1, 0x0100, 4, 256)
    records.extend([
        (0, False, 0, irp_base, out_setup + out),
        (0, True, 3, irp_base, b""),
        (0x80, False, 0, irp_base+1, in_setup),
        (0x80, True, 3, irp_base+1, inp),
    ])


def wet_readback(value: int) -> bytes:
    words = (1, 20, 10, 200, 50, 80, value)
    return ACPFrame(
        0x8F,
        b"\xFF" + b"".join(x.to_bytes(2, "little", signed=True) for x in words)
    ).to_bytes()


def fixture(path: Path, *, ack=b"\x8f", trailing_read=True):
    recs = []
    hid_transfer(recs, ACPFrame(0x8F, b"").to_bytes(), wet_readback(80), 1)
    hid_transfer(recs, ACPFrame(0x8F, b"\x06\x4f\x00").to_bytes(), ack, 3)
    hid_transfer(recs, ACPFrame(0x8F, b"").to_bytes(), wet_readback(79), 5)
    hid_transfer(recs, ACPFrame(0x8F, b"\x06\x50\x00").to_bytes(), ack, 7)
    if trailing_read:
        hid_transfer(recs, ACPFrame(0x8F, b"").to_bytes(), wet_readback(80), 9)

    with path.open("wb") as stream:
        stream.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 249))
        for n, (ep, done, stage, irp, data) in enumerate(recs):
            urb = USB.pack(
                28, irp, 0, 8 if done else 27, int(done),
                2, 1, ep, 2, len(data)
            ) + bytes([stage]) + data
            stream.write(struct.pack("<IIII", 1234567890, n*1000, len(urb), len(urb)))
            stream.write(urb)


class WriteAckTests(unittest.TestCase):
    def test_byte_exact_wet_detection(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "wet.pcap"
            fixture(f)
            records = list(packets(f))
            values = [decode_wet_write(p) for p in records]
            self.assertEqual([v for v in values if v is not None], [79, 80])
            self.assertEqual(select_board(records, None, None), (2, 1))
            self.assertEqual(select_board(records, 2, 1), (2, 1))
            with self.assertRaises(ValueError):
                select_board(records, 5, 9)

    def test_two_writes_are_associated_with_bare_ack_and_verified_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wet.pcap"
            fixture(path)
            result = inspect(analyze(path, 2, 1))
            self.assertEqual(result["write_count"], 2)
            self.assertEqual(result["recognized_bare_ack_count"], 2)
            self.assertFalse(result["unpaired_set_report_packets"])
            self.assertEqual(
                [w["ack_classification"] for w in result["writes"]],
                ["bare_8f_zero_padded", "bare_8f_zero_padded"],
            )
            self.assertEqual(
                [w["value"] for w in result["writes"]], [79, 80]
            )
            self.assertEqual(result["baseline_wet_from_prewrite_readback"], 80)
            self.assertTrue(result["final_write_matches_prewrite_baseline"])
            self.assertTrue(result["post_restore_readback_confirmed"])
            self.assertEqual(
                [r["wet"] for r in result["chorus_readbacks"]],
                [80, 79, 80],
            )

    def test_missing_final_readback_does_not_claim_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wet.pcap"
            fixture(path, trailing_read=False)
            result = inspect(analyze(path, 2, 1))
            self.assertEqual(result["baseline_wet_from_prewrite_readback"], 80)
            self.assertTrue(result["final_write_matches_prewrite_baseline"])
            self.assertFalse(result["post_restore_readback_confirmed"])

    def test_ack_alternate_shape_remains_unverified(self):
        self.assertEqual(ack_shape(b"\x8f" + bytes(255)), "bare_8f_zero_padded")
        self.assertEqual(ack_shape(b"\x8f\x01" + bytes(254)), "unknown")
        self.assertEqual(ack_shape(b"\x8f"), "nonstandard_report_length")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wet.pcap"
            fixture(path, ack=b"\x8f\x01")
            result = inspect(analyze(path, 2, 1))
            self.assertEqual(result["recognized_bare_ack_count"], 0)
            self.assertEqual(result["write_count"], 2)
            self.assertEqual(result["writes"][0]["ack_classification"], "unknown")

    def test_nonstandard_outgoing_command_is_not_treated_as_wet_write(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "wet.pcap"
            fixture(path)
            records = list(packets(path))
            altered = dict(records[4])
            altered["payload_hex"] = (
                ACPFrame(0x8F, b"\x05\x4f\x00").to_bytes()
                + bytes(248)
            ).hex(" ")
            self.assertIsNone(decode_wet_write(altered))


if __name__ == "__main__":
    unittest.main()
