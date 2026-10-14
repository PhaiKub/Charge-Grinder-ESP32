"""Serial protocol v1. Spec: docs/protocol.md. Keep in sync with firmware/src/protocol.h."""

from dataclasses import dataclass
from enum import IntEnum
import struct

VERSION = 1
SYNC_REQ = 0xA5
SYNC_REPLY = 0x5A
MAX_PAYLOAD = 32
WINDOW = 8  # max requests in flight; 8 * 37 bytes fits the device's 256-byte RX buffer
# Default in flight. Measured on the ESP32-S3 with Arduino core 2.0.17: with 2+ in flight
# the board's USB IN endpoints (HID and CDC) stall within a few commands and only a
# replug recovers; with 1 it ran 5000 moves at ~2 ms each. See docs/protocol.md.
DEFAULT_WINDOW = 1
ABS_MAX = 32767


class Cmd(IntEnum):
    HELLO = 0x01
    PING = 0x02
    SET_LED = 0x03
    MOVE_ABS = 0x10
    MOVE_REL = 0x11
    GLIDE_ABS = 0x12
    BUTTON_DOWN = 0x20
    BUTTON_UP = 0x21
    CLICK = 0x22
    SCROLL = 0x23
    KEY_DOWN = 0x30
    KEY_UP = 0x31
    KEY_TAP = 0x32
    RELEASE_ALL = 0x33


class Status(IntEnum):
    OK = 0
    BAD_CRC = 1
    BAD_CMD = 2
    BAD_LEN = 3
    BUSY = 4


def crc8(data: bytes, crc: int = 0) -> int:
    """CRC-8/ATM: poly 0x07, init 0."""
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def encode_request(seq: int, cmd: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"payload too long ({len(payload)} > {MAX_PAYLOAD})")
    body = bytes((seq & 0xFF, cmd, len(payload))) + payload
    return bytes((SYNC_REQ,)) + body + bytes((crc8(body),))


def encode_reply(seq: int, status: int, payload: bytes = b"") -> bytes:
    """Device-side framing; used by tests and the fake device."""
    body = bytes((seq & 0xFF, status, len(payload))) + payload
    return bytes((SYNC_REPLY,)) + body + bytes((crc8(body),))


@dataclass
class Reply:
    seq: int
    status: int
    payload: bytes


class ReplyParser:
    """Incremental parser for device replies. Frames with a bad CRC are skipped."""

    def __init__(self):
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Reply]:
        self._buf += data
        out = []
        while True:
            start = self._buf.find(SYNC_REPLY)
            if start < 0:
                self._buf.clear()
                return out
            del self._buf[:start]
            if len(self._buf) < 5:
                return out
            length = self._buf[3]
            if length > MAX_PAYLOAD:
                del self._buf[0]
                continue
            end = 5 + length
            if len(self._buf) < end:
                return out
            frame = bytes(self._buf[:end])
            if crc8(frame[1:-1]) != frame[-1]:
                del self._buf[0]  # not a real frame start; resync on the next sync byte
                continue
            del self._buf[:end]
            out.append(Reply(seq=frame[1], status=frame[2], payload=frame[4:-1]))


# ── Payload builders ─────────────────────────────────────────────────────────

def p_xy(x: int, y: int) -> bytes:
    return struct.pack("<HH", x, y)


def p_dxdy(dx: int, dy: int) -> bytes:
    return struct.pack("<hh", dx, dy)


def p_glide(x: int, y: int, duration_ms: int) -> bytes:
    return struct.pack("<HHH", x, y, duration_ms)


def p_mask_hold(mask: int, hold_ms: int) -> bytes:
    return struct.pack("<BH", mask, hold_ms)
