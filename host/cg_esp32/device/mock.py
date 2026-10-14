"""In-memory InputDevice for tests and dry runs; records every call."""

from .base import InputDevice
from ..keys import button_mask, key_code


class MockDevice(InputDevice):
    def __init__(self, screen_size=(1920, 1080)):
        super().__init__(screen_size)
        self.calls: list[tuple] = []
        self.pos = (0, 0)
        self.buttons = 0
        self.keys: set[int] = set()

    def _log(self, *call):
        self.calls.append(call)

    def position(self):
        return self.pos

    def move_to(self, x, y):
        self.pos = (x, y)
        self._log("move_to", x, y)

    def glide_to(self, x, y, duration_ms):
        self.pos = (x, y)
        self._log("glide_to", x, y, duration_ms)

    def move_by(self, dx, dy):
        self.pos = (self.pos[0] + dx, self.pos[1] + dy)
        self._log("move_by", dx, dy)

    def button_down(self, button="left"):
        self.buttons |= button_mask(button)
        self._log("button_down", button)

    def button_up(self, button="left"):
        self.buttons &= ~button_mask(button)
        self._log("button_up", button)

    def click(self, button="left", hold_ms=30):
        button_mask(button)
        self._log("click", button, hold_ms)

    def scroll(self, wheel):
        self._log("scroll", wheel)

    def key_down(self, key):
        self.keys.add(key_code(key))
        self._log("key_down", key)

    def key_up(self, key):
        self.keys.discard(key_code(key))
        self._log("key_up", key)

    def key_tap(self, key, hold_ms=35):
        key_code(key)
        self._log("key_tap", key, hold_ms)

    def release_all(self):
        self.buttons = 0
        self.keys.clear()
        self._log("release_all")

    def flush(self):
        pass

    def close(self):
        self._log("close")
