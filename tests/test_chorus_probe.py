"""Pure offline simulations of the M1F live Chorus write/restore protocol.

No tests call Win32, hidapi or actual USB. The fake "device" always returns
mock ACP frames and records candidate/restoration values.
"""
from __future__ import annotations

import unittest

from bpcontrol.acp import ACPFrame
from bpcontrol.usb_chorus_probe import (
    ACK_REPORT, ChorusWetProbeSession, chorus_values,
    parse_wet_ack, plan_wet_step, run_one_probe,
)
from bpcontrol.usb_hid import HIDTransportError


class FakeProbe(ChorusWetProbeSession):
    def __init__(self, initial=(1, 20, 10, 200, 50, 80, 80),
                 *, fail_candidate=False, fail_restore=False,
                 fail_after_restore=False, preflight_drift=False,
                 changed_other_field=False):
        super().__init__()
        self._handle = 123  # fake only; never calls __enter__
        self.values = list(initial)
        self.sent: list[int] = []
        self.read_count = 0
        self.fail_candidate = fail_candidate
        self.fail_restore = fail_restore
        self.fail_after_restore = fail_after_restore
        self.preflight_drift = preflight_drift
        self.changed_other_field = changed_other_field

    def query(self, command: int):
        if command == 0x00:
            return ACPFrame(0, bytes.fromhex("30 00 03 00 02 18 00"))
        if command != 0x8F:
            raise HIDTransportError("fake only supports firmware and Chorus")
        self.read_count += 1
        if self.preflight_drift and self.read_count == 2:
            self.values[6] += 1
        if self.fail_after_restore and self._phase == 2:
            raise HIDTransportError("synthetic disconnected USB")
        payload = b"\xff" + b"".join(
            x.to_bytes(2, "little", signed=True) for x in self.values
        )
        return ACPFrame(0x8F, payload)

    def _exchange_write(self, value: int) -> None:
        # Uses exact session state guards in the REAL inherited send methods.
        self.sent.append(value)
        if self._phase == 1:
            self.values[6] = value
            if self.changed_other_field:
                self.values[3] += 1
            if self.fail_candidate:
                # Simulates ACK error AFTER the parameter was actually changed.
                raise HIDTransportError("synthetic lost candidate ACK")
        elif self._phase == 2:
            if self.fail_restore:
                # Restore command was attempted, but the board did not process it.
                raise HIDTransportError("synthetic restore failed")
            self.values[6] = value
            if self.changed_other_field:
                self.values[3] -= 1
        else:
            raise AssertionError("write only at phase 1 or 2")


class ChorusProbeTests(unittest.TestCase):
    def test_exact_bare_ack(self):
        self.assertEqual(len(ACK_REPORT), 257)
        parse_wet_ack(ACK_REPORT)
        for bad in (
            b"\x8F" + bytes(255),                  # missing ID slot
            b"\x00\x90" + bytes(255),             # Auto Wah ACK
            b"\x01\x8F" + bytes(255),             # unexpected ID
            b"\x00\x8F" + bytes(254) + b"\x01",  # dirty padding
            b"\x00\xA5\x5A\x8F\x00\x16" + bytes(251),  # ACP reply instead
        ):
            with self.subTest(bad=bad[:8]), self.assertRaises(HIDTransportError):
                parse_wet_ack(bad)

    def test_one_step_boundaries(self):
        self.assertEqual(plan_wet_step(80), 79)
        self.assertEqual(plan_wet_step(1), 0)
        self.assertEqual(plan_wet_step(0), 1)
        self.assertEqual(plan_wet_step(100), 99)
        for v in (-1, 101, 1.5, True, None):
            with self.subTest(v=v), self.assertRaises(HIDTransportError):
                plan_wet_step(v)

    def test_success_exact_candidate_then_restore(self):
        fake = FakeProbe()
        result = run_one_probe(fake, 80)
        self.assertEqual(result.status, "PASS_RESTORED")
        self.assertEqual(result.candidate, 79)
        self.assertEqual(result.candidate_readback[6], 79)
        self.assertEqual(result.restoration_readback[6], 80)
        self.assertTrue(result.candidate_ack_valid)
        self.assertTrue(result.restoration_ack_valid)
        self.assertTrue(result.restoration_verified)
        self.assertEqual(result.error_messages, ())
        self.assertEqual(fake.sent, [79, 80])
        self.assertEqual(fake.read_count, 4)
        with self.assertRaises(HIDTransportError):
            fake.send_restoration_once()
        with self.assertRaises(HIDTransportError):
            fake.send_candidate_once()

    def test_stale_expected_value_refuses_without_writing(self):
        fake = FakeProbe()
        with self.assertRaisesRegex(HIDTransportError, "NO WRITES"):
            run_one_probe(fake, 81)
        self.assertEqual(fake.sent, [])

    def test_wrong_firmware_refuses_without_writing(self):
        fake = FakeProbe()
        def query(cmd):
            if cmd == 0:
                return ACPFrame(0, bytes.fromhex("30 00 03 00 02 19 00"))
            return FakeProbe.query(fake, cmd)
        fake.query = query
        with self.assertRaisesRegex(ValueError, "allowlist"):
            run_one_probe(fake, 80)
        self.assertEqual(fake.sent, [])

    def test_preflight_drift_refuses_without_writing(self):
        fake = FakeProbe(preflight_drift=True)
        with self.assertRaisesRegex(HIDTransportError, "NO WRITES"):
            run_one_probe(fake, 80)
        self.assertEqual(fake.sent, [])

    def test_failed_candidate_ack_still_restores_once(self):
        fake = FakeProbe(fail_candidate=True)
        result = run_one_probe(fake, 80)
        self.assertEqual(result.status, "ERROR_BUT_RESTORED")
        self.assertFalse(result.candidate_ack_valid)
        self.assertTrue(result.restoration_ack_valid)
        self.assertTrue(result.restoration_verified)
        self.assertEqual(fake.sent, [79, 80])

    def test_failed_restore_must_be_uncertain(self):
        fake = FakeProbe(fail_restore=True)
        result = run_one_probe(fake, 80)
        self.assertEqual(result.status, "STATE_UNCERTAIN")
        self.assertTrue(result.candidate_ack_valid)
        self.assertFalse(result.restoration_ack_valid)
        self.assertFalse(result.restoration_verified)
        self.assertEqual(fake.sent, [79, 80])
        self.assertEqual(fake.values[6], 79)

    def test_lost_final_readback_must_be_uncertain(self):
        fake = FakeProbe(fail_after_restore=True)
        result = run_one_probe(fake, 80)
        self.assertEqual(result.status, "STATE_UNCERTAIN")
        self.assertTrue(result.restoration_ack_valid)
        self.assertFalse(result.restoration_verified)
        self.assertEqual(fake.sent, [79, 80])

    def test_changes_in_other_chorus_fields_fail_closed(self):
        fake = FakeProbe(changed_other_field=True)
        # The fake changes another field transiently during the probe but
        # restores it later: candidate readback mismatch is still an error.
        result = run_one_probe(fake, 80)
        self.assertEqual(result.status, "ERROR_BUT_RESTORED")
        self.assertTrue(any("candidate" in err for err in result.error_messages))
        self.assertTrue(result.restoration_verified)
        self.assertEqual(fake.sent, [79, 80])

    def test_only_chorus_wet_field_is_used(self):
        fake = FakeProbe()
        fake._firmware_ok = True
        with self.assertRaises(HIDTransportError):
            fake.send_candidate_once()
        with self.assertRaises(HIDTransportError):
            fake.send_restoration_once()
        frame = ACPFrame(0x90, bytes.fromhex("FF 00 00"))
        with self.assertRaises(HIDTransportError):
            chorus_values(frame)


if __name__ == "__main__":
    unittest.main()
