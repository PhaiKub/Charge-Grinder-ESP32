"""Watch the human-like movement on the real board.

    uv run --with pyserial --with numpy python tools/motion_demo.py

Moves to a few targets with generated paths (no clicks), then reports where
the pointer actually stopped and how long each move took.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))

from cg_esp32.device import DeviceError, Esp32Device  # noqa: E402
from cg_esp32.motion import move  # noqa: E402

TARGETS = [(0.5, 0.5), (0.15, 0.2), (0.85, 0.25), (0.8, 0.8), (0.2, 0.85), (0.52, 0.48), (0.5, 0.5)]
TARGET_SIZE = (20, 20)


def main() -> int:
    try:
        dev = Esp32Device()
    except DeviceError as exc:
        print(f"FAILED: {exc}")
        return 1
    with dev:
        w, h = dev.screen_w, dev.screen_h
        print(f"firmware {dev.firmware_version}, screen {w}x{h}, target size {TARGET_SIZE}")
        misses = 0
        for fx, fy in TARGETS:
            tx, ty = int(w * fx), int(h * fy)
            t0 = time.perf_counter()
            move(dev, tx, ty, target_size=TARGET_SIZE)
            took = time.perf_counter() - t0
            time.sleep(0.15)
            x, y = dev.position()
            inside = abs(x - tx) <= TARGET_SIZE[0] / 2 and abs(y - ty) <= TARGET_SIZE[1] / 2
            misses += not inside
            print(f"-> ({tx}, {ty}): stopped at ({x}, {y}) in {took * 1000:.0f} ms"
                  f"  {'inside target' if inside else 'MISSED'}")
            time.sleep(0.6)
    print("OK" if not misses else f"{misses} missed")
    return 0 if not misses else 1


if __name__ == "__main__":
    sys.exit(main())
