"""Offline regression checks for USBPcap framing and fail-closed evidence export."""
import struct
import tempfile
from pathlib import Path
import unittest

from tools.analyze_usb_capture import USB, analyze, chorus_exchanges, frames, write_sanitized_chorus


def fixture(path, response_padding=0):
    request = bytes.fromhex('a5 5a 8f 00 16') + bytes(251)
    response = bytes.fromhex('a5 5a 8f 0f ff 01 00 14 00 0a 00 c8 00 32 00 50 00 50 00 16')
    response += bytes([response_padding]) + bytes(235)
    setup_out = struct.pack('<BBHHH', 0x21, 9, 0x0200, 4, 256)
    setup_in = struct.pack('<BBHHH', 0xa1, 1, 0x0100, 4, 256)
    with path.open('wb') as f:
        f.write(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 249))
        # Deliberately reuse one kernel IRP across every separate operation.
        records = [(0, 0, 0, setup_out + request), (0, 1, 3, b''),
                   (128, 0, 0, setup_in), (128, 1, 3, response)] * 2
        for n, (ep, complete, stage, data) in enumerate(records):
            raw = USB.pack(28, 0xffff112233445566, 0, 8 if complete else 27,
                           complete, 2, 1, ep, 2, len(data)) + bytes([stage]) + data
            f.write(struct.pack('<IIII', 1234567890, n * 1000, len(raw), len(raw)))
            f.write(raw)


class CaptureTests(unittest.TestCase):
    def test_report_id_not_in_usb_payload_and_irp_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / 'input.pcap'
            fixture(source)
            result = analyze(source, 2, 1)
            self.assertEqual([p['transaction'] for p in result['packets']],
                             [1, 1, 2, 2, 3, 3, 4, 4])
            self.assertEqual(result['packets'][0]['setup']['wValue'], 0x0200)
            self.assertEqual(result['packets'][0]['acp'][0]['offset'], 0)
            exchanges = chorus_exchanges(result)
            self.assertEqual(len(exchanges), 2)
            self.assertEqual(exchanges[0]['raw_values'], [1, 20, 10, 200, 50, 80, 80])
            dest = Path(d) / 'sanitized.pcap'
            write_sanitized_chorus(dest, result)
            clean = analyze(dest, 1, 1)
            self.assertEqual(len(chorus_exchanges(clean)), 2)
            self.assertEqual([p['payload_hex'] for p in clean['packets']],
                             [p['payload_hex'] for p in result['packets']])
            self.assertNotIn(struct.pack('<Q', 0xffff112233445566), dest.read_bytes())
            with self.assertRaises(FileExistsError):
                write_sanitized_chorus(dest, result)

    def test_nonzero_tail_refuses_export(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / 'input.pcap'
            fixture(source, response_padding=65)
            result = analyze(source, 2, 1)
            self.assertEqual(chorus_exchanges(result), [])
            with self.assertRaises(ValueError):
                write_sanitized_chorus(Path(d) / 'clean.pcap', result)

    def test_length_footer_and_offsets(self):
        self.assertFalse(frames(bytes.fromhex('a5 5a 8f 00 00'))[0]['complete'])
        self.assertFalse(frames(bytes.fromhex('a5 5a 8f ff 16'))[0]['complete'])
        self.assertEqual(frames(bytes.fromhex('42 a5 5a 8f 00 16'))[0]['offset'], 1)

    def test_truncated_capture_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / 'input.pcap'
            fixture(source)
            source.write_bytes(source.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, 'Truncated'):
                analyze(source, 2, 1)


if __name__ == '__main__':
    unittest.main()
