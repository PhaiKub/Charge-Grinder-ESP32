"""Human-like pointer movement.

builder.py, generator.py, inertia.py and model.npz come from Walpth's
Charge-Grinder (source/utils/movement) unchanged apart from imports. The
original's pointer_gain.py is not ported: it learned Windows' pointer
acceleration curve to aim relative moves, and the ESP32 moves the pointer in
absolute coordinates, so every point lands exactly where it is sent.
"""

import time

import numpy as np

from ..device.base import InputDevice
from .builder import build_trajectory
from .inertia import get_inherited_velocity, update_inertia

__all__ = ["build_trajectory", "drag", "move", "play"]


def play(dev: InputDevice, points, times, speed: float = 1.0) -> None:
    """Replay a timed path as absolute moves.

    The path is sampled at 1 kHz but one round trip to the board takes 1–2 ms,
    so each step sends the newest point that is due rather than every point;
    the pointer stays on schedule and always finishes on the last point.
    """
    pts = np.rint(np.asarray(points, dtype=float)).astype(int)
    ts = np.asarray(times, dtype=float) / max(float(speed), 1e-3)
    n = min(len(pts), len(ts))
    if n == 0:
        return
    start = time.perf_counter()
    last = None
    while True:
        elapsed = time.perf_counter() - start
        i = min(int(np.searchsorted(ts[:n], elapsed, side="right")) - 1, n - 1)
        i = max(i, 0)
        point = (int(pts[i, 0]), int(pts[i, 1]))
        if point != last:
            dev.move_to(*point)
            last = point
        if i == n - 1:
            break
        wait = ts[i + 1] - (time.perf_counter() - start)
        if wait > 5e-4:
            time.sleep(wait - 3e-4)
    dev.flush()


def _within(a, b, size) -> bool:
    w, h = size
    return abs(a[0] - b[0]) <= w / 2 and abs(a[1] - b[1]) <= h / 2


def move(dev: InputDevice, x, y, *, duration: float | None = None, target_size=(5.0, 5.0),
         curve: float = 1.0, n_sub: int | None = None, inertia: bool = False,
         speed: float = 1.0) -> None:
    """Move to (x, y) along a generated human-like path.

    Mirrors the original moveTo(): `target_size` is the clickable area the
    path may end anywhere inside, `duration` overrides the sampled one,
    `curve` scales curviness and `n_sub` forces the number of sub-movements.
    `speed` > 1 replays the path faster.
    """
    w, h = dev.screen_w, dev.screen_h
    end = (min(max(int(round(x)), 0), w - 1), min(max(int(round(y)), 0), h - 1))
    start = dev.position()
    if _within(start, end, target_size):
        return

    traj = build_trajectory(
        start,
        end,
        duration_override=duration if duration and duration > 0 else None,
        target_width=target_size[0],
        target_height=target_size[1],
        initial_velocity=get_inherited_velocity() if inertia else None,
        curviness=curve,
        n_submovements=n_sub,
    )
    points = np.asarray(traj["points"], dtype=float)
    points[:, 0] = np.clip(points[:, 0], 0, w - 1)
    points[:, 1] = np.clip(points[:, 1], 0, h - 1)
    play(dev, points, traj["times"], speed=speed)
    update_inertia(points, traj["times"])


def drag(dev: InputDevice, x, y, *, duration: float = 0.1, button: str = "left",
         target_size=(5.0, 5.0)) -> None:
    """Press, move in one fairly straight stroke, release (the original dragTo)."""
    dev.button_down(button)
    time.sleep(0.03)
    move(dev, x, y, duration=duration, target_size=target_size, n_sub=1, curve=0.2)
    time.sleep(0.03)
    dev.button_up(button)
    dev.flush()
