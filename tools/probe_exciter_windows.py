"""M1K-B: one explicit physical BP1032 Harmonic Exciter (0x9D) probe with verified rollback.

Refuses to run without all four independent opt-ins:
  --live-exciter-probe
  --field {cutoff,dry,wet}
  --expect-value N
  --authorize-one-temporary-write

WARNING: A timeout or device disconnect can leave the Exciter value modified.
Always confirm the state in ACPWorkbench if STATE_UNCERTAIN or TIMEOUT occurs.
Never run this while ACPWorkbench is open. This does NOT save to flash.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bpcontrol.usb_exciter_probe import PROBEABLE_EXCITER_FIELDS, plan_exciter_step  # noqa: E402
from bpcontrol.usb_hid import HIDTransportError  # noqa: E402

WORKER_LIMIT_SECONDS = 15


def worker(field_name: str, expected_value: int) -> int:
    from bpcontrol.usb_exciter_probe import ExciterProbeSession, run_one_exciter_probe

    with ExciterProbeSession() as session:
        result = run_one_exciter_probe(session, field_name, expected_value)
    print(json.dumps(result.as_dict(), ensure_ascii=False), flush=True)
    return 0 if result.status == "PASS_RESTORED" else 4


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-exciter-probe", action="store_true",
        help="authorize one temporary Harmonic Exciter (0x9D) step on the physical BP1032",
    )
    parser.add_argument(
        "--field", choices=tuple(PROBEABLE_EXCITER_FIELDS),
        help="Exciter field to test (cutoff, dry, or wet)",
    )
    parser.add_argument(
        "--expect-value", type=int, metavar="N",
        help="require this exact live value for the chosen field before ANY parameter write",
    )
    parser.add_argument(
        "--authorize-one-temporary-write", action="store_true",
        help="confirm temporary alteration and single restoration, NEVER flash save",
    )
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if not (
        args.live_exciter_probe
        and args.authorize_one_temporary_write
        and args.field is not None
        and args.expect_value is not None
    ):
        parser.print_help()
        print("\nNO USB ACCESS. All four explicit options are mandatory.")
        return 0

    try:
        plan_exciter_step(args.field, args.expect_value)
    except HIDTransportError as exc:
        parser.error(str(exc))

    if sys.platform != "win32":
        parser.error("Windows HID transport is required")

    if args._worker:
        try:
            return worker(args.field, args.expect_value)
        except Exception as exc:
            print(
                f"REFUSED/FAILED: {type(exc).__name__}: {exc}. "
                "If a write could have started, device state is UNCERTAIN; "
                "verify manually before another attempt.",
                file=sys.stderr, flush=True,
            )
            return 5

    print("M1K-B — EXPLICIT PHYSICAL HARMONIC EXCITER (0x9D) PROBE", flush=True)
    print("ACPWorkbench MUST be CLOSED and audio muted; no other HID control apps.", flush=True)
    print(f"Only Exciter 0x9D field '{args.field}', one small reversible step and single restore.", flush=True)
    print(f"Preflight requires CURRENT {args.field}={args.expect_value}; mismatches refuse writes.", flush=True)
    print("No firmware save, no reset, no retries, no writes to other effects.", flush=True)
    print(
        f"Watchdog {WORKER_LIMIT_SECONDS}s: timeout kills worker and might interrupt "
        "restoration, leaving device state UNCERTAIN.",
        flush=True,
    )
    try:
        child = subprocess.run(
            [
                sys.executable, str(Path(__file__).resolve()),
                "--_worker",
                "--live-exciter-probe",
                "--authorize-one-temporary-write",
                "--field", args.field,
                "--expect-value", str(args.expect_value),
            ],
            capture_output=True, text=True, timeout=WORKER_LIMIT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        if exc.stdout:
            print(
                exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout,
                end="",
            )
        if exc.stderr:
            print(
                exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr,
                file=sys.stderr, end="",
            )
        print(
            "TIMEOUT — STATE UNCERTAIN. Worker terminated, no automatic retry. "
            "Open ACPWorkbench only after the worker has exited and verify "
            "Exciter state; restore manually if necessary.",
            file=sys.stderr,
        )
        return 3
    if child.stdout:
        print(child.stdout, end="")
    if child.stderr:
        print(child.stderr, end="", file=sys.stderr)
    if child.returncode == 0:
        print(
            "PASS: single temporary Exciter write was ACKed/read back; all 4 Exciter "
            "fields restored and verified. No persistent save sent."
        )
        return 0
    print(
        "NOT PASSED: do not automatically retry. Verify Exciter state manually "
        "in ACPWorkbench before further development.",
        file=sys.stderr,
    )
    return child.returncode or 2


if __name__ == "__main__":
    raise SystemExit(main())
