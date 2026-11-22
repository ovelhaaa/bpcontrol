"""Offline event timeline for a mixed Guitar Chorus / Auto Wah ACPWorkbench capture.

Never opens a USB/HID device or sends ACP frames. Reuses the verified
USBPcap parser and read-ACK analyzer to explain unexpected GUI actions.

Read-only analysis:
  py tools/inspect_m1e_timeline.py artifacts/usb-capture/chorus-wet-01.pcapng
  py tools/inspect_m1e_timeline.py artifacts/usb-capture/chorus-wet-01.pcapng --json

No output file is needed. Only relevant effect commands (0x8F / 0x90)
are summarized, no device paths, serial numbers or unrelated payloads.
"""
from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.analyze_usb_capture import analyze, packets
from tools.analyze_chorus_write_ack import (
    HID_OUT, HID_IN, select_board, valid_pair, inspect,
)

EFFECT_NAMES = {0x8F: "Guitar Chorus", 0x90: "Guitar Auto Wah"}
PARAMETER_HINTS = {(0x8F, 6): "wet", (0x90, 0): "enable (INI hint)"}


def _roundtrip(scoped, i, command):
    """Inspect next USB control report pair, without assuming ACK success."""
    if i + 3 >= len(scoped):
        return "missing", None, None
    a, b, c, d = scoped[i:i+4]
    if not (valid_pair(a, b, 0) and c.get("setup") == HID_IN
            and valid_pair(c, d, 0x80)
            and b.get("payload_length") == 0
            and c.get("payload_length") == 0
            and d.get("payload_length") == 256):
        return "unpaired", None, None
    data = bytes.fromhex(d["payload_hex"])
    if data[0] == command and not any(data[1:]):
        return "bare_ack", None, d["number"]
    if data[:2] == b"\xA5\x5A" and len(data) == 256:
        size = 5 + data[3]
        if (size <= 256 and data[size-1] == 0x16
                and data[2] == command and not any(data[size:])):
            frame = data[:size]
            if frame[3] >= 1 and frame[4] == 0xFF and (frame[3]-1)%2 == 0:
                values = [int.from_bytes(frame[k:k+2], "little", signed=True)
                          for k in range(5, size-1, 2)]
                return "full_readback", values, d["number"]
            return "unexpected_acp_response", None, d["number"]
    return "unknown_reply", None, d["number"]


def timeline(result: dict) -> dict:
    """Return an evidence-only timeline of observed Chorus & Auto Wah ACP events."""
    scoped = result["packets"]
    events = []
    for i, p in enumerate(scoped):
        if (p.get("setup") != HID_OUT or p.get("endpoint") != 0
                or p.get("completion") or p.get("stage") != 0
                or p.get("status") or p.get("truncated")):
            continue
        try:
            raw = bytes.fromhex(p["payload_hex"])
        except (KeyError, TypeError, ValueError):
            continue
        if (len(raw) != 256 or raw[:2] != b"\xA5\x5A"
                or raw[2] not in EFFECT_NAMES):
            continue
        command = raw[2]
        size = 5 + raw[3]
        if size > 256 or raw[size-1] != 0x16 or any(raw[size:]):
            continue
        payload = raw[4:size-1]
        if len(payload) == 0:
            op = "read"
            field = None
            value = None
        elif len(payload) == 3:
            op = "field_write"
            field = payload[0]
            value = int.from_bytes(payload[1:3], "little", signed=True)
        else:
            op = "other_acp"
            field = None
            value = None
        result_kind, response_values, response_packet = _roundtrip(scoped, i, command)
        event = {
            "packet": p["number"],
            "time_s": p.get("relative_seconds"),
            "effect": EFFECT_NAMES[command],
            "command": f"0x{command:02X}",
            "operation": op,
            "field": field,
            "field_hint": PARAMETER_HINTS.get((command, field)),
            "value_raw": value,
            "response_kind": result_kind,
            "response_packet": response_packet,
        }
        if response_values is not None:
            event["readback_words"] = len(response_values)
            if command == 0x8F and len(response_values) == 7:
                event["wet_readback"] = response_values[6]
            if command == 0x90 and len(response_values) == 7:
                event["auto_wah_field0_readback"] = response_values[0]
        events.append(event)

    # Reuse the specialized strict read/ACK validator for cross-checking.
    chorus = inspect(result)
    chorus_writes = [
        event for event in events if event["command"] == "0x8F"
        and event["operation"] == "field_write"
        and event["field"] == 6
    ]
    wah_writes = [
        event for event in events if event["command"] == "0x90"
        and event["operation"] == "field_write"
    ]
    original_wet = chorus["baseline_wet_from_prewrite_readback"]
    outliers = [
        {"packet": event["packet"], "value_raw": event["value_raw"]}
        for event in chorus_writes
        if original_wet is not None
        and abs(event["value_raw"] - original_wet) > 1
    ]
    auto_wah_field0 = [e for e in wah_writes if e["field"] == 0]
    wah_readbacks = [
        e for e in events if e["command"] == "0x90"
        and "auto_wah_field0_readback" in e
    ]
    auto_wah_original = (
        next((e["auto_wah_field0_readback"] for e in reversed(wah_readbacks)
              if wah_writes and e["packet"] < wah_writes[0]["packet"]), None)
    )
    wah_post = [
        e for e in wah_readbacks
        if wah_writes and e["packet"] > wah_writes[-1]["packet"]
    ]
    auto_wah_restored = (
        None if auto_wah_original is None or not wah_post else
        wah_post[-1]["auto_wah_field0_readback"] == auto_wah_original
    )
    issues = []
    if len(chorus_writes) != 2:
        issues.append("Chorus wet was written more/fewer than the expected two times")
    if outliers:
        issues.append("Chorus wet values differ from baseline by more than one raw point")
    if wah_writes:
        issues.append("Other effect written: Auto Wah; capture is NOT isolated")
    if any(e["response_kind"] != "bare_ack" for e in chorus_writes):
        issues.append("At least one Chorus wet write lacks a recognized bare ACK")
    if not chorus["post_restore_readback_confirmed"]:
        issues.append("No confirmed post-write restoration of Chorus wet")
    if wah_writes and auto_wah_restored is not True:
        issues.append("Original Auto Wah field-0 state has not been proven restored")
    return {
        "format": "bpcontrol-m1e-mixed-activity-timeline-v1",
        "offline_only": True,
        "chorus_wet_writes": len(chorus_writes),
        "chorus_wet_values": [e["value_raw"] for e in chorus_writes],
        "chorus_wet_baseline": original_wet,
        "chorus_wet_outliers": outliers,
        "chorus_wet_restoration_readback": chorus["post_restore_readback_confirmed"],
        "auto_wah_field_writes": len(wah_writes),
        "auto_wah_field0_values": [e["value_raw"] for e in auto_wah_field0],
        "auto_wah_original_field0": auto_wah_original,
        "auto_wah_restoration_verified": auto_wah_restored,
        "issues": issues,
        "requires_review": bool(issues),
        "events": events,
        "note": "INI field names are hints. Full valid ACK/readback does not mean "
                "unplanned changes are harmless. Never authorize live writes from this report."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--bus", type=int)
    parser.add_argument("--device", type=int)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--tshark", default=shutil.which("tshark") or
                        r"C:\Program Files\Wireshark\tshark.exe")
    args = parser.parse_args()
    if (args.bus is None) != (args.device is None):
        parser.error("--bus and --device must be specified together")
    with tempfile.TemporaryDirectory(prefix="bpcontrol-m1e-timeline-") as tempdir:
        converted = args.capture
        with converted.open("rb") as stream:
            if stream.read(4) == b"\x0a\x0d\x0d\x0a":
                converted = Path(tempdir) / "converted.pcap"
                subprocess.run([args.tshark, "-r", str(args.capture),
                                "-F", "pcap", "-w", str(converted)],
                               capture_output=True, check=True, timeout=120)
        all_packets = list(packets(converted))
        bus, device = select_board(all_packets, args.bus, args.device)
        activity = timeline(analyze(converted, bus, device))
    if args.json:
        print(json.dumps(activity, indent=2, ensure_ascii=False))
    else:
        print("BPCONTROL M1E — OFFLINE MIXED-ACTIVITY TIMELINE")
        print("No USB/HID accessed; no writes performed.")
        print(f"Chorus wet writes: {activity['chorus_wet_writes']}; "
              f"values: {activity['chorus_wet_values']}")
        print(f"Chorus baseline: {activity['chorus_wet_baseline']}; "
              f"out-of-±1 events: {activity['chorus_wet_outliers']}")
        print(f"Chorus restored by readback: "
              f"{activity['chorus_wet_restoration_readback']}")
        print(f"Auto Wah writes: {activity['auto_wah_field_writes']}; "
              f"field0 values: {activity['auto_wah_field0_values']}")
        print(f"Auto Wah original field0: {activity['auto_wah_original_field0']}; "
              f"restoration verified: {activity['auto_wah_restoration_verified']}")
        print("Relevant events:")
        for e in activity["events"]:
            tail = (
                f" value={e['value_raw']}" if e["operation"] == "field_write"
                else f" readback_wet={e['wet_readback']}" if "wet_readback" in e
                else f" readback_field0={e['auto_wah_field0_readback']}"
                if "auto_wah_field0_readback" in e else ""
            )
            print(f"  #{e['packet']:04d} {e['time_s']}s "
                  f"{e['command']} {e['operation']} field={e['field']}"
                  f"{tail} response={e['response_kind']}")
        for issue in activity["issues"]:
            print(f"REVIEW: {issue}")
        print("No BPControl writes are enabled. No recapture is required for this analysis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
