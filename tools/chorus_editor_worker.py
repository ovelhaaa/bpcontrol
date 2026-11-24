"""M1G GUI worker: one read OR one explicitly armed Chorus wet single-step Apply.

Use ONLY via the parent GUI, which imposes a subprocess deadline. Running
this script directly can block inside Windows HID. Every invocation opens
and closes one session and emits a single machine-readable JSON reply.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def run_action(
    mode: str,
    expected_json: str | None,
    target: int | None,
    effect_index: int | None = None,
) -> dict:
    from bpcontrol.acp import effect_command
    from bpcontrol.chorus_editor import (
        ChorusEditorSession, read_editor_chorus, apply_one_editor_step,
        validate_editor_target,
    )
    from bpcontrol.snapshot import INSTANCE_COUNT
    from bpcontrol.usb_snapshot import WindowsSnapshotSession

    if mode == "read_effect":
        if type(effect_index) is not int or not 1 <= effect_index <= INSTANCE_COUNT:
            raise ValueError("effect_index must be 1..59")
        with WindowsSnapshotSession() as session:
            session.authorize_after_firmware(session.query(0x00))
            cmd = effect_command(effect_index)
            frame = session.query(cmd)
            if (
                frame.command != cmd
                or frame.payload[:1] != b"\xff"
                or len(frame.payload) < 3
                or (len(frame.payload) - 1) % 2 != 0
            ):
                raise ValueError(f"Malformed readback payload for effect {effect_index}")
            raw_words = frame.payload[1:]
            words = [
                int.from_bytes(raw_words[i:i + 2], "little", signed=True)
                for i in range(0, len(raw_words), 2)
            ]
            return {
                "status": "EFFECT_READ_OK",
                "index": effect_index,
                "command": f"0x{cmd:02X}",
                "fields": words,
            }

    # Validate pure input *before* opening the USB collection.
    expected = None
    if mode == "apply":
        parsed = json.loads(expected_json or "")
        if not isinstance(parsed, list):
            raise ValueError("expected fields must be JSON array")
        expected = tuple(parsed)
        validate_editor_target(expected, target)

    with ChorusEditorSession() as session:
        try:
            if mode == "read":
                observed = read_editor_chorus(session)
                return {"status": "READ_OK", "fields": list(observed), "wet": observed[6]}
            if mode == "apply":
                return apply_one_editor_step(session, expected, target).as_dict()
            raise ValueError("unsupported mode")
        except Exception as exc:
            # Session phase is advanced BEFORE candidate HID SET_REPORT.
            # Any exception after that point means board state may be unknown.
            return {
                "status": "REFUSED_NO_WRITE" if session._phase == 0
                          else "STATE_UNCERTAIN",
                "error": f"{type(exc).__name__}: {exc}",
                "write_attempted": bool(session._phase),
            }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--read", action="store_true",
                       help="one non-mutating live read with firmware validation")
    modes.add_argument("--read-effect", type=int, metavar="INDEX",
                       help="one non-mutating live read of any effect instance (1..59)")
    modes.add_argument("--apply", action="store_true",
                       help="one confirmed single-point Chorus wet write")
    parser.add_argument("--expected-fields", type=str,
                        help="full seven-field JSON from previous live read")
    parser.add_argument("--target", type=int, help="target wet, one point apart")
    parser.add_argument("--authorize-one-apply", action="store_true",
                        help="explicit permission to make one volatile change")
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        parser.error("real USB HID control requires Windows")
    if args.apply and not (
        args.authorize_one_apply and args.expected_fields is not None
        and args.target is not None
    ):
        parser.error("apply requires --expected-fields, --target, --authorize-one-apply")
    if (args.read or args.read_effect is not None) and (
        args.authorize_one_apply or args.expected_fields is not None
        or args.target is not None
    ):
        parser.error("read mode rejects write-related flags")
    if args.read_effect is not None and not 1 <= args.read_effect <= 59:
        parser.error("--read-effect must be between 1 and 59")

    mode = "apply" if args.apply else ("read_effect" if args.read_effect is not None else "read")
    try:
        response = run_action(
            mode, args.expected_fields, args.target, effect_index=args.read_effect
        )
    except (ValueError, RuntimeError, OSError) as exc:
        # Exceptions from preflight refuse before mutation; any unexpected
        # transport exception after dispatch must be treated conservatively.
        response = {"status": "READ_ERROR" if mode != "apply" else "STATE_UNCERTAIN",
                    "error": f"{type(exc).__name__}: {exc}",
                    "instruction": "If a write may have begun, verify state manually."}
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0 if response["status"] in ("READ_OK", "EFFECT_READ_OK", "APPLIED_VERIFIED") else 4


if __name__ == "__main__":
    raise SystemExit(main())
