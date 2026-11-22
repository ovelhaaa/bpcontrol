"""One-shot, explicitly opt-in BP1032 MI_04 read over Windows HID.

Requires Windows and the already installed `hidapi` Python package.
The parent kills the worker after 4 seconds, so synchronous Win32 HID calls
cannot leave the command running indefinitely. No retries or effect writes.
"""
from pathlib import Path
import argparse
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Single BP1032 Chorus read; NEVER write effect parameters")
    parser.add_argument("--live-read-chorus", action="store_true",
                        help="explicitly authorize one ACP read on verified MI_04")
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args._worker:
        from bpcontrol.usb_hid import read_guitar_chorus_once
        snapshot = read_guitar_chorus_once()
        print("READ OK: 0x8F Guitar Chorus")
        print(
            "values: enable={0.enable}, delay_length={0.delay_length}, "
            "depth={0.modulation_depth}, rate_raw={0.modulation_rate_raw}, "
            "feedback={0.feedback}, dry={0.dry}, wet={0.wet}".format(snapshot)
        )
        return 0

    if not args.live_read_chorus:
        parser.print_help()
        print("\nNo device was opened. Supply --live-read-chorus to perform ONE read.")
        return 0
    if sys.platform != "win32":
        parser.error("Only available on Windows")
    print("Make sure ACPWorkbench is CLOSED, BP1032 is connected, and the audio is muted.")
    print("Attempting exactly ONE SET_REPORT read query and ONE GET_REPORT response.")
    print("A timed-out worker will be terminated; NO retry is performed.", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--_worker"],
            capture_output=True, text=True, timeout=4, check=False,
        )
    except subprocess.TimeoutExpired:
        print("TIMEOUT after 4 seconds: worker terminated, no automatic retry.", file=sys.stderr)
        return 3
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    if result.returncode:
        print(f"Read failed (worker exit code {result.returncode}); no retry.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
