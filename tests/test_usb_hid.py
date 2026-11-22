"""Zero-hardware tests for MI_04 control transport framing."""
import unittest

from bpcontrol.usb_hid import (
    API_REPORT_SIZE, WIRE_DATA_SIZE, HIDTransportError,
    make_chorus_output_report, parse_chorus_input_report, ChorusSnapshot,
)


class WindowsHidFramingTests(unittest.TestCase):
    def setUp(self):
        self.response = bytes.fromhex(
            "A5 5A 8F 0F FF 01 00 14 00 0A 00 C8 00 32 00 50 00 50 00 16"
        )
        self.report = b"\x00" + self.response + bytes(WIRE_DATA_SIZE - len(self.response))

    def test_request_windows_buffer_vs_captured_wire(self):
        request = make_chorus_output_report()
        self.assertEqual(len(request), API_REPORT_SIZE)
        self.assertEqual(request[0], 0)
        self.assertEqual(request[1:6], bytes.fromhex("A5 5A 8F 00 16"))
        self.assertEqual(request[6:], bytes(251))
        self.assertEqual(len(request[1:]), WIRE_DATA_SIZE)

    def test_chorus_captured_reply(self):
        self.assertEqual(
            parse_chorus_input_report(self.report),
            ChorusSnapshot(1, 20, 10, 200, 50, 80, 80),
        )

    def test_id_mismatch_fails_closed(self):
        with self.assertRaisesRegex(HIDTransportError, "report-ID"):
            parse_chorus_input_report(bytes([1]) + self.report[1:])

    def test_nonzero_tail_fails_closed(self):
        mutated = bytearray(self.report)
        mutated[-1] = 1
        with self.assertRaisesRegex(HIDTransportError, "nonzero"):
            parse_chorus_input_report(bytes(mutated))

    def test_wrong_command_fails_closed(self):
        mutated = bytearray(self.report)
        mutated[3] = 0x94
        with self.assertRaisesRegex(HIDTransportError, "unexpected command"):
            parse_chorus_input_report(bytes(mutated))

    def test_bad_footer_fails_closed(self):
        mutated = bytearray(self.report)
        mutated[1 + len(self.response) - 1] = 0
        with self.assertRaisesRegex(HIDTransportError, "invalid ACP"):
            parse_chorus_input_report(bytes(mutated))

    def test_wrong_length_fails_closed(self):
        with self.assertRaisesRegex(HIDTransportError, "expected"):
            parse_chorus_input_report(self.report[:-1])


if __name__ == "__main__":
    unittest.main()
