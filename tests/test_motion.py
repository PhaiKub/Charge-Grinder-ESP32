import time

import pytest

np = pytest.importorskip("numpy")

from cg_esp32.device import MockDevice  # noqa: E402
from cg_esp32.motion import build_trajectory, drag, move, play  # noqa: E402


def test_trajectory_starts_at_start_and_ends_inside_target():
    for start, end in [((100, 100), (1500, 800)), ((10, 1000), (1900, 20)), ((960, 540), (980, 530))]:
        traj = build_trajectory(start, end, target_width=10, target_height=10)
        pts = traj["points"]
        assert tuple(pts[0]) == start
        assert abs(pts[-1][0] - end[0]) <= 5 and abs(pts[-1][1] - end[1]) <= 5
        assert np.all(np.diff(traj["times"]) >= 0)


def test_play_keeps_schedule_and_finishes_on_last_point():
    dev = MockDevice()
    pts = [(i, 2 * i) for i in range(200)]
    times = [i / 1000 for i in range(200)]  # 1 kHz, 0.2 s
    t0 = time.perf_counter()
    play(dev, pts, times)
    dt = time.perf_counter() - t0
    assert dev.pos == (199, 398)
    assert 0.19 <= dt <= 0.4
    xs = [c[1] for c in dev.calls if c[0] == "move_to"]
    assert xs == sorted(xs)  # never goes backwards along the path


def test_play_speed_scales_time():
    dev = MockDevice()
    pts = [(i, 0) for i in range(300)]
    times = [i / 1000 for i in range(300)]
    t0 = time.perf_counter()
    play(dev, pts, times, speed=3.0)
    assert time.perf_counter() - t0 < 0.2


def test_move_lands_in_target_and_stays_on_screen():
    dev = MockDevice((1920, 1080))
    dev.pos = (100, 100)
    move(dev, 1919, 1079, target_size=(10, 10), speed=4.0)
    x, y = dev.pos
    assert 1914 <= x <= 1919 and 1074 <= y <= 1079
    for call in dev.calls:
        if call[0] == "move_to":
            assert 0 <= call[1] <= 1919 and 0 <= call[2] <= 1079


def test_move_inside_target_does_nothing():
    dev = MockDevice()
    dev.pos = (500, 500)
    move(dev, 501, 499)
    assert dev.calls == []


def test_drag_presses_moves_releases():
    dev = MockDevice()
    dev.pos = (100, 100)
    drag(dev, 400, 120)
    names = [c[0] for c in dev.calls]
    assert names[0] == "button_down" and names[-1] == "button_up"
    assert "move_to" in names and dev.buttons == 0
