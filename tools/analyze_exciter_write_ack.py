"""Inspect a passive USBPcap capture of ACPWorkbench Harmonic Exciter (0x9D) writes.

This is OFFLINE evidence analysis. It never opens a USB/HID device,
sends ACP frames, changes DSP settings, or runs ACPWorkbench.

Usage:
  py tools/analyze_exciter_write_ack.py artifacts/usb-capture/exciter-01.pcapng \
      --output artifacts/usb-capture/exciter-01-ack.json

It identifies a unique bus/address from *exact, validated* Exciter (0x9D)
SET_REPORT writes (or reads if --allow-read-only-selection), or you may
explicitly pass both --bus and --device.
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
from tools.analyze_usb_capture import analyze, packets

EXCITER_CMD = 0x9D
EXCITER_WORD_COUNT = 4
EXCITER_FIELDS = {
    0: "enable",
    1: "cutoff",
    2: "dry",
    3: "wet",
}

HID_OUT = {
    "bmRequestType": 0x21, "bRequest": 0x09,
    "wValue": 0x0200, "wIndex": 4, "wLength": 256,
}
HID_IN = {
    "bmRequestType": 0xA1, "bRequest": 0x01,
    "wValue": 0x0100, "wIndex": 4, "wLength": 256,
}


def decode_exciter_write(packet: dict) -> tuple[int, int] | None:
    """Return (field_index, signed_value) only for a byte-exact 256-byte 0x9D write."""
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
    if (len(raw) != 256 or raw[:4] != b"\xA5\x5A\x9D\x03"
            or raw[4] not in EXCITER_FIELDS
            or raw[7] != 0x16 or any(raw[8:])):
        return None
    return raw[4], int.from_bytes(raw[5:7], "little", signed=True)


def classify_invalid_exciter_out(packet: dict) -> str | None:
    """Return a diagnostic reason if an OUT packet targets 0x9D but is malformed."""
    if packet.get("setup") != HID_OUT or packet.get("endpoint") != 0:
        return None
    if packet.get("completion") or packet.get("stage") != 0:
        return None
    try:
        raw = bytes.fromhex(packet.get("payload_hex", ""))
    except (ValueError, TypeError):
        return "invalid_hex_payload"
    if len(raw) < 4 or raw[:3] != b"\xA5\x5A\x9D":
        return None
    if packet.get("truncated"):
        return "truncated_usb_record"
    if len(raw) != 256:
        return f"nonstandard_report_length_{len(raw)}"
    if raw[3] == 0:
        # Candidate read request: valid only if exact A5 5A 9D 00 16 + zeros
        if raw[4] != 0x16 or any(raw[5:]):
            return "malformed_read_request"
        return None
    if raw[3] != 3:
        return f"unexpected_acp_payload_length_{raw[3]}"
    if raw[4] not in EXCITER_FIELDS:
        return f"unsupported_field_index_{raw[4]}"
    if raw[7] != 0x16:
        return "invalid_acp_footer"
    if any(raw[8:]):
        return "nonzero_hid_padding"
    return None


def select_board(records: list[dict], bus: int | None, device: int | None) -> tuple[int, int]:
    if (bus is None) != (device is None):
        raise ValueError("--bus and --device must be provided together")
    candidates = {(p["bus"], p["device"]) for p in records
                  if decode_exciter_write(p) is not None}
    if bus is not None:
        if (bus, device) not in candidates:
            raise ValueError("No matching Exciter write on the specified bus/address")
        return bus, device
    if len(candidates) != 1:
        raise ValueError(
            "Expected exactly ONE device with a validated Exciter (0x9D) write, "
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
    if payload[0] == EXCITER_CMD and not any(payload[1:]):
        return "bare_9d_zero_padded"
    if payload[:2] == b"\xA5\x5A" and len(payload) >= 5:
        end = 5 + payload[3]
        if end <= 256 and payload[end - 1] == 0x16 and not any(payload[end:]):
            return "candidate_full_acp_frame"
    return "unknown"


def exciter_exchanges(result: dict) -> list[dict]:
    """Fail-closed selector for consecutive, successful 0x9D read exchanges."""
    scoped = result["packets"]
    exchanges = []
    expected_query = (b"\xA5\x5A\x9D\x00\x16" + bytes(251)).hex(" ")
    for i in range(len(scoped) - 3):
        a, b, c, d = scoped[i:i + 4]
        if a.get("setup") != HID_OUT or a.get("payload_hex") != expected_query:
            continue
        if c.get("setup") != HID_IN:
            continue
        group = [a, b, c, d]
        if any(p.get("truncated") or p.get("status") or p.get("transfer") != "control"
               for p in group):
            continue
        if [p.get("endpoint") for p in group] != [0, 0, 128, 128]:
            continue
        if [p.get("stage") for p in group] != [0, 3, 0, 3]:
            continue
        if [p.get("completion") for p in group] != [False, True, False, True]:
            continue
        if b.get("payload_length") or c.get("payload_length") or d.get("payload_length") != 256:
            continue
        if a.get("transaction") != b.get("transaction") or c.get("transaction") != d.get("transaction"):
            continue
        if len(d.get("acp", [])) != 1:
            continue
        frame = d["acp"][0]
        if not (frame.get("complete") and frame.get("command") == EXCITER_CMD
                and frame.get("payload_length") == 1 + 2 * EXCITER_WORD_COUNT
                and frame.get("offset") == 0 and frame.get("suffix_all_zero")):
            continue
        raw = bytes.fromhex(frame["hex"])
        if raw[4] != 0xFF:
            continue
        words = [
            int.from_bytes(raw[j:j + 2], "little", signed=True)
            for j in range(5, 5 + 2 * EXCITER_WORD_COUNT, 2)
        ]
        exchanges.append({
            "packets": [p["number"] for p in group],
            "latency_ms": round(1000 * (d["relative_seconds"] - a["relative_seconds"]), 3),
            "response_hex": frame["hex"],
            "raw_values": words,
            "fields": {
                EXCITER_FIELDS[idx]: words[idx]
                for idx in range(EXCITER_WORD_COUNT)
            },
            "readback_validated": True,
        })
    return exchanges


def _classify_unpaired_reason(scoped: list[dict], index: int) -> str:
    a = scoped[index]
    if index + 3 >= len(scoped):
        return "no_matching_ack"
    b, c, d = scoped[index + 1:index + 4]
    if not valid_pair(a, b, 0):
        return "out_of_order_or_interleaved"
    if c.get("setup") != HID_IN:
        return "no_matching_ack" if c.get("setup") == HID_OUT else "out_of_order_or_interleaved"
    if not valid_pair(c, d, 0x80) or d.get("payload_length") != 256:
        return "out_of_order_or_interleaved"
    return "no_matching_ack"


def inspect(result: dict) -> dict:
    scoped = result["packets"]
    writes = []
    unmatched = []
    out_of_order_packets = []
    invalid_packets = []
    other_acp_writes = 0
    previous_write_key: tuple[int, int] | None = None

    for i, a in enumerate(scoped):
        invalid_reason = classify_invalid_exciter_out(a)
        if invalid_reason is not None:
            invalid_packets.append({
                "packet": a["number"],
                "reason": invalid_reason,
            })
            continue

        if a.get("setup") == HID_OUT and not a.get("completion") and a.get("stage") == 0:
            try:
                raw_out = bytes.fromhex(a.get("payload_hex", ""))
            except ValueError:
                raw_out = b""
            if (len(raw_out) == 256 and raw_out[:2] == b"\xA5\x5A"
                    and raw_out[2] != EXCITER_CMD and raw_out[3] > 0):
                other_acp_writes += 1

        decoded = decode_exciter_write(a)
        if decoded is None:
            continue

        field_index, value = decoded
        field_name = EXCITER_FIELDS[field_index]
        raw = bytes.fromhex(a["payload_hex"])
        is_duplicate = previous_write_key == (field_index, value)
        previous_write_key = (field_index, value)

        item = {
            "command": "0x9D",
            "field_index": field_index,
            "field_name": field_name,
            "value": value,
            "is_duplicate": is_duplicate,
            "acp_write_hex": raw[:8].hex(" ").upper(),
            "set_report_packet": a["number"],
            "set_report_size": len(raw),
            "set_report_setup": HID_OUT,
            "set_time_s": a.get("relative_seconds"),
            "ack_classification": "no_matching_ack",
        }

        if i + 3 >= len(scoped):
            unmatched.append(a["number"])
            writes.append(item)
            continue

        b, c, d = scoped[i + 1:i + 4]
        if not (
            valid_pair(a, b, 0)
            and c.get("setup") == HID_IN
            and valid_pair(c, d, 0x80)
            and b.get("payload_length") == 0
            and c.get("payload_length") == 0
            and d.get("payload_length") == 256
        ):
            reason = _classify_unpaired_reason(scoped, i)
            item["ack_classification"] = reason
            unmatched.append(a["number"])
            if reason == "out_of_order_or_interleaved":
                out_of_order_packets.append(a["number"])
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

    reads = exciter_exchanges(result)

    # Associate each write with the first readback occurring after it and before the next write.
    for idx, w in enumerate(writes):
        w_end = w.get("get_report_completion_packet", w["set_report_packet"])
        next_start = writes[idx + 1]["set_report_packet"] if idx + 1 < len(writes) else float("inf")
        following = [
            r for r in reads
            if r["packets"][0] > w_end and r["packets"][-1] < next_start
        ]
        if following:
            rb = following[0]
            rb_val = rb["fields"][w["field_name"]]
            w["post_write_readback_packets"] = rb["packets"]
            w["post_write_readback_value"] = rb_val
            w["readback_matches_written_value"] = (rb_val == w["value"])
        else:
            w["post_write_readback_packets"] = None
            w["post_write_readback_value"] = None
            w["readback_matches_written_value"] = None

    acknowledgement_count = sum(
        w["ack_classification"] == "bare_9d_zero_padded" for w in writes
    )
    duplicate_count = sum(w["is_duplicate"] for w in writes)

    baseline_reads = [
        r for r in reads if writes and r["packets"][-1] < writes[0]["set_report_packet"]
    ]
    baseline_fields = baseline_reads[-1]["fields"] if baseline_reads else None

    last_write_end = (
        writes[-1].get("get_report_completion_packet", writes[-1]["set_report_packet"])
        if writes else -1
    )
    subsequent_reads = [r for r in reads if r["packets"][0] > last_write_end]
    final_read_fields = subsequent_reads[-1]["fields"] if subsequent_reads else None

    per_field = {}
    all_written_fields_match_baseline = True if (baseline_fields and writes) else None
    for field_index, field_name in EXCITER_FIELDS.items():
        fw = [w for w in writes if w["field_index"] == field_index]
        base_val = baseline_fields[field_name] if baseline_fields is not None else None
        final_write_matches = (
            None if (base_val is None or not fw)
            else fw[-1]["value"] == base_val
        )
        if fw and final_write_matches is False:
            all_written_fields_match_baseline = False
        post_val = final_read_fields[field_name] if (final_read_fields is not None and fw) else None
        confirmed = bool(
            fw
            and base_val is not None
            and final_write_matches is True
            and post_val is not None
            and post_val == base_val
        )
        per_field[field_name] = {
            "field_index": field_index,
            "write_count": len(fw),
            "recognized_bare_ack_count": sum(
                w["ack_classification"] == "bare_9d_zero_padded" for w in fw
            ),
            "duplicate_write_count": sum(w["is_duplicate"] for w in fw),
            "written_values": [w["value"] for w in fw],
            "baseline_from_prewrite_readback": base_val,
            "final_write_matches_baseline": final_write_matches,
            "post_restore_readback_value": post_val,
            "post_restore_readback_confirmed": confirmed,
        }

    if not writes:
        restoration_status = "no_writes"
        restore_readback = False
    elif baseline_fields is None:
        restoration_status = "missing_prewrite_baseline"
        restore_readback = False
    elif not subsequent_reads:
        restoration_status = "missing_post_restore_readback"
        restore_readback = False
    elif all_written_fields_match_baseline is False:
        restoration_status = "final_write_mismatch"
        restore_readback = False
    elif final_read_fields != baseline_fields:
        restoration_status = "readback_mismatch"
        restore_readback = False
    else:
        restoration_status = "confirmed"
        restore_readback = True

    return {
        "format": "bpcontrol-exciter-write-ack-evidence-v1",
        "command": "0x9D",
        "passive_only": True,
        "write_count": len(writes),
        "recognized_bare_ack_count": acknowledgement_count,
        "duplicate_write_count": duplicate_count,
        "unpaired_set_report_packets": unmatched,
        "out_of_order_packets": out_of_order_packets,
        "invalid_packets": invalid_packets,
        "other_acp_writes": other_acp_writes,
        "writes": writes,
        "exciter_readbacks": reads,
        "per_field": per_field,
        "baseline_from_prewrite_readback": baseline_fields,
        "final_writes_match_prewrite_baseline": all_written_fields_match_baseline,
        "post_restore_readback_confirmed": restore_readback,
        "restoration_status": restoration_status,
        "limitations": [
            "USBPcap records are Windows URBs, not individual physical USB packets.",
            "A bare padded 0x9D may be an ACP application ACK; shape alone does not prove parameter change.",
            "The original state must come from a PRE-write full Exciter readback, not the first write.",
            "A final write matching the baseline is NOT proof of actual device restoration.",
            "Post-restore readback is only confirmed if a later full Exciter read matches all baseline fields.",
            "Data is scoped by bus/address and ACP command, not a capture of the USB descriptor.",
            "Never use this diagnostic JSON to authorize firmware saves or live Exciter writes without review.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="local USBPcap .pcap or .pcapng")
    parser.add_argument("--bus", type=int)
    parser.add_argument("--device", type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--tshark",
        default=shutil.which("tshark") or r"C:\Program Files\Wireshark\tshark.exe",
    )
    args = parser.parse_args()
    if args.capture.resolve() == args.output.resolve():
        parser.error("Output must differ from capture")
    if args.output.exists():
        parser.error("Output already exists; use a new output filename")
    if (args.bus is None) != (args.device is None):
        parser.error("--bus and --device must be passed together")

    with tempfile.TemporaryDirectory(prefix="bpcontrol-exciter-ack-") as temporary:
        data = args.capture
        with data.open("rb") as f:
            magic = f.read(4)
        if magic == b"\x0a\x0d\x0d\x0a":
            data = Path(temporary) / "capture.pcap"
            subprocess.run(
                [args.tshark, "-r", str(args.capture), "-F", "pcap", "-w", str(data)],
                check=True, capture_output=True, timeout=120,
            )
        seen = list(packets(data))
        bus, device = select_board(seen, args.bus, args.device)
        findings = inspect(analyze(data, bus, device))

    findings["device_filter"] = {
        "bus": bus,
        "address": device,
        "selection": "unique validated Exciter (0x9D) SET_REPORT candidate",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(findings, out, indent=2, ensure_ascii=False)
        out.write("\n")

    print("BPCONTROL M1K-A — PASSIVE EXCITER (0x9D) WRITE ACK INSPECTION (NO USB)")
    print(f"Found: {findings['write_count']} Exciter writes ({findings['duplicate_write_count']} duplicates)")
    print(f"Bare padded 0x9D candidate ACKs: {findings['recognized_bare_ack_count']}")
    print(f"Invalid 0x9D packets: {len(findings['invalid_packets'])}")
    print(f"Unpaired / out-of-order packets: {len(findings['unpaired_set_report_packets'])}")
    for entry in findings["writes"]:
        print(
            f"  SET packet {entry['set_report_packet']}: {entry['field_name']}={entry['value']} "
            f"ACK={entry['ack_classification']}, "
            f"readback={entry['post_write_readback_value']}"
        )
    print(f"Pre-write baseline: {findings['baseline_from_prewrite_readback']}")
    print(f"Restoration status: {findings['restoration_status']} (confirmed={findings['post_restore_readback_confirmed']})")
    print(f"Report saved locally: {args.output}")
    print("No BPControl writes performed. Review ACK/readback evidence before any live control.")
    return 0 if findings["write_count"] >= 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
