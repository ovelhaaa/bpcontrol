"""Pure offline decoders for actual device firmware and status readbacks."""
import unittest

from bpcontrol.acp import ACPError, ACPFrame
from bpcontrol.device_info import parse_firmware_info, parse_system_status


class DeviceInfoTests(unittest.TestCase):
    def test_actual_firmware_from_physical_bp1032(self):
        frame = ACPFrame(0x00, bytes.fromhex("30 00 03 00 02 18 00"))
        info = parse_firmware_info(frame)
        self.assertEqual(info.type_code, 0x30)
        self.assertEqual(info.family, "BPxx AudioPlay SDK")
        self.assertEqual(info.firmware_version, "0.3.0")
        self.assertEqual(info.effects_library_version, "2.24.0")

    def test_actual_status_from_physical_bp1032(self):
        frame = ACPFrame(0x02, bytes.fromhex("FF 46 00 1A 00 00 40 01 40 01"))
        status = parse_system_status(frame)
        self.assertEqual(status.memory_kb, 70)
        self.assertEqual(status.cpu_usage_raw, 26)
        self.assertFalse(status.external_parameter_change)
        self.assertEqual(status.cpu_max_mhz, 320)
        self.assertEqual(status.memory_max_kb, 320)
        self.assertAlmostEqual(status.memory_percent, 21.875)

    def test_nonmatching_command_or_payload_size_rejected(self):
        for frame in (
            ACPFrame(0x02, bytes.fromhex("30 00 03 00 02 18 00")),
            ACPFrame(0x00, bytes.fromhex("30 00 03")),
        ):
            with self.subTest(frame=frame), self.assertRaises(ACPError):
                parse_firmware_info(frame)

        for frame in (
            ACPFrame(0x00, bytes.fromhex("FF 46 00 1A 00 00 40 01 40 01")),
            ACPFrame(0x02, bytes.fromhex("FF 46 00 1A 00")),
            ACPFrame(0x02, bytes.fromhex("00 46 00 1A 00 00 40 01 40 01")),
            ACPFrame(0x02, bytes.fromhex("FF 46 00 1A 00 02 40 01 40 01")),
        ):
            with self.subTest(frame=frame), self.assertRaises(ACPError):
                parse_system_status(frame)

    def test_zero_max_memory_safe_and_flag_one(self):
        frame = ACPFrame(0x02, bytes.fromhex("FF 00 00 00 00 01 40 01 00 00"))
        status = parse_system_status(frame)
        self.assertTrue(status.external_parameter_change)
        self.assertIsNone(status.memory_percent)

    def test_unknown_firmware_type_preserved(self):
        info = parse_firmware_info(ACPFrame(0, bytes.fromhex("F7 01 02 03 04 05 06")))
        self.assertEqual(info.type_code, 0xF7)
        self.assertIn("0xF7", info.family)


if __name__ == "__main__":
    unittest.main()
