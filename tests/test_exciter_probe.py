"""Offline tests for M1K-B Harmonic Exciter (0x9D) one-step probe."""
from __future__ import annotations

import subprocess
import sys
import unittest
from unittest import mock

from bpcontrol.acp import ACPFrame
from bpcontrol.usb_exciter_probe import (
    EXCITER_ACK_REPORT,
    ExciterProbeSession,
    exciter_values,
    parse_exciter_ack,
    plan_exciter_step,
    run_one_exciter_probe,
)
from bpcontrol.usb_hid import HIDTransportError
from tools import probe_exciter_windows


def exciter_frame(enable: int, cutoff: int, dry: int, wet: int) -> ACPFrame:
    words = (enable, cutoff, dry, wet)
    return ACPFrame(
        0x9D,
        b"\xFF" + b"".join(x.to_bytes(2, "little", signed=True) for x in words),
    )


class FakeExciterSession(ExciterProbeSession):
    """In-memory fake HID session for offline M1K-B probe testing."""

    def __init__(
        self,
        initial: tuple[int, int, int, int] = (1, 1000, 100, 100),
        *,
        drift_on_second_read: bool = False,
        fail_candidate_ack: bool = False,
        wrong_candidate_readback: tuple[int, int, int, int] | None = None,
        fail_restore_ack: bool = False,
        fail_restore_readback: bool = False,
    ) -> None:
        super().__init__()
        self._handle = object()
        self._firmware_ok = False
        self.state = list(initial)
        self.drift_on_second_read = drift_on_second_read
        self.fail_candidate_ack = fail_candidate_ack
        self.wrong_candidate_readback = wrong_candidate_readback
        self.fail_restore_ack = fail_restore_ack
        self.fail_restore_readback = fail_restore_readback
        self.queries: list[int] = []
        self.writes: list[tuple[int, int]] = []
        self._exciter_reads = 0

    def query(self, command: int) -> ACPFrame:
        self.queries.append(command)
        if command == 0x00:
            return ACPFrame(0x00, bytes.fromhex("30 00 03 00 02 18 00"))
        if command == 0x9D:
            self._exciter_reads += 1
            if self.drift_on_second_read and self._exciter_reads == 2:
                self.state[3] = max(0, self.state[3] - 5)
            return exciter_frame(*self.state)
        raise AssertionError(f"Unexpected query opcode: 0x{command:02X}")

    def authorize_after_firmware(self, frame: ACPFrame):
        self._firmware_ok = True
        return None

    def _exchange_write(self, field_index: int, value: int) -> None:
        self.writes.append((field_index, value))
        if len(self.writes) == 1:
            if self.fail_candidate_ack:
                # Simulate lost ACK after DSP may have already changed
                self.state[field_index] = value
                raise HIDTransportError("simulated lost candidate ACK")
            if self.wrong_candidate_readback is not None:
                self.state = list(self.wrong_candidate_readback)
            else:
                self.state[field_index] = value
            return
        if self.fail_restore_ack:
            raise HIDTransportError("simulated lost restore ACK")
        if not self.fail_restore_readback:
            self.state[field_index] = value


class ExciterProbeTests(unittest.TestCase):
    def test_ack_validation_is_strict(self):
        parse_exciter_ack(EXCITER_ACK_REPORT)
        for bad in (
            b"\x01\x9D" + bytes(255),
            b"\x00\x8F" + bytes(255),
            b"\x00\x9D\x01" + bytes(254),
            b"\x00\x9D" + bytes(254),
            "not bytes",
        ):
            with self.assertRaises(HIDTransportError):
                parse_exciter_ack(bad)  # type: ignore[arg-type]

    def test_exciter_values_strict_decoding(self):
        self.assertEqual(
            exciter_values(exciter_frame(1, 1000, 80, 50)),
            (1, 1000, 80, 50),
        )
        with self.assertRaises(HIDTransportError):
            exciter_values(ACPFrame(0x8F, b"\xFF" + bytes(8)))
        with self.assertRaises(HIDTransportError):
            exciter_values(ACPFrame(0x9D, b"\x00" + bytes(8)))
        with self.assertRaises(HIDTransportError):
            exciter_values(ACPFrame(0x9D, b"\xFF" + bytes(6)))

    def test_plan_exciter_step_bounds(self):
        self.assertEqual(plan_exciter_step("cutoff", 1000), 1100)
        self.assertEqual(plan_exciter_step("cutoff", 9950), 9850)
        self.assertEqual(plan_exciter_step("dry", 100), 99)
        self.assertEqual(plan_exciter_step("wet", 0), 1)
        for bad_field, bad_val in (
            ("cutoff", 300),
            ("cutoff", 999),
            ("cutoff", 10001),
            ("dry", -1),
            ("wet", 101),
            ("enable", 1),
        ):
            with self.assertRaises(HIDTransportError):
                plan_exciter_step(bad_field, bad_val)

    def test_happy_path_pass_restored_for_cutoff_dry_wet(self):
        for field, expected, field_idx, candidate in (
            ("cutoff", 1000, 1, 1100),
            ("dry", 100, 2, 99),
            ("wet", 100, 3, 99),
        ):
            with self.subTest(field=field):
                fake = FakeExciterSession((1, 1000, 100, 100))
                res = run_one_exciter_probe(fake, field, expected)
                self.assertEqual(res.status, "PASS_RESTORED")
                self.assertTrue(res.candidate_ack_valid)
                self.assertTrue(res.restoration_ack_valid)
                self.assertTrue(res.restoration_verified)
                self.assertEqual(res.candidate, candidate)
                self.assertEqual(res.baseline, (1, 1000, 100, 100))
                self.assertEqual(res.restoration_readback, (1, 1000, 100, 100))
                self.assertEqual(fake.writes, [(field_idx, candidate), (field_idx, expected)])
                self.assertEqual(fake.queries, [0x00, 0x9D, 0x9D, 0x9D, 0x9D])

    def test_preflight_mismatch_or_drift_refuses_without_writes(self):
        fake_mismatch = FakeExciterSession((1, 1000, 100, 100))
        with self.assertRaises(HIDTransportError):
            run_one_exciter_probe(fake_mismatch, "wet", 80)
        self.assertEqual(fake_mismatch.writes, [])

        fake_drift = FakeExciterSession((1, 1000, 100, 100), drift_on_second_read=True)
        with self.assertRaises(HIDTransportError):
            run_one_exciter_probe(fake_drift, "wet", 100)
        self.assertEqual(fake_drift.writes, [])

    def test_lost_candidate_ack_restores_once_and_verifies(self):
        fake = FakeExciterSession((1, 1000, 100, 100), fail_candidate_ack=True)
        res = run_one_exciter_probe(fake, "dry", 100)
        self.assertEqual(res.status, "ERROR_BUT_RESTORED")
        self.assertFalse(res.candidate_ack_valid)
        self.assertTrue(res.restoration_ack_valid)
        self.assertTrue(res.restoration_verified)
        self.assertEqual(fake.writes, [(2, 99), (2, 100)])

    def test_wrong_readback_or_failed_restore_never_claims_pass(self):
        fake_wrong = FakeExciterSession(
            (1, 1000, 100, 100),
            wrong_candidate_readback=(1, 1000, 100, 50),
        )
        res_wrong = run_one_exciter_probe(fake_wrong, "wet", 100)
        self.assertEqual(res_wrong.status, "ERROR_BUT_RESTORED")

        fake_uncertain = FakeExciterSession(
            (1, 1000, 100, 100),
            fail_restore_ack=True,
            fail_restore_readback=True,
        )
        res_unc = run_one_exciter_probe(fake_uncertain, "wet", 100)
        self.assertEqual(res_unc.status, "STATE_UNCERTAIN")
        self.assertFalse(res_unc.restoration_verified)

    def test_cli_without_all_flags_never_opens_usb(self):
        with mock.patch("tools.probe_exciter_windows.subprocess.run") as run:
            rc = probe_exciter_windows.main([])
        self.assertEqual(rc, 0)
        run.assert_not_called()

        with self.assertRaises(SystemExit):
            probe_exciter_windows.main([
                "--live-exciter-probe",
                "--authorize-one-temporary-write",
                "--field", "cutoff",
                "--expect-value", "300",
            ])

    def test_cli_timeout_fails_closed_without_retry(self):
        with (
            mock.patch.object(sys, "platform", "win32"),
            mock.patch(
                "tools.probe_exciter_windows.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["python"], 15),
            ) as run,
        ):
            rc = probe_exciter_windows.main([
                "--live-exciter-probe",
                "--authorize-one-temporary-write",
                "--field", "wet",
                "--expect-value", "100",
            ])
        self.assertEqual(rc, 3)
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
