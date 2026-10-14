"""Flash a merged firmware image (firmware/dist/<env>.bin) with esptool.

The image already holds bootloader, partition table and app at their offsets,
so it is written at 0x0 and the flash mode/size in its header are kept.
"""

from __future__ import annotations

import contextlib
import io
import re
import time
from typing import Callable

FLASH_BAUD = 460800

_PROGRESS = re.compile(r"\((\d{1,3}) ?%\)")


class FlashError(Exception):
    pass


def enter_download_mode(port: str, *, list_native: Callable[[], list[str]],
                        on_line: Callable[[str], None] | None = None,
                        settle: float = 3.0, timeout: float = 10.0,
                        sleep: Callable[[float], None] = time.sleep) -> str:
    """Restart a board running on its native USB port into ROM download mode
    and return the port it comes back on (the COM number may change).

    Uses the Arduino "1200 baud touch": opening the TinyUSB serial port at
    1200 baud makes the firmware restart into the bootloader. A board that is
    already in download mode ignores it and keeps its port.
    """
    say = on_line or (lambda _line: None)
    say(f"Restarting the board on {port} into download mode...")
    try:
        import serial
        link = serial.Serial(port, 1200)
        link.dtr = False
        link.close()
    except Exception as exc:  # already gone, or a ROM port that dislikes 1200 baud
        say(f"{port}: {exc}")

    # Wait for the port to drop off the bus (it may not, if the board was
    # already in download mode), then for a native port to come back.
    waited = 0.0
    while waited < settle and port in list_native():
        sleep(0.25)
        waited += 0.25
    waited = 0.0
    while waited < timeout:
        ports = list_native()
        if ports:
            sleep(0.5)  # let Windows finish installing the port
            chosen = next((p for p in ports if p != port), ports[0])
            say(f"Download mode port: {chosen}")
            return chosen
        sleep(0.25)
        waited += 0.25
    raise FlashError("the board did not come back in download mode")


class _LineWriter(io.TextIOBase):
    """stdout replacement that hands esptool's output over line by line."""

    def __init__(self, on_line: Callable[[str], None] | None, on_progress: Callable[[int], None] | None):
        self._on_line = on_line
        self._on_progress = on_progress
        self._buf = ""
        self.lines: list[str] = []

    def writable(self):
        return True

    def isatty(self):
        return False  # esptool then prints progress as plain lines, not \r overwrites

    def write(self, text):
        self._buf += text.replace("\r", "\n")
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._emit(line)
        return len(text)

    def flush(self):
        pass

    def finish(self):
        if self._buf:
            self._emit(self._buf)
            self._buf = ""

    def _emit(self, line: str):
        line = line.rstrip()
        if not line:
            return
        self.lines.append(line)
        match = _PROGRESS.search(line)
        if match and line.startswith("Writing at") and self._on_progress:
            self._on_progress(min(int(match.group(1)), 100))
        if self._on_line:
            self._on_line(line)


def esptool_args(port: str, image: str, chip: str, *, baud: int = FLASH_BAUD, reset: bool = True) -> list[str]:
    """esptool command line for writing a merged image.

    `reset=False` is for a board already in download mode on its native USB
    port, where the UART reset lines (DTR/RTS) do nothing.
    """
    return [
        "--chip", chip,
        "--port", port,
        "--baud", str(baud),
        "--before", "default_reset" if reset else "no_reset",
        "--after", "hard_reset",
        "write_flash", "-z", "0x0", str(image),
    ]


def flash(port: str, image: str, chip: str, *, baud: int = FLASH_BAUD, reset: bool = True,
          on_line: Callable[[str], None] | None = None,
          on_progress: Callable[[int], None] | None = None) -> None:
    """Write `image` to the board on `port`. Raises FlashError with esptool's reason."""
    try:
        import esptool
    except ImportError as exc:
        raise FlashError("esptool is not installed (pip install esptool)") from exc

    writer = _LineWriter(on_line, on_progress)
    args = esptool_args(port, image, chip, baud=baud, reset=reset)
    try:
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            esptool.main(args)
    except esptool.FatalError as exc:
        raise FlashError(str(exc)) from exc
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise FlashError(f"esptool exited with {exc.code}") from exc
    except Exception as exc:  # serial errors: port busy, unplugged mid-flash, ...
        raise FlashError(str(exc) or exc.__class__.__name__) from exc
    finally:
        writer.finish()
    if on_progress:
        on_progress(100)
