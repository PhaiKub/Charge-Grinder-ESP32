"""Quick check that the flashed board and the host package talk to each other.

Plug the board's native USB (OTG) port, then run from the repo root:

    uv run --with pyserial python tools/smoke_test.py

It only moves the pointer (no clicks or keys): centre, the four corners, then a
slow glide back to the centre. Watch that the pointer lands where it says.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))

from cg_esp32.device import DeviceError, Esp32Device  # noqa: E402
from cg_esp32.device.esp32 import find_port  # noqa: E402


def cursor_pos():
    """Where Windows actually put the pointer (None off Windows)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def main() -> int:
    port = find_port()
    print(f"port: {port or 'not found'}")
    try:
        dev = Esp32Device(port)
    except DeviceError as exc:
        print(f"FAILED: {exc}")
        return 1

    with dev:
        w, h = dev.screen_w, dev.screen_h
        print(f"firmware {dev.firmware_version}, screen {w}x{h}")

        t0 = time.perf_counter()
        for _ in range(100):
            dev.ping()
        print(f"ping round trip: {(time.perf_counter() - t0) * 10:.2f} ms")

        # One move at a time first, so a failure shows exactly which step hangs.
        for i, (x, y) in enumerate([(w // 2, h // 2), (w // 2 + 100, h // 2), (w // 2, h // 2)]):
            t0 = time.perf_counter()
            dev.move_to(x, y)
            dev.flush()
            print(f"single move {i + 1}: {(time.perf_counter() - t0) * 1000:.1f} ms")

        t0 = time.perf_counter()
        for i in range(500):
            dev.move_to(w // 2 + (i % 50), h // 2)
        dev.flush()
        print(f"500 moves: {(time.perf_counter() - t0) * 1000:.0f} ms")

        points = [("centre", w // 2, h // 2), ("top-left", 0, 0), ("top-right", w - 1, 0),
                  ("bottom-right", w - 1, h - 1), ("bottom-left", 0, h - 1)]
        worst = 0
        for name, x, y in points:
            dev.move_to(x, y)
            dev.flush()
            time.sleep(0.3)  # let Windows apply the report before reading it back
            actual = cursor_pos()
            if actual is None:
                print(f"-> {name} ({x}, {y})")
            else:
                err = max(abs(actual[0] - x), abs(actual[1] - y))
                worst = max(worst, err)
                print(f"-> {name}: wanted ({x}, {y}), got {actual}  [off by {err} px]")
            time.sleep(1.5)

        print("-> glide to centre over 1 s")
        dev.glide_to(w // 2, h // 2, 1000)
        dev.flush()
        time.sleep(0.3)
        actual = cursor_pos()
        if actual is not None:
            err = max(abs(actual[0] - w // 2), abs(actual[1] - h // 2))
            worst = max(worst, err)
            print(f"   got {actual}  [off by {err} px]")
    print(f"OK, worst position error {worst} px" if cursor_pos() is not None else "OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
