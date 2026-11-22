"""Explicit one-shot Windows HID firmware/status reader for BP1032.

No writes to DSP parameters. No polling. Hardware is never opened unless a
--live-read-* option is supplied. Worker is bounded by parent process timeout.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

WORKER_COMMANDS = {"firmware": 0x00, "status": 0x02}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-shot BP1032 firmware or runtime status READ (no field writes)"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--live-read-firmware", action="store_true",
                       help="explicitly authorize one 0x00 firmware read")
    group.add_argument("--live-read-status", action="store_true",
                       help="explicitly authorize one 0x02 status read")
    parser.add_argument("--_worker", choices=sorted(WORKER_COMMANDS), help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args._worker is not None:
        from bpcontrol.usb_read_only import read_info_once
        from bpcontrol.device_info import parse_firmware_info, parse_system_status

        command = WORKER_COMMANDS[args._worker]
        reply = read_info_once(command)
        print(f"READ OK: {args._worker} command=0x{command:02X}")
        print("raw_payload_hex: " + reply.payload.hex(" ").upper())
        print("payload_bytes: " + str(len(reply.payload)))
        if command == 0x00:
            info = parse_firmware_info(reply)
            print(f"firmware_type: 0x{info.type_code:02X} ({info.family})")
            print(f"firmware_version: {info.firmware_version}")
            print(f"effects_library_version: {info.effects_library_version}")
        else:
            state = parse_system_status(reply)
            print(f"memory_used_kb: {state.memory_kb}")
            print(f"memory_max_kb: {state.memory_max_kb}")
            if state.memory_percent is not None:
                print(f"memory_usage_percent: {state.memory_percent:.1f}")
            print(f"cpu_usage_mcps: {state.cpu_mcps} (million cycles per second; ACPWorkbench manual §8.1)")
            if state.cpu_percent_of_nominal_max is not None:
                print(f"cpu_nominal_max_percent: {state.cpu_percent_of_nominal_max:.1f} (not instant CPU utilization)")
            print(f"cpu_max_frequency_mhz: {state.cpu_max_mhz}")
            print(f"external_parameter_change: {int(state.external_parameter_change)}")
        return 0

    mode = "firmware" if args.live_read_firmware else (
        "status" if args.live_read_status else None
    )
    if mode is None:
        parser.print_help()
        print("\nNo USB access was performed; pass exactly one --live-read-* flag.")
        return 0
    if sys.platform != "win32":
        parser.error("Windows is required for this HID control test")

    print("Close ACPWorkbench first. Only ONE read query will be transmitted.", flush=True)
    print("No parameter writes, flash saves, firmware upgrades or retries.", flush=True)
    try:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--_worker", mode],
            capture_output=True, text=True, timeout=4, check=False,
        )
    except subprocess.TimeoutExpired:
        print("TIMEOUT: worker stopped. No automatic retry.", file=sys.stderr)
        return 3
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    if completed.returncode:
        print(f"Read failed (worker code {completed.returncode}); no retry.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
