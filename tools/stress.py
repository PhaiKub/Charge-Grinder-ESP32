"""Find how hard the board can be pushed before USB stalls.

    uv run --with pyserial python tools/stress.py            # windows 1, 2, 4, 8
    uv run --with pyserial python tools/stress.py 1 5000     # window 1, 5000 moves

For each window size (requests in flight) it sends a burst of small absolute
moves around the screen centre and reports the rate, or where it stalled. After
a stall the board usually needs a replug, so the run stops there.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))

from cg_esp32.device import DeviceError, Esp32Device  # noqa: E402


def run(window: int, count: int) -> bool:
    dev = Esp32Device(window=window)
    w, h = dev.screen_w, dev.screen_h
    t0 = time.perf_counter()
    try:
        for i in range(count):
            dev.move_to(w // 2 + (i % 100) - 50, h // 2)
        dev.flush()
    except DeviceError as exc:
        print(f"window {window}: STALLED after ~{i} moves ({time.perf_counter() - t0:.1f} s): {exc}")
        return False
    dt = time.perf_counter() - t0
    print(f"window {window}: {count} moves OK in {dt:.2f} s ({count / dt:.0f} moves/s, {dt / count * 1000:.2f} ms each)")
    dev.close()
    return True


def main() -> int:
    windows = [int(sys.argv[1])] if len(sys.argv) > 1 else [1, 2, 4, 8]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    for window in windows:
        if not run(window, count):
            return 1
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
