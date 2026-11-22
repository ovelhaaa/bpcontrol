import unittest

from bpcontrol.acp import (
    ACPError, ACPFrame, decode_frame, decode_readback,
    encode_read, encode_write, is_ack, parse_hex,
)


class TestACP(unittest.TestCase):
    def test_read_chorus(self):
        self.assertEqual(encode_read(15).hex(" ").upper(), "A5 5A 8F 00 16")

    def test_pitch_plus_7_and_12(self):
        self.assertEqual(encode_write(20, 1, 70).hex(" ").upper(), "A5 5A 94 03 01 46 00 16")
        self.assertEqual(encode_write(20, 1, 120).hex(" ").upper(), "A5 5A 94 03 01 78 00 16")

    def test_negative_16_bit(self):
        self.assertEqual(encode_write(13, 3, -14).hex(" ").upper(), "A5 5A 8D 03 03 F2 FF 16")

    def test_chorus_fixture(self):
        h = "A5 5A 8F 0F FF 01 00 07 00 05 00 64 00 19 00 50 00 5A 00 16"
        self.assertEqual(decode_readback(parse_hex(h), 15), [1, 7, 5, 100, 25, 80, 90])

    def test_echo_fixture(self):
        h = "A5 5A 8A 13 FF 01 00 28 23 F5 32 2C 01 00 00 5E 01 01 00 5A 00 5A 00 16"
        self.assertEqual(decode_readback(parse_hex(h), 10), [1, 9000, 13045, 300, 0, 350, 1, 90, 90])

    def test_pingpong_fixture(self):
        h = "A5 5A 8E 0D FF 01 00 26 40 2C 01 01 00 50 00 E8 03 16"
        self.assertEqual(decode_readback(parse_hex(h), 14), [1, 16422, 300, 1, 80, 1000])

    def test_music_delay_fixture(self):
        h = "A5 5A 9C 09 FF 01 00 06 00 32 00 01 00 16"
        self.assertEqual(decode_readback(parse_hex(h), 28), [1, 6, 50, 1])

    def test_pitch_fixture(self):
        self.assertEqual(
            decode_readback(parse_hex("A5 5A 94 05 FF 01 00 78 00 16"), 20),
            [1, 120],
        )

    def test_ack(self):
        self.assertTrue(is_ack(b"\x94", 20))
        self.assertFalse(is_ack(b"\x8F", 20))

    def test_reject_malformed(self):
        with self.assertRaises(ACPError):
            decode_frame(parse_hex("A5 5A 8F 02 01 16"))
        with self.assertRaises(ACPError):
            encode_write(15, 1, 65535)
        with self.assertRaises(ACPError):
            decode_readback(parse_hex("A5 5A 8F 02 FF 01 16"))

    def test_frame_roundtrip(self):
        frame = ACPFrame(0x94, b"\x01\x78\x00")
        self.assertEqual(decode_frame(frame.to_bytes()), frame)


if __name__ == "__main__":
    unittest.main()
