"""Offline USBPcap ACP inspector. Never opens a USB/HID device.

PCAPNG is converted locally by TShark. Output contains device-scoped payloads;
it is LOCAL evidence, not automatically safe for publication.
USBPcap layout: github.com/desowin/usbpcap/blob/master/USBPcapDriver/include/USBPcap.h
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

USB = struct.Struct('<HQIHBHHBBI')
TRANSFERS = {0: 'isochronous', 1: 'interrupt', 2: 'control', 3: 'bulk'}


def frames(data):
    """Find complete ACP candidates; preserve offset, reject invalid length/footer."""
    result = []
    for offset in range(max(0, len(data) - 1)):
        if data[offset:offset + 2] != b'\xa5\x5a':
            continue
        if offset + 4 > len(data):
            result.append({'offset': offset, 'complete': False})
            continue
        end = offset + 5 + data[offset + 3]
        valid = end <= len(data) and data[end - 1] == 0x16
        item = {'offset': offset, 'command': data[offset + 2],
                'payload_length': data[offset + 3], 'complete': valid}
        if valid:
            item.update(hex=data[offset:end].hex(' '),
                        prefix_hex=data[:offset].hex(' '),
                        suffix_length=len(data) - end,
                        suffix_all_zero=all(x == 0 for x in data[end:]))
        result.append(item)
    return result


def packets(path):
    with path.open('rb') as stream:
        header = stream.read(24)
        formats = {b'\xd4\xc3\xb2\xa1': ('<', 1e6), b'\xa1\xb2\xc3\xd4': ('>', 1e6),
                   b'\x4d\x3c\xb2\xa1': ('<', 1e9), b'\xa1\xb2\x3c\x4d': ('>', 1e9)}
        if len(header) != 24 or header[:4] not in formats:
            raise ValueError('Expected classic PCAP (convert PCAPNG with TShark)')
        endian, scale = formats[header[:4]]
        if struct.unpack(endian + 'I', header[20:24])[0] & 0xffff != 249:
            raise ValueError('Expected LINKTYPE_USBPCAP=249')
        index = 0
        while raw_header := stream.read(16):
            if len(raw_header) != 16:
                raise ValueError('Truncated PCAP record header')
            sec, frac, captured, original = struct.unpack(endian + 'IIII', raw_header)
            if captured > 16 * 1024 * 1024:
                raise ValueError('Unreasonable record size')
            raw = stream.read(captured)
            if len(raw) != captured or len(raw) < USB.size:
                raise ValueError('Truncated USBPcap record')
            index += 1
            hlen, irp, status, function, info, bus, device, ep, transfer, length = USB.unpack_from(raw)
            if hlen < USB.size or hlen > len(raw):
                raise ValueError('Invalid USBPcap header length')
            payload = raw[hlen:hlen + length]
            stage = raw[27] if transfer == 2 and hlen >= 28 else None
            setup = None
            if transfer == 2 and stage == 0 and len(payload) >= 8:
                bm, request, value, interface, wanted = struct.unpack('<BBHHH', payload[:8])
                setup = dict(bmRequestType=bm, bRequest=request, wValue=value,
                             wIndex=interface, wLength=wanted)
                payload = payload[8:]
            yield dict(number=index, timestamp=sec + frac / scale, bus=bus, device=device,
                       endpoint=ep, direction='IN' if ep & 0x80 else 'OUT',
                       transfer=TRANSFERS.get(transfer, f'unknown:{transfer}'),
                       irp=irp, completion=bool(info & 1), status=status, stage=stage,
                       captured_length=captured, original_length=original,
                       usb_data_length=length, payload_length=len(payload),
                       truncated=captured < original or len(raw) - hlen < length,
                       setup=setup, payload_hex=payload.hex(' '), acp=frames(payload))


def analyze(path, bus, device):
    selected = [p for p in packets(path) if p['bus'] == bus and p['device'] == device]
    origin = selected[0]['timestamp'] if selected else 0
    irps = {}
    next_transaction = 0
    for packet in selected:
        packet['relative_seconds'] = round(packet.pop('timestamp') - origin, 6)
        irp = packet.pop('irp')
        key = (irp, packet['endpoint'])
        if not packet['completion'] or key not in irps:
            next_transaction += 1
            irps[key] = next_transaction
        packet['transaction'] = irps[key]
        if packet['completion']:
            irps.pop(key, None)  # Windows can reuse the same IRP for later URBs.
    # Only temporal candidates; ACP has no proven sequence number here.
    queries = []
    associations = []
    for p in selected:
        for f in p['acp']:
            if not f.get('complete'):
                continue
            if p['direction'] == 'OUT' and f['payload_length'] == 0:
                queries.append((p, f))
            elif p['direction'] == 'IN':
                matches = [(q, a) for q, a in queries
                           if a['command'] == f['command'] and
                           0 <= p['relative_seconds'] - q['relative_seconds'] <= 2]
                associations.append(dict(response=p['number'], command=f['command'],
                                         candidate_requests=[q['number'] for q, _ in matches],
                                         certainty='temporal hypothesis only'))
    return dict(bus=bus, device=device, packet_count=len(selected),
                summary=dict(Counter(f"{p['transfer']} ep=0x{p['endpoint']:02x} {p['direction']} payload={p['payload_length']}"
                                     for p in selected)),
                packets=selected, associations=associations,
                limitations=['URB records are not physical USB bus packets.',
                             'Report IDs require descriptor or SET_REPORT evidence.',
                             'No automatic cross-URB reassembly; incomplete candidates remain explicit.',
                             'Device-scoped payloads may include audio or serials; keep local.'])


def chorus_exchanges(result):
    """Fail-closed selector for consecutive, successful Chorus read exchanges."""
    packets = result['packets']
    exchanges = []
    for i in range(len(packets) - 3):
        a, b, c, d = packets[i:i + 4]
        if a['setup'] != dict(bmRequestType=0x21, bRequest=9, wValue=0x0200,
                              wIndex=4, wLength=256):
            continue
        if a['payload_hex'] != (b'\xa5\x5a\x8f\x00\x16' + bytes(251)).hex(' '):
            continue
        if c['setup'] != dict(bmRequestType=0xa1, bRequest=1, wValue=0x0100,
                              wIndex=4, wLength=256):
            continue
        group = [a, b, c, d]
        if any(p['truncated'] or p['status'] or p['transfer'] != 'control' for p in group):
            continue
        if [p['endpoint'] for p in group] != [0, 0, 128, 128]:
            continue
        if [p['stage'] for p in group] != [0, 3, 0, 3]:
            continue
        if [p['completion'] for p in group] != [False, True, False, True]:
            continue
        if b['payload_length'] or c['payload_length'] or d['payload_length'] != 256:
            continue
        if a['transaction'] != b['transaction'] or c['transaction'] != d['transaction']:
            continue
        if len(d['acp']) != 1:
            continue
        frame = d['acp'][0]
        if not (frame.get('complete') and frame.get('command') == 0x8f and
                frame.get('payload_length') == 15 and frame['offset'] == 0 and
                frame.get('suffix_all_zero')):
            continue
        raw = bytes.fromhex(frame['hex'])
        if raw[4] != 0xff:
            continue
        exchanges.append(dict(packets=[p['number'] for p in group],
                              latency_ms=round(1000 * (d['relative_seconds'] - a['relative_seconds']), 3),
                              response_hex=frame['hex'],
                              raw_values=[int.from_bytes(raw[j:j + 2], 'little', signed=True)
                                          for j in range(5, 19, 2)],
                              association='consecutive SET_REPORT/GET_REPORT; matching ACP command'))
    return exchanges


def write_sanitized_chorus(path, result):
    """Export only validated Chorus read exchanges, stripping host identifiers.

    Rebuild minimal classic PCAP: no PCAPNG comments, paths or OS metadata;
    synthetic epoch, bus/device=1, sequential URB tokens. Preserve report bytes.
    """
    exchanges = chorus_exchanges(result)
    if not exchanges:
        raise ValueError('No complete validated Chorus read exchanges; export refused')
    numbers = {n for exchange in exchanges for n in exchange['packets']}
    selected = [p for p in result['packets'] if p['number'] in numbers]
    origin = selected[0]['relative_seconds']
    tokens = {}
    with path.open('xb') as output:
        output.write(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 249))
        for p in selected:
            token = tokens.setdefault(p['transaction'], len(tokens) + 1)
            payload = bytes.fromhex(p['payload_hex'])
            setup = p['setup']
            if setup:
                payload = struct.pack('<BBHHH', *(setup[k] for k in
                                      ('bmRequestType', 'bRequest', 'wValue', 'wIndex', 'wLength'))) + payload
            raw = USB.pack(28, token, p['status'], 8 if p['completion'] else 0x1b,
                           int(p['completion']), 1, 1, p['endpoint'], 2, len(payload))
            raw += bytes([p['stage']]) + payload
            micros = round((p['relative_seconds'] - origin) * 1_000_000)
            sec, usec = divmod(micros, 1_000_000)
            output.write(struct.pack('<IIII', 1 + sec, usec, len(raw), len(raw)))
            output.write(raw)
    return dict(original_packet_numbers=[p['number'] for p in selected],
                sanitized_packet_numbers=list(range(1, len(selected) + 1)),
                sanitized_bus=1, sanitized_device=1,
                removed=['absolute timestamps', 'IRP kernel addresses', 'host metadata',
                         'all non-Chorus exchanges'], exchanges=exchanges)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--bus', required=True, type=int)
    parser.add_argument('--device', required=True, type=int)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--sanitized-pcap', type=Path,
                        help='New local PCAP containing only validated Chorus read exchanges')
    parser.add_argument('--tshark', default=shutil.which('tshark') or r'C:\Program Files\Wireshark\tshark.exe')
    args = parser.parse_args()
    if args.capture.resolve() == args.output.resolve():
        parser.error('Output must differ from input')
    if args.sanitized_pcap and args.sanitized_pcap.resolve() in (args.capture.resolve(), args.output.resolve()):
        parser.error('Sanitized PCAP must differ from input and JSON output')
    with tempfile.TemporaryDirectory(prefix='bpcontrol-usb-') as temporary:
        path = args.capture
        with path.open('rb') as stream:
            magic = stream.read(4)
        if magic == b'\x0a\x0d\x0d\x0a':
            path = Path(temporary) / 'converted.pcap'
            # Preserve source frame numbers; filtering happens inside analyze().
            subprocess.run([args.tshark, '-r', str(args.capture), '-F', 'pcap',
                            '-w', str(path)], check=True, capture_output=True, timeout=120)
        result = analyze(path, args.bus, args.device)
    result['chorus_exchanges'] = chorus_exchanges(result)
    if args.sanitized_pcap:
        result['sanitization'] = write_sanitized_chorus(args.sanitized_pcap, result)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f"{result['packet_count']} device-scoped records; local JSON written")


if __name__ == '__main__':
    main()
