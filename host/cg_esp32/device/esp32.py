"""ESP32 (S3/S2) InputDevice over the v1 binary serial protocol (docs/protocol.md).

A reader thread matches replies by seq. By default only one request is in
flight (protocol.DEFAULT_WINDOW); a bigger window pipelines requests but
currently stalls the board's USB, see docs/protocol.md.
"""

import logging
import sys
import threading
import time

import serial
import serial.tools.list_ports

from .. import protocol as p
from ..keys import button_mask, key_code
from .base import DeviceError, DeviceLost, DeviceRejected, InputDevice

log = logging.getLogger(__name__)

ESPRESSIF_VID = 0x303A
PRODUCT_NAME = "Charge-Grinder-ESP32"
BAUD = 115200
REPLY_TIMEOUT = 2.0  # seconds, on top of any hold/glide time the command asked for


def find_port() -> str | None:
    """Our board first (product string), then any Espressif native-USB port."""
    ports = list(serial.tools.list_ports.comports())
    for info in ports:
        if info.vid == ESPRESSIF_VID and PRODUCT_NAME in (info.product or ""):
            return info.device
    for info in ports:
        if info.vid == ESPRESSIF_VID:
            return info.device
    return None


def primary_screen_size() -> tuple[int, int]:
    if sys.platform != "win32":
        raise DeviceError("screen size must be given explicitly off Windows")
    import ctypes
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


class _Pending:
    __slots__ = ("cmd", "deadline", "event", "reply")

    def __init__(self, cmd, deadline):
        self.cmd = cmd
        self.deadline = deadline
        self.event = threading.Event()
        self.reply = None


class Esp32Device(InputDevice):
    def __init__(self, port: str | None = None, screen_size=None, *, link=None, window: int = p.DEFAULT_WINDOW):
        """`link` replaces the serial port (tests pass a fake one).

        `window` is how many requests may be in flight (1 = wait for each reply).
        """
        super().__init__(screen_size or primary_screen_size())
        if link is None:
            port = port or find_port()
            if port is None:
                raise DeviceLost("board not found. Plug in its native USB port.")
            try:
                link = serial.Serial(port, BAUD, timeout=0.05, write_timeout=1.0)
            except (serial.SerialException, OSError) as exc:
                raise DeviceLost(f"cannot open {port}: {exc}") from exc
        self.port = port
        self._link = link
        self._window = max(1, min(int(window), p.WINDOW))
        self._parser = p.ReplyParser()
        self._seq = 0
        self._pending: dict[int, _Pending] = {}
        self._cond = threading.Condition()
        self._error: DeviceError | None = None
        self._closed = False
        self._replies = 0
        self._reader = threading.Thread(target=self._read_loop, name="esp32-reader", daemon=True)
        self._reader.start()
        try:
            text = self.hello()
        except Exception:
            self._closed = True
            self._reader.join(timeout=1.0)
            self._link.close()
            raise
        # "<version> <board>" since firmware 0.2.0; older firmware sends only the version.
        version, _, board = text.partition(" ")
        self.firmware_version = version
        self.firmware_board = board or None

    # ── Link ─────────────────────────────────────────────────────────────────

    def _read_loop(self):
        while not self._closed:
            try:
                # Read what's already buffered, or block for the first byte. A fixed
                # read(64) would sit out the whole port timeout on every 5-byte reply.
                data = self._link.read(max(1, self._link.in_waiting))
            except Exception as exc:  # port vanished (unplugged)
                self._fail(DeviceLost(f"serial link lost: {exc}"))
                return
            if not data:
                continue
            for reply in self._parser.feed(data):
                self._replies += 1
                with self._cond:
                    pending = self._pending.pop(reply.seq, None)
                    if pending is None:
                        log.debug("reply for unknown seq %d", reply.seq)
                        continue
                    pending.reply = reply
                    if reply.status != p.Status.OK and self._error is None:
                        self._error = DeviceRejected(
                            f"device rejected {p.Cmd(pending.cmd).name}: {p.Status(reply.status).name}")
                    self._cond.notify_all()
                pending.event.set()

    def _fail(self, err: DeviceError):
        with self._cond:
            if self._error is None:
                self._error = err
            for pending in self._pending.values():
                pending.event.set()
            self._pending.clear()
            self._cond.notify_all()

    def _raise_if_failed(self):
        if self._error is not None:
            err, self._error = self._error, None
            raise err

    def _expire(self):
        """Called with the lock held: fail if any request is overdue."""
        now = time.monotonic()
        for seq, pending in self._pending.items():
            if now > pending.deadline:
                raise DeviceLost(
                    f"no reply to {p.Cmd(pending.cmd).name} (seq {seq}, {len(self._pending)} in flight, "
                    f"{self._replies} replies so far); device stopped responding")

    def _send(self, cmd: p.Cmd, payload: bytes = b"", *, extra_ms: int = 0, wait: bool = False):
        with self._cond:
            while True:
                self._raise_if_failed()
                self._expire()
                if len(self._pending) < self._window:
                    break
                self._cond.wait(0.05)
            seq = self._seq
            self._seq = (self._seq + 1) & 0xFF
            pending = _Pending(cmd, time.monotonic() + REPLY_TIMEOUT + extra_ms / 1000)
            self._pending[seq] = pending
            try:
                self._link.write(p.encode_request(seq, cmd, payload))
            except Exception as exc:
                self._pending.pop(seq, None)
                raise DeviceLost(f"serial write failed: {exc}") from exc
        if not wait:
            return None
        if not pending.event.wait(REPLY_TIMEOUT + extra_ms / 1000):
            raise DeviceLost(f"no reply to {cmd.name}; device stopped responding")
        with self._cond:
            self._raise_if_failed()
        return pending.reply

    # ── Session ──────────────────────────────────────────────────────────────

    @property
    def alive(self) -> bool:
        """False once closed or once the serial port is gone (e.g. unplugged)."""
        return not self._closed and self._reader.is_alive()

    def hello(self) -> str:
        reply = self._send(p.Cmd.HELLO, wait=True)
        if not reply.payload or reply.payload[0] != p.VERSION:
            got = reply.payload[0] if reply.payload else None
            raise DeviceError(
                f"firmware speaks protocol {got}, this app needs {p.VERSION}. Flash the bundled firmware.")
        return reply.payload[1:].decode("ascii", "replace")

    def ping(self) -> bool:
        try:
            return self._send(p.Cmd.PING, wait=True).status == p.Status.OK
        except DeviceError:
            return False

    def flush(self):
        with self._cond:
            while self._pending:
                self._raise_if_failed()
                self._expire()
                self._cond.wait(0.05)
            self._raise_if_failed()

    def close(self):
        if self._closed:
            return
        try:
            self.release_all()
            self.flush()
        except DeviceError:
            pass
        self._closed = True
        self._reader.join(timeout=1.0)
        self._link.close()

    # ── Pointer ──────────────────────────────────────────────────────────────

    def _to_abs(self, x: int, y: int) -> tuple[int, int]:
        # HID range starts at 1, not 0: Windows drops an absolute report at exactly
        # (0, 0) (seen on the real board: top-left left the pointer where it was).
        # 1/32767 of the screen still rounds to pixel 0.
        def axis(v, size):
            v = min(max(v, 0), size - 1)
            return 1 + round(v * (p.ABS_MAX - 1) / max(size - 1, 1))
        return axis(x, self.screen_w), axis(y, self.screen_h)

    def move_to(self, x, y):
        self._send(p.Cmd.MOVE_ABS, p.p_xy(*self._to_abs(x, y)))

    def glide_to(self, x, y, duration_ms):
        duration_ms = max(0, min(int(duration_ms), 0xFFFF))
        self._send(p.Cmd.GLIDE_ABS, p.p_glide(*self._to_abs(x, y), duration_ms), extra_ms=duration_ms)

    def move_by(self, dx, dy):
        dx = max(-32768, min(int(dx), 32767))
        dy = max(-32768, min(int(dy), 32767))
        self._send(p.Cmd.MOVE_REL, p.p_dxdy(dx, dy))

    def button_down(self, button="left"):
        self._send(p.Cmd.BUTTON_DOWN, bytes((button_mask(button),)))

    def button_up(self, button="left"):
        self._send(p.Cmd.BUTTON_UP, bytes((button_mask(button),)))

    def click(self, button="left", hold_ms=30):
        self._send(p.Cmd.CLICK, p.p_mask_hold(button_mask(button), hold_ms), extra_ms=hold_ms)

    def scroll(self, wheel):
        self._send(p.Cmd.SCROLL, int(max(-127, min(wheel, 127))).to_bytes(1, "little", signed=True))

    # ── Keyboard ─────────────────────────────────────────────────────────────

    def key_down(self, key):
        self._send(p.Cmd.KEY_DOWN, bytes((key_code(key),)))

    def key_up(self, key):
        self._send(p.Cmd.KEY_UP, bytes((key_code(key),)))

    def key_tap(self, key, hold_ms=35):
        self._send(p.Cmd.KEY_TAP, p.p_mask_hold(key_code(key), hold_ms), extra_ms=hold_ms)

    def release_all(self):
        self._send(p.Cmd.RELEASE_ALL)

    # ── Board ────────────────────────────────────────────────────────────────

    def set_led(self, on):
        """Status LED on or off. The board keeps the setting across restarts.
        Firmware before 0.3.0 doesn't know the command (DeviceRejected)."""
        self._send(p.Cmd.SET_LED, bytes((1 if on else 0,)), wait=True)
