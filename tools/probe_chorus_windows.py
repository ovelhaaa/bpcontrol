"""M1F: one explicit physical BP1032 Chorus wet ±1 probe with verified rollback.

This is the ONLY hardware-writing BPControl script. It refuses to run without
all three independent opt-ins: --live-chorus-probe, --expect-wet N,
--authorize-one-temporary-write.

WARNING: A timeout/device disconnect can leave the Chorus value modified.
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

WORKER_LIMIT_SECONDS = 15


def worker(expected_wet: int) -> int:
    from bpcontrol.usb_chorus_probe import ChorusWetProbeSession, run_one_probe

    with ChorusWetProbeSession() as session:
        result = run_one_probe(session, expected_wet)
    print(json.dumps(result.as_dict(), ensure_ascii=False), flush=True)
    return 0 if result.status == "PASS_RESTORED" else 4


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-chorus-probe", action="store_true",
        help="authorize the temporary Chorus wet ±1 experiment on the physical BP1032"
    )
    parser.add_argument(
        "--expect-wet", type=int, metavar="0..100",
        help="require this exact live Chorus wet value before ANY parameter write"
    )
    parser.add_argument(
        "--authorize-one-temporary-write", action="store_true",
        help="confirm temporary alteration and single restoration, NEVER flash save"
    )
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if not (args.live_chorus_probe and args.authorize_one_temporary_write
            and args.expect_wet is not None):
        parser.print_help()
        print("\nNO USB ACCESS. All three explicit options are mandatory.")
        return 0
    if not 0 <= args.expect_wet <= 100:
        parser.error("--expect-wet must be 0..100")
    if sys.platform != "win32":
        parser.error("Windows HID transport is required")

    if args._worker:
        # The parent is responsible for enforcing the watchdog.
        try:
            return worker(args.expect_wet)
        except Exception as exc:
            print(
                f"REFUSED/FAILED: {type(exc).__name__}: {exc}. "
                "If a write could have started, device state is UNCERTAIN; "
                "verify manually before another attempt.",
                file=sys.stderr, flush=True
            )
            return 5

    print("M1F — EXPLICIT PHYSICAL CHORUS PROBE", flush=True)
    print("ACPWorkbench MUST be CLOSED and audio muted; no other HID control apps.", flush=True)
    print("Only Chorus 0x8F field 6 (wet), one-point change and single restore.", flush=True)
    print(f"Preflight requires CURRENT wet={args.expect_wet}; mismatches refuse writes.", flush=True)
    print("No firmware save, no reset, no retries, no writes to other effects.", flush=True)
    print(
        f"Watchdog {WORKER_LIMIT_SECONDS}s: timeout kills worker and might interrupt "
        "restoration, leaving device state UNCERTAIN.", flush=True
    )
    try:
        child = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--_worker",
             "--live-chorus-probe", "--authorize-one-temporary-write",
             "--expect-wet", str(args.expect_wet)],
            capture_output=True, text=True, timeout=WORKER_LIMIT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        if exc.stdout:
            print(exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes)
                  else exc.stdout, end="")
        if exc.stderr:
            print(exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes)
                  else exc.stderr, file=sys.stderr, end="")
        print(
            "TIMEOUT — STATE UNCERTAIN. Worker terminated, no automatic retry. "
            "Open ACPWorkbench only after the worker has exited and verify "
            "Chorus wet; restore manually if necessary.",
            file=sys.stderr
        )
        return 3
    if child.stdout:
        print(child.stdout, end="")
    if child.stderr:
        print(child.stderr, end="", file=sys.stderr)
    if child.returncode == 0:
        print(
            "PASS: single temporary write was ACKed/read back; all 7 Chorus "
            "fields restored and verified. No persistent save sent."
        )
        return 0
    print(
        "NOT PASSED: do not automatically retry. Verify Chorus wet manually "
        "in ACPWorkbench before further development.",
        file=sys.stderr
    )
    return child.returncode or 2


if __name__ == "__main__":
    raise SystemExit(main())
