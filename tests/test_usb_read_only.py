"""Offline tests for narrowly whitelisted BP1032 firmware/status reads."""
import unittest

from bpcontrol.acp import ACPFrame
from bpcontrol.usb_hid import API_REPORT_SIZE, WIRE_DATA_SIZE, HIDTransportError
from bpcontrol.usb_read_only import make_read_output_report, parse_read_input_report


def report(command, data):
    frame = ACPFrame(command, data).to_bytes()
    return b"\x00" + frame + bytes(WIRE_DATA_SIZE - len(frame))


class ReadOnlyTests(unittest.TestCase):
    def test_firmware_request_bytes(self):
        raw = make_read_output_report(0x00)
        self.assertEqual(len(raw), API_REPORT_SIZE)
        self.assertEqual(raw[1:6], bytes.fromhex("A5 5A 00 00 16"))
        self.assertEqual(raw[6:], bytes(251))

    def test_status_request_bytes(self):
        raw = make_read_output_report(0x02)
        self.assertEqual(len(raw), API_REPORT_SIZE)
        self.assertEqual(raw[1:6], bytes.fromhex("A5 5A 02 00 16"))

    def test_real_firmware_response_fixture(self):
        # An earlier ACPWorkbench log reports this exact 7-byte firmware payload.
        frame = parse_read_input_report(
            report(0x00, bytes.fromhex("30 00 03 00 02 18 00")), 0x00
        )
        self.assertEqual(frame.command, 0x00)
        self.assertEqual(frame.payload, bytes.fromhex("30 00 03 00 02 18 00"))

    def test_status_preserves_opaque_payload(self):
        payload = bytes.fromhex("11 22 33 44 55 66 77 88 99")
        self.assertEqual(parse_read_input_report(report(0x02, payload), 0x02).payload, payload)

    def test_unknown_commands_blocked_before_any_io(self):
        for command in (0x01, 0x8F, 0x80, 0xFD, 0xFE, 0xFF, 256, -1, True):
            with self.subTest(command=command):
                with self.assertRaises(HIDTransportError):
                    make_read_output_report(command)

    def test_wrong_reply_command(self):
        with self.assertRaisesRegex(HIDTransportError, "unexpected ACP command"):
            parse_read_input_report(report(0x02, b"abc"), 0x00)

    def test_firmware_wrong_length(self):
        with self.assertRaisesRegex(HIDTransportError, "firmware reply size"):
            parse_read_input_report(report(0x00, b"123"), 0x00)

    def test_report_id_and_nonzero_padding_rejected(self):
        good = report(0x02, b"123")
        with self.assertRaisesRegex(HIDTransportError, "report ID"):
            parse_read_input_report(b"\x01" + good[1:], 0x02)
        with self.assertRaisesRegex(HIDTransportError, "padding"):
            parse_read_input_report(good[:-1] + b"\x01", 0x02)


if __name__ == "__main__":
    unittest.main()
