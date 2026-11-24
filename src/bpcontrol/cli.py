"""Offline command-line inspector. NO hardware communication."""
import argparse

from .acp import ACPError, decode_frame, decode_readback, encode_read, encode_write, parse_hex
from .effects import EFFECTS, db_from_q15, q15_from_db
from .protocol_effects import PROTOCOL_EFFECTS, decode_protocol_effect


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BPControl offline ACP inspector (no USB I/O)")
    subs = parser.add_subparsers(dest="action", required=True)
    subs.add_parser("effects", help="list mapped effects")
    subs.add_parser("protocol-list", help="list all 45 ACP V2.40.0 protocol effect types (read-only)")
    pdecode = subs.add_parser("protocol-decode", help="decode an ACP readback packet using V2.40.0 schema")
    pdecode.add_argument("type_id", type=int, choices=sorted(PROTOCOL_EFFECTS))
    pdecode.add_argument("hex_packet")
    read = subs.add_parser("read", help="print an ACP read request; do not send")
    read.add_argument("effect", choices=EFFECTS)
    write = subs.add_parser("write", help="print an ACP field write; do not send")
    write.add_argument("effect", choices=EFFECTS)
    write.add_argument("parameter")
    write.add_argument("value", type=int, help="signed 16-bit raw ACP value")
    decode = subs.add_parser("decode", help="decode complete ACP response")
    decode.add_argument("hex_packet")
    convert = subs.add_parser("db2q15")
    convert.add_argument("db", type=float)
    args = parser.parse_args(argv)
    try:
        if args.action == "effects":
            for slug, effect in EFFECTS.items():
                print(f"{slug:22} effect={effect.index:<2} cmd=0x{effect.command:02X} {effect.name}")
        elif args.action == "protocol-list":
            for tid, schema in sorted(PROTOCOL_EFFECTS.items()):
                print(f"type={tid:<2} words={schema.word_count:<2} {schema.type_name:26} ({schema.doc_ref})")
        elif args.action == "protocol-decode":
            raw = parse_hex(args.hex_packet)
            words = decode_readback(raw)
            for item in decode_protocol_effect(args.type_id, words):
                print(f"[{item['index']:2d}] {item['name']:24} = {item['formatted']} (raw={item['raw']})")
        elif args.action == "read":
            print(encode_read(EFFECTS[args.effect].index).hex(" ").upper())
        elif args.action == "write":
            effect = EFFECTS[args.effect]
            param = effect.get_param(args.parameter)
            if not param.writable or param.evidence == "inferred":
                parser.error("read-only or unverified field")
            print(encode_write(effect.index, param.index, args.value).hex(" ").upper())
            print("OFFLINE ONLY — NOT SENT TO HARDWARE")
        elif args.action == "decode":
            raw = parse_hex(args.hex_packet)
            frame = decode_frame(raw)
            print(f"cmd=0x{frame.command:02X}, payload={frame.payload.hex(' ').upper()}")
            print("signed fields:", decode_readback(raw))
        elif args.action == "db2q15":
            gain = q15_from_db(args.db)
            print(f"{args.db:g} dB -> raw={gain} hex=0x{gain:04X}; approx {db_from_q15(gain):.3f} dB")
    except (ACPError, KeyError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
