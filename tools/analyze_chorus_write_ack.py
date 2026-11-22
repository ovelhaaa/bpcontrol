"""Inspect a passive USBPcap capture of ACPWorkbench Guitar Chorus wet writes.

This is OFFLINE evidence analysis. It never opens a USB/HID device,
sends ACP frames, changes DSP settings, or runs ACPWorkbench.

Usage:
  py tools/analyze_chorus_write_ack.py artifacts/usb-capture/wet-01.pcapng \
      --output artifacts/usb-capture/wet-01-ack.json

It identifies a unique bus/address from *exact, validated* Chorus wet
SET_REPORTs, or you may explicitly pass both --bus and --device.
Reports include only relevant packet numbers, values, ACK shapes and
Chorus readbacks; the full capture is kept private/local.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.analyze_usb_capture import analyze, chorus_exchanges, packets

HID_OUT = {
    "bmRequestType": 0x21, "bRequest": 0x09,
    "wValue": 0x0200, "wIndex": 4, "wLength": 256,
}
HID_IN = {
    "bmRequestType": 0xA1, "bRequest": 0x01,
    "wValue": 0x0100, "wIndex": 4, "wLength": 256,
}


def decode_wet_write(packet: dict) -> int | None:
    """Return the proposed raw wet value only for a byte-exact 256-byte report."""
    if packet.get("setup") != HID_OUT or packet.get("endpoint") != 0:
        return None
    if packet.get("completion") or packet.get("stage") != 0:
        return None
    if packet.get("truncated") or packet.get("transfer") != "control":
        return None
    try:
        raw = bytes.fromhex(packet["payload_hex"])
    except (ValueError, KeyError, TypeError):
        return None
    if (len(raw) != 256 or raw[:5] != b"\xA5\x5A\x8F\x03\x06"
            or raw[7] != 0x16 or any(raw[8:])):
        return None
    return int.from_bytes(raw[5:7], "little", signed=True)


def select_board(records: list[dict], bus: int | None, device: int | None) -> tuple[int, int]:
    if (bus is None) != (device is None):
        raise ValueError("--bus and --device must be provided together")
    candidates = {(p["bus"], p["device"]) for p in records
                  if decode_wet_write(p) is not None}
    if bus is not None:
        if (bus, device) not in candidates:
            raise ValueError("No matching Chorus wet write on the specified bus/address")
        return bus, device
    if len(candidates) != 1:
        raise ValueError(
            "Expected exactly ONE device with a validated Chorus wet write, "
            f"found {len(candidates)}; verify capture and/or specify --bus/--device"
        )
    return next(iter(candidates))


def valid_pair(a: dict, b: dict, endpoint: int) -> bool:
    return (
        a.get("transfer") == b.get("transfer") == "control"
        and a.get("endpoint") == b.get("endpoint") == endpoint
        and a.get("stage") == 0
        and b.get("stage") == 3
        and a.get("completion") is False
        and b.get("completion") is True
        and a.get("transaction") == b.get("transaction")
        and a.get("status") == b.get("status") == 0
        and not a.get("truncated") and not b.get("truncated")
    )


def ack_shape(payload: bytes) -> str:
    if len(payload) != 256:
        return "nonstandard_report_length"
    if payload[0] == 0x8F and not any(payload[1:]):
        return "bare_8f_zero_padded"
    if payload[:2] == b"\xA5\x5A" and len(payload) >= 5:
        end = 5 + payload[3]
        if end <= 256 and payload[end-1] == 0x16 and not any(payload[end:]):
            return "candidate_full_acp_frame"
    return "unknown"


def inspect(result: dict) -> dict:
    scoped = result["packets"]
    writes = []
    unmatched = []
    other_chorus_writes = 0

    for i, a in enumerate(scoped):
        if a.get("setup") != HID_OUT:
            continue
        try:
            raw = bytes.fromhex(a.get("payload_hex", ""))
        except ValueError:
            continue
        if (len(raw) == 256 and raw[:4] == b"\xA5\x5A\x8F\x03"
                and raw[7] == 0x16 and not any(raw[8:])
                and raw[4] != 6):
            other_chorus_writes += 1

        wet = decode_wet_write(a)
        if wet is None:
            continue

        item = {
            "command": "0x8F",
            "field_index": 6,
            "value": wet,
            "acp_write_hex": raw[:8].hex(" ").upper(),
            "set_report_packet": a["number"],
            "set_report_size": len(raw),
            "set_report_setup": HID_OUT,
            "set_time_s": a.get("relative_seconds"),
            "ack_classification": "no_matching_ack",
        }
        # Require a consecutive successful SET submit/complete then
        # GET submit/complete. Do not fabricate an ACK if interleaved.
        if i + 3 >= len(scoped):
            unmatched.append(a["number"])
            writes.append(item)
            continue
        b, c, d = scoped[i+1:i+4]
        if not (
            valid_pair(a, b, 0)
            and c.get("setup") == HID_IN
            and valid_pair(c, d, 0x80)
            and b.get("payload_length") == 0
            and c.get("payload_length") == 0
            and d.get("payload_length") == 256
        ):
            unmatched.append(a["number"])
            writes.append(item)
            continue

        data = bytes.fromhex(d["payload_hex"])
        item.update({
            "set_report_completion_packet": b["number"],
            "get_report_setup_packet": c["number"],
            "get_report_completion_packet": d["number"],
            "get_report_setup": HID_IN,
            "get_report_size": len(data),
            "ack_classification": ack_shape(data),
            "ack_first_32_hex": data[:32].hex(" ").upper(),
            "ack_zero_after_first": not any(data[1:]),
            "latency_ms": round(
                (d["relative_seconds"] - a["relative_seconds"]) * 1000, 3
            ),
        })
        writes.append(item)

    reads = [
        {
            "packets": e["packets"],
            "wet": e["raw_values"][6],
            "chorus_raw_values": e["raw_values"],
            "readback_validated": True,
        }
        for e in chorus_exchanges(result)
    ]
    acknowledgement_count = sum(
        w["ack_classification"] == "bare_8f_zero_padded" for w in writes
    )
    restored_values = (
        len(writes) >= 2 and writes[-1]["value"] == writes[0]["value"]
    )
    last_write_end = (
        writes[-1].get("get_report_completion_packet", writes[-1]["set_report_packet"])
        if writes else -1
    )
    subsequent_reads = [r for r in reads if r["packets"][0] > last_write_end]
    restore_readback = (
        bool(restored_values and subsequent_reads
             and subsequent_reads[-1]["wet"] == writes[-1]["value"])
    )
    return {
        "format": "bpcontrol-chorus-write-ack-evidence-v1",
        "passive_only": True,
        "write_count": len(writes),
        "recognized_bare_ack_count": acknowledgement_count,
        "unpaired_set_report_packets": unmatched,
        "other_chorus_field_writes": other_chorus_writes,
        "writes": writes,
        "chorus_readbacks": reads,
        "first_last_write_value_equal": bool(restored_values),
        "post_restore_readback_confirmed": restore_readback,
        "limitations": [
            "USBPcap records are Windows URBs, not individual physical USB packets.",
            "A bare padded 0x8F may be an ACP application ACK; shape alone does not prove parameter change.",
            "First/last write values matching is NOT proof of actual device restoration.",
            "Post-restore readback is only confirmed if a later full Chorus read was captured.",
            "Data is scoped by bus/address and ACP command, not a capture of the USB descriptor.",
            "Never use this diagnostic JSON to authorize firmware saves or automatic writes.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="local USBPcap .pcap or .pcapng")
    parser.add_argument("--bus", type=int)
    parser.add_argument("--device", type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tshark", default=shutil.which("tshark") or
                        r"C:\Program Files\Wireshark\tshark.exe")
    args = parser.parse_args()
    if args.capture.resolve() == args.output.resolve():
        parser.error("Output must differ from capture")
    if args.output.exists():
        parser.error("Output already exists; use a new output filename")
    if (args.bus is None) != (args.device is None):
        parser.error("--bus and --device must be passed together")

    with tempfile.TemporaryDirectory(prefix="bpcontrol-ack-") as temporary:
        data = args.capture
        with data.open("rb") as f:
            magic = f.read(4)
        if magic == b"\x0a\x0d\x0d\x0a":
            data = Path(temporary) / "capture.pcap"
            subprocess.run(
                [args.tshark, "-r", str(args.capture), "-F", "pcap",
                 "-w", str(data)],
                check=True, capture_output=True, timeout=120,
            )
        seen = list(packets(data))
        bus, device = select_board(seen, args.bus, args.device)
        findings = inspect(analyze(data, bus, device))
    findings["device_filter"] = {
        "bus": bus, "address": device,
        "selection": "unique validated Chorus wet SET_REPORT candidate",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(findings, out, indent=2, ensure_ascii=False)
        out.write("\n")
    print("BPCONTROL M1E — PASSIVE CHORUS WRITE ACK INSPECTION (NO USB)")
    print(f"Found: {findings['write_count']} Chorus wet writes")
    print(f"Bare padded 0x8F candidate ACKs: {findings['recognized_bare_ack_count']}")
    print(f"Other Chorus-field writes: {findings['other_chorus_field_writes']}")
    for entry in findings["writes"]:
        print(
            f"  SET packet {entry['set_report_packet']}: wet={entry['value']} "
            f"ACK={entry['ack_classification']}, "
            f"GET packet={entry.get('get_report_completion_packet', 'unpaired')}"
        )
    print(f"Initial/final write values equal: {findings['first_last_write_value_equal']}")
    print(f"Restoration readback in capture: {findings['post_restore_readback_confirmed']}")
    print(f"Report saved locally: {args.output}")
    print("No BPControl writes performed. ACK evidence must be reviewed before live control.")
    return 0 if findings["write_count"] >= 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
