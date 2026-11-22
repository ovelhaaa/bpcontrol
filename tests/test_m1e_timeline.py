"""Synthetic offline timeline tests for mixed Chorus editing and Auto Wah toggles.

These PCAP records are fake: they do not represent an independent analysis
of the user's actual capture. No USB/HID access or parameter writes.
"""
from __future__ import annotations

import struct
import tempfile
from pathlib import Path
import unittest

from bpcontrol.acp import ACPFrame
from tools.analyze_usb_capture import USB, analyze
from tools.inspect_m1e_timeline import timeline


def readback(command: int, values: tuple[int, ...]) -> bytes:
    return ACPFrame(
        command, b"\xFF" + b"".join(v.to_bytes(2, "little", signed=True) for v in values)
    ).to_bytes()


def build_capture(path: Path, *, include_final_wah: bool):
    records = []
    def transaction(command: int, payload: bytes, reply: bytes):
        irp = 100 + 2 * len(records)//4
        sent = ACPFrame(command, payload).to_bytes()
        output = sent + bytes(256 - len(sent))
        incoming = reply + bytes(256 - len(reply))
        setup_out = struct.pack("<BBHHH", 0x21, 9, 0x0200, 4, 256)
        setup_in = struct.pack("<BBHHH", 0xA1, 1, 0x0100, 4, 256)
        records.extend([
            (0, False, 0, irp, setup_out + output),
            (0, True, 3, irp, b""),
            (0x80, False, 0, irp+1, setup_in),
            (0x80, True, 3, irp+1, incoming),
        ])

    chorus = lambda wet: readback(0x8F, (1,20,10,200,50,80,wet))
    wah = lambda enabled: readback(0x90, (enabled,100,200,1000,40,80,80))
    def write(command: int, field: int, value: int):
        transaction(command, bytes([field]) + value.to_bytes(2,"little",signed=True),
                    bytes([command]))

    transaction(0x8F, b"", chorus(80))
    transaction(0x90, b"", wah(0))
    write(0x8F, 6, 8)
    write(0x8F, 6, 81)
    write(0x90, 0, 1)
    transaction(0x90, b"", wah(1))
    write(0x8F, 6, 81)
    write(0x8F, 6, 8)
    write(0x90, 0, 0)
    write(0x8F, 6, 80)
    write(0x8F, 6, 80)
    transaction(0x8F, b"", chorus(80))
    if include_final_wah:
        transaction(0x90, b"", wah(0))

    with path.open("wb") as f:
        f.write(struct.pack("<IHHIIII", 0xA1B2C3D4,2,4,0,0,65535,249))
        for n,(endpoint, done, stage, irp, payload) in enumerate(records):
            urb = USB.pack(28, irp, 0, 8 if done else 27,
                           int(done), 2,1,endpoint,2,len(payload))
            urb += bytes([stage]) + payload
            f.write(struct.pack("<IIII",1234567890,n*1000,len(urb),len(urb)))
            f.write(urb)


class MixedActivityTimelineTests(unittest.TestCase):
    def test_typed_intermediate_values_separated_from_auto_wah(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"capture.pcap"
            build_capture(p,include_final_wah=True)
            result=timeline(analyze(p,2,1))
            self.assertEqual(result["chorus_wet_values"],[8,81,81,8,80,80])
            self.assertEqual(result["chorus_wet_baseline"],80)
            self.assertTrue(result["intermediate_numeric_editing_plausible"])
            self.assertTrue(result["chorus_wet_restoration_readback"])
            self.assertEqual(result["auto_wah_field0_values"],[1,0])
            self.assertEqual(result["auto_wah_original_field0"],0)
            self.assertTrue(result["auto_wah_restoration_verified"])
            self.assertEqual(result["auto_wah_field_writes"],2)
            self.assertEqual(len(result["chorus_wet_outliers"]),2)
            self.assertTrue(result["requires_review"])

    def test_missing_auto_wah_final_readback_remains_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"capture.pcap"
            build_capture(p,include_final_wah=False)
            result=timeline(analyze(p,2,1))
            self.assertIsNone(result["auto_wah_restoration_verified"])
            self.assertTrue(any("Auto Wah" in issue for issue in result["issues"]))


if __name__=="__main__":
    unittest.main()
