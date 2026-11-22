"""ACP application-layer framing observed in ACPWorkbench traces.

Frames: A5 5A CMD LEN PAYLOAD 16. Single-byte ACK is NOT a frame.
No USB/HID transport or board I/O is implemented here.
"""
from dataclasses import dataclass

HEADER = b"\xA5\x5A"
FOOTER = 0x16


class ACPError(ValueError):
    pass


@dataclass(frozen=True)
class ACPFrame:
    command: int
    payload: bytes

    def to_bytes(self) -> bytes:
        if not 0 <= self.command <= 255:
            raise ACPError("command must fit u8")
        if len(self.payload) > 255:
            raise ACPError("payload length must fit u8")
        return HEADER + bytes((self.command, len(self.payload))) + self.payload + bytes((FOOTER,))


def decode_frame(raw: bytes) -> ACPFrame:
    if len(raw) < 5 or raw[:2] != HEADER or raw[-1] != FOOTER:
        raise ACPError("invalid ACP framing")
    if len(raw) != 5 + raw[3]:
        raise ACPError("payload length mismatch")
    return ACPFrame(raw[2], bytes(raw[4:-1]))


def effect_command(effect_index: int) -> int:
    """Effect index mappings validated only for the observed firmware."""
    if not 1 <= effect_index <= 59:
        raise ACPError("effect index outside observed catalog range")
    return 0x80 + effect_index


def encode_read(effect_index: int) -> bytes:
    return ACPFrame(effect_command(effect_index), b"").to_bytes()


def encode_write(effect_index: int, field_index: int, value: int) -> bytes:
    if not 0 <= field_index <= 255:
        raise ACPError("field index must fit u8")
    if not -32768 <= value <= 32767:
        raise ACPError("value must fit signed 16-bit; do not truncate")
    payload = bytes((field_index,)) + value.to_bytes(2, "little", signed=True)
    return ACPFrame(effect_command(effect_index), payload).to_bytes()


def decode_readback(raw: bytes, expected_effect_index: int | None = None) -> list[int]:
    frame = decode_frame(raw)
    if expected_effect_index is not None and frame.command != effect_command(expected_effect_index):
        raise ACPError("unexpected effect command")
    if not frame.payload or frame.payload[0] != 0xFF:
        raise ACPError("readback must start with FF marker")
    values = frame.payload[1:]
    if len(values) % 2:
        raise ACPError("readback has odd byte count")
    return [int.from_bytes(values[i:i + 2], "little", signed=True)
            for i in range(0, len(values), 2)]


def is_ack(data: bytes, effect_index: int) -> bool:
    return data == bytes((effect_command(effect_index),))


def parse_hex(text: str) -> bytes:
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise ACPError(f"invalid hex: {exc}") from exc
