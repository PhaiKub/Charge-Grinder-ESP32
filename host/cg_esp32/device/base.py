"""The one interface bot code uses to drive mouse and keyboard."""

from abc import ABC, abstractmethod


class DeviceError(RuntimeError):
    pass


class InputDevice(ABC):
    """Screen coordinates are pixels on the primary monitor.

    Implementations convert to whatever the hardware wants (the ESP32 uses the
    HID absolute range 0–32767), so bot code never deals with pointer speed,
    acceleration, or relative-move correction.
    """

    def __init__(self, screen_size: tuple[int, int]):
        self.screen_w, self.screen_h = screen_size

    # Pointer
    @abstractmethod
    def move_to(self, x: int, y: int) -> None: ...

    @abstractmethod
    def glide_to(self, x: int, y: int, duration_ms: int) -> None: ...

    @abstractmethod
    def move_by(self, dx: int, dy: int) -> None: ...

    @abstractmethod
    def button_down(self, button: str = "left") -> None: ...

    @abstractmethod
    def button_up(self, button: str = "left") -> None: ...

    @abstractmethod
    def click(self, button: str = "left", hold_ms: int = 30) -> None: ...

    @abstractmethod
    def scroll(self, wheel: int) -> None: ...

    # Keyboard
    @abstractmethod
    def key_down(self, key: str) -> None: ...

    @abstractmethod
    def key_up(self, key: str) -> None: ...

    @abstractmethod
    def key_tap(self, key: str, hold_ms: int = 35) -> None: ...

    def position(self) -> tuple[int, int]:
        """Where the pointer actually is, read back from Windows."""
        import sys
        if sys.platform != "win32":
            raise DeviceError("reading the pointer position needs Windows")
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    # Housekeeping
    @abstractmethod
    def release_all(self) -> None: ...

    @abstractmethod
    def flush(self) -> None:
        """Block until the device has executed everything sent so far."""

    @abstractmethod
    def close(self) -> None: ...

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
