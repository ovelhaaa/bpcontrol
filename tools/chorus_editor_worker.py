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


def run_action(mode: str, expected_json: str | None, target: int | None) -> dict:
    from bpcontrol.chorus_editor import (
        ChorusEditorSession, read_editor_chorus, apply_one_editor_step,
        validate_editor_target,
    )

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
    if args.read and (args.authorize_one_apply or args.expected_fields is not None
                      or args.target is not None):
        parser.error("read mode rejects write-related flags")

    try:
        response = run_action(
            "apply" if args.apply else "read", args.expected_fields, args.target
        )
    except (ValueError, RuntimeError, OSError) as exc:
        # Exceptions from preflight refuse before mutation; any unexpected
        # transport exception after dispatch must be treated conservatively.
        response = {"status": "READ_ERROR" if args.read else "STATE_UNCERTAIN",
                    "error": f"{type(exc).__name__}: {exc}",
                    "instruction": "If a write may have begun, verify state manually."}
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0 if response["status"] in ("READ_OK", "APPLIED_VERIFIED") else 4


if __name__ == "__main__":
    raise SystemExit(main())
