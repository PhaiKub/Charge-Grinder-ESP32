"""A Python stand-in for the firmware, speaking protocol v1 over a fake serial link."""

import queue
import struct
import threading

from cg_esp32 import protocol as p


class FakeLink:
    """Implements the slice of serial.Serial that Esp32Device uses."""

    def __init__(self, proto_version=p.VERSION, fw="test", drop_replies=False, corrupt_next=0):
        self.proto_version = proto_version
        self.fw = fw
        self.drop_replies = drop_replies
        self.corrupt_next = corrupt_next  # flip a byte in the next N requests
        self.executed: list[tuple] = []
        self.max_in_flight = 0
        self._rx = queue.Queue()
        self._buf = bytearray()
        self._unanswered = 0
        self._lock = threading.Lock()

    # serial.Serial API
    in_waiting = 0

    def write(self, data: bytes):
        data = bytearray(data)
        if self.corrupt_next:
            self.corrupt_next -= 1
            data[-1] ^= 0xFF
        with self._lock:
            self._unanswered += 1
            self.max_in_flight = max(self.max_in_flight, self._unanswered)
            self._buf += data
            self._process()
        return len(data)

    def read(self, n):
        try:
            return self._rx.get(timeout=0.02)
        except queue.Empty:
            return b""

    def close(self):
        pass

    # device side
    def _reply(self, seq, status, payload=b""):
        self._unanswered -= 1
        if not self.drop_replies:
            self._rx.put(p.encode_reply(seq, status, payload))

    def _process(self):
        while True:
            start = self._buf.find(p.SYNC_REQ)
            if start < 0 or len(self._buf) - start < 5:
                return
            del self._buf[:start]
            seq, cmd, length = self._buf[1], self._buf[2], self._buf[3]
            if len(self._buf) < 5 + length:
                return
            frame = bytes(self._buf[: 5 + length])
            del self._buf[: 5 + length]
            if p.crc8(frame[1:-1]) != frame[-1]:
                self._reply(seq, p.Status.BAD_CRC)
                continue
            self._execute(seq, cmd, frame[4:-1])

    def _execute(self, seq, cmd, payload):
        if cmd == p.Cmd.HELLO:
            return self._reply(seq, p.Status.OK, bytes((self.proto_version,)) + self.fw.encode())
        try:
            name = p.Cmd(cmd).name
        except ValueError:
            return self._reply(seq, p.Status.BAD_CMD)
        fmt = {
            p.Cmd.MOVE_ABS: "<HH", p.Cmd.MOVE_REL: "<hh", p.Cmd.GLIDE_ABS: "<HHH",
            p.Cmd.CLICK: "<BH", p.Cmd.KEY_TAP: "<BH", p.Cmd.SCROLL: "<b",
            p.Cmd.BUTTON_DOWN: "<B", p.Cmd.BUTTON_UP: "<B", p.Cmd.KEY_DOWN: "<B", p.Cmd.KEY_UP: "<B",
        }.get(cmd, "")
        if struct.calcsize(fmt) != len(payload):
            return self._reply(seq, p.Status.BAD_LEN)
        if cmd != p.Cmd.PING:
            self.executed.append((name, *struct.unpack(fmt, payload)))
        self._reply(seq, p.Status.OK)
