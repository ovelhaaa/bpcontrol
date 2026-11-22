"""Capture exactly one bounded, read-only snapshot of 59 BP1032 effect instances.

This is an EXPERIMENTAL hardware operation (firmware and status previously
validated on the physical board, 59-instance batch not yet validated).
No writes to any DSP parameters, no 0xFD/0xFE, no polling or retries.
The CLI does not touch USB unless --live-read-all is explicitly supplied.

Usage (ACPWorkbench closed):
  py tools/snapshot_windows.py --live-read-all --output artifacts/snapshots/bp1032.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
MAX_SECONDS = 45


def capture_once() -> dict:
    from bpcontrol.acp import effect_command
    from bpcontrol.device_info import parse_system_status
    from bpcontrol.snapshot import read_catalog, build_snapshot
    from bpcontrol.usb_snapshot import WindowsSnapshotSession

    catalog = read_catalog()
    captured = {}
    with WindowsSnapshotSession() as session:
        firmware = session.authorize_after_firmware(session.query(0x00))
        status = parse_system_status(session.query(0x02))
        for row in catalog["effects"]:
            index = row["index"]
            try:
                captured[index] = session.query(effect_command(index))
            except Exception as exc:
                # Fail closed: never continue querying after one unexpected reply.
                # Preserve the partial snapshot for diagnosis, not as complete data.
                return build_snapshot(
                    catalog, firmware, status, captured,
                    failed_index=index, error=f"{type(exc).__name__}: {exc}"
                )
    return build_snapshot(catalog, firmware, status, captured)


def main() -> int:
    parser = argparse.ArgumentParser(description="Opt-in BP1032 59-effect snapshot (READ ONLY)")
    parser.add_argument("--live-read-all", action="store_true",
                        help="authorize one bounded run of 61 known ACP read queries")
    parser.add_argument("--output", type=Path,
                        help="destination JSON (refuses to overwrite)")
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args._worker:
        # Parent always supervises this worker with a timeout. Manual invocation
        # of this hidden option is unsupported.
        result = capture_once()
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0

    if not args.live_read_all:
        parser.print_help()
        print("\nHardware NOT accessed. Supply --live-read-all and --output explicitly.")
        return 0
    if args.output is None:
        parser.error("--output is required with --live-read-all")
    if sys.platform != "win32":
        parser.error("the USB HID snapshot requires Windows")
    if args.output.exists():
        parser.error("output file already exists; choose a different name")
    print("READ-ONLY: close ACPWorkbench; BP1032 must be connected.", flush=True)
    print("Request budget: 1 firmware + 1 status + up to 59 effect READS.", flush=True)
    print("This 59-effect batch has not yet been physically validated.", flush=True)
    print(f"Parent watchdog: {MAX_SECONDS}s; no retries. No DSP writes.", flush=True)

    try:
        child = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--_worker"],
            capture_output=True, text=True, timeout=MAX_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        print("TIMEOUT: worker terminated; NO automatic retry and no output saved.", file=sys.stderr)
        return 3
    if child.returncode != 0:
        print(child.stderr.strip() or f"Worker error {child.returncode}", file=sys.stderr)
        print("Stopped; NO retries. No complete snapshot was saved.", file=sys.stderr)
        return 2

    try:
        snapshot = json.loads(child.stdout)
        if snapshot.get("format") != "bpcontrol-snapshot-v1":
            raise ValueError("wrong snapshot format")
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Invalid worker output: {exc}", file=sys.stderr)
        return 2

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(snapshot, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except FileExistsError:
        print("Destination exists; refused to overwrite.", file=sys.stderr)
        return 2
    print(f"Saved: {args.output}")
    print(f"Read: {snapshot['effect_count_read']}/59 effects")
    if snapshot["complete"]:
        print("COMPLETE. All effects were read. No DSP parameters changed.")
        return 0
    print(
        f"PARTIAL: stopped at effect {snapshot['error_effect_index']}: "
        f"{snapshot['error']}. No retry performed.", file=sys.stderr
    )
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
