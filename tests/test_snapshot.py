"""Offline 59-instance read-only catalog/snapshot/HID simulator regression tests."""
from pathlib import Path
import unittest

from bpcontrol.acp import ACPError, ACPFrame
from bpcontrol.device_info import parse_firmware_info, parse_system_status
from bpcontrol.snapshot import (
    read_catalog, require_observed_firmware, effect_record, build_snapshot,
)
from bpcontrol.usb_hid import API_REPORT_SIZE, HIDTransportError
from bpcontrol.usb_snapshot import WindowsSnapshotSession
from tools.render_snapshot import build_html, TEMPLATE


class OfflineCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = read_catalog()
        cls.firmware = parse_firmware_info(
            ACPFrame(0x00, bytes.fromhex("30 00 03 00 02 18 00")))
        cls.status = parse_system_status(
            ACPFrame(0x02, bytes.fromhex("FF 46 00 1A 00 00 40 01 40 01")))

    def test_catalog_exact_59_known_instances(self):
        items = self.catalog["effects"]
        self.assertEqual(len(items), 59)
        self.assertEqual([r["index"] for r in items], list(range(1, 60)))
        self.assertEqual([r["command"] for r in items],
                         [f"0x{0x80+i:02X}" for i in range(1, 60)])
        self.assertEqual(items[14]["name"], "Guitar:Chorus")
        self.assertGreater(len(items[41]["parameter_hints"]), 50)

    def test_firmware_gate_accept_and_reject(self):
        require_observed_firmware(self.firmware)
        other = parse_firmware_info(ACPFrame(0, bytes.fromhex("30 00 03 00 02 19 00")))
        with self.assertRaisesRegex(ACPError, "allowlist"):
            require_observed_firmware(other)

    def test_chorus_field_labels_use_confirmed_schema(self):
        row = self.catalog["effects"][14]
        record = effect_record(row, ACPFrame(0x8F,
            bytes.fromhex("FF 01 00 14 00 0A 00 C8 00 32 00 50 00 50 00")))
        self.assertTrue(record["schema_match"])
        self.assertEqual([f["signed"] for f in record["fields"]], [1,20,10,200,50,80,80])
        self.assertEqual(record["fields"][3]["name"], "modulation_rate")

    def test_unknown_eq_uses_only_hints_not_unverified_names(self):
        row = self.catalog["effects"][41]
        record = effect_record(row, ACPFrame(0xAA, b"\xFF" + bytes(158)))
        self.assertFalse(record["schema_match"])
        self.assertEqual(len(record["fields"]), 79)
        self.assertEqual(record["fields"][0]["name"], "field_00")
        self.assertEqual(record["fields"][0]["ini_hint"], "enable")
        self.assertEqual(record["fields"][0]["mapping"], "unknown")

    def test_signed_and_unsigned_preserved(self):
        row = self.catalog["effects"][0]
        record = effect_record(row, ACPFrame(0x81, bytes.fromhex("FF 00 00 9C E6")))
        self.assertEqual(record["fields"][1]["signed"], -6500)
        self.assertEqual(record["fields"][1]["unsigned"], 59036)

    def test_stop_on_invalid_effect_reply(self):
        row = self.catalog["effects"][0]
        for frame in (ACPFrame(0x81, bytes.fromhex("01 02 03")),
                      ACPFrame(0x81, bytes.fromhex("FF 01")),
                      ACPFrame(0x82, bytes.fromhex("FF 01 00"))):
            with self.subTest(frame=frame), self.assertRaises(ACPError):
                effect_record(row, frame)

    def test_complete_requires_all_59(self):
        with self.assertRaises(ACPError):
            build_snapshot(self.catalog, self.firmware, self.status, {})
        partial = build_snapshot(self.catalog, self.firmware, self.status, {},
                                 failed_index=1, error="test abort")
        self.assertEqual(len(partial["effects"]), 59)
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["effects"][0]["status"], "error")
        self.assertEqual(partial["effects"][1]["status"], "unread")

    def test_self_contained_html_escapes_embedded_data(self):
        source = build_snapshot(self.catalog, self.firmware, self.status, {},
                                failed_index=1, error="danger </script><script>alert(1)</script>")
        page = build_html(source, TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(page.count("<script type=\"application/json\""), 1)
        self.assertNotIn("</script><script>alert(1)</script>", page)
        self.assertIn("\\u003c/script\\u003e", page)
        self.assertNotIn("__BPCONTROL_JSON__", page)


class FakeHid:
    """Imitates USB report payloads without touching a physical USB device."""
    def __init__(self):
        self.commands = []
        self.response = None

    def HidD_SetOutputReport(self, handle, raw, size):
        sent = bytes(raw)
        assert size == API_REPORT_SIZE
        assert sent[0] == 0
        assert sent[1:3] == b"\xA5\x5A"
        assert sent[4] == 0
        assert sent[6:] == bytes(251)
        cmd = sent[3]
        self.commands.append(cmd)
        payload = (
            bytes.fromhex("30 00 03 00 02 18 00") if cmd == 0 else
            bytes.fromhex("FF 46 00 1A 00 00 40 01 40 01") if cmd == 2 else
            bytes.fromhex("FF 00 00 9C E6")
        )
        frame = ACPFrame(cmd, payload).to_bytes()
        self.response = b"\x00" + frame + bytes(256 - len(frame))
        return 1

    def HidD_GetInputReport(self, handle, incoming, size):
        assert size == API_REPORT_SIZE
        for i, b in enumerate(self.response):
            incoming[i] = b
        return 1


class ReadOnlySessionTests(unittest.TestCase):
    def setUp(self):
        self.session = WindowsSnapshotSession()
        self.session._handle = 123  # fake handle: do NOT use __enter__ (actual OS)
        self.hid = FakeHid()
        self.session._hiddll = self.hid

    def test_opcode_allowlist_and_firmware_gate(self):
        with self.assertRaisesRegex(HIDTransportError, "verify observed firmware"):
            self.session.query(0x81)
        for cmd in (0x01, 0x80, 0xFC, 0xFD, 0xFE, 0xFF, -1, 256, True):
            with self.subTest(cmd=cmd), self.assertRaises(HIDTransportError):
                self.session.query(cmd)
        fw = self.session.query(0)
        self.session.authorize_after_firmware(fw)
        status = self.session.query(2)
        effect = self.session.query(0x81)
        self.assertEqual(effect.payload[0], 0xFF)
        self.assertEqual(status.payload[0], 0xFF)
        self.assertEqual(self.hid.commands, [0, 2, 0x81])

    def test_unverified_firmware_blocks_all_effects(self):
        with self.assertRaises(ACPError):
            self.session.authorize_after_firmware(
                ACPFrame(0, bytes.fromhex("30 00 03 01 02 18 00")))
        with self.assertRaises(HIDTransportError):
            self.session.query(0x81)
        self.assertEqual(self.hid.commands, [])


if __name__ == "__main__":
    unittest.main()
