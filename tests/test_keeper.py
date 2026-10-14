import pytest

from cg_esp32.device import BoardKeeper, DeviceError, DeviceLost, MockDevice, WaitCancelled


class Board(MockDevice):
    def __init__(self, port):
        super().__init__()
        self.port = port
        self.alive = True

    def close(self):
        self.alive = False
        super().close()


class Bus:
    """Boards that open on demand; `plugged` decides whether one answers."""

    def __init__(self):
        self.plugged = True
        self.opened = []
        self.error = None

    def open(self, port):
        if self.error is not None:
            raise self.error
        if not self.plugged:
            raise DeviceLost("board not found")
        board = Board(port or "COM5")
        self.opened.append(board)
        return board


def make_keeper(bus, **kw):
    return BoardKeeper(bus.open, present=lambda: bus.plugged, poll=0, settle=0, sleep=lambda s: None, **kw)


def test_get_opens_once_and_reopens_a_dead_board():
    bus = Bus()
    keeper = make_keeper(bus)
    first = keeper.get()
    assert keeper.get() is first
    first.alive = False
    second = keeper.get()
    assert second is not first
    assert second.port == "COM5"
    assert len(bus.opened) == 2


def test_run_raises_without_a_listener():
    keeper = make_keeper(Bus())

    def op(dev):
        raise DeviceLost("serial link lost")

    with pytest.raises(DeviceLost):
        keeper.run(op)


def test_run_waits_for_the_board_and_repeats_the_step():
    bus = Bus()
    events = []
    keeper = make_keeper(bus)
    keeper.on_lost = lambda reason: (events.append(("lost", reason)), setattr(bus, "plugged", False))
    keeper.on_back = lambda dev: events.append(("back", dev.port))
    attempts = []
    polls = []

    def sleep(_):
        polls.append(1)
        if len(polls) == 3:
            bus.plugged = True  # replugged after a few polls

    keeper._sleep = sleep

    def op(dev):
        attempts.append(dev)
        if len(attempts) == 1:
            raise DeviceLost("serial link lost")
        dev.key_down("a")
        return "done"

    assert keeper.run(op) == "done"
    assert events[0] == ("lost", "serial link lost")
    assert events[-1] == ("back", "COM5")
    assert attempts[0] is not attempts[1]
    # the new board was cleared before the step ran again
    assert attempts[1].calls[0] == ("release_all",)
    assert attempts[1].calls[-1] == ("key_down", "a")


def test_wait_is_cancelled_by_stop():
    bus = Bus()
    keeper = make_keeper(bus)
    stop = []
    keeper.on_lost = lambda reason: setattr(bus, "plugged", False)
    keeper.cancelled = lambda: bool(stop)
    keeper._sleep = lambda s: stop.append(1)

    def op(dev):
        raise DeviceLost("serial link lost")

    with pytest.raises(WaitCancelled):
        keeper.run(op)


def test_other_device_errors_are_not_waited_out():
    bus = Bus()
    keeper = make_keeper(bus)
    keeper.on_lost = lambda reason: None

    def op(dev):
        raise DeviceError("device rejected KEY_DOWN: BAD_LEN")

    with pytest.raises(DeviceError, match="BAD_LEN"):
        keeper.run(op)


def test_wrong_firmware_after_replug_stops_the_wait():
    bus = Bus()
    keeper = make_keeper(bus)
    keeper.on_lost = lambda reason: setattr(bus, "error", DeviceError("firmware speaks protocol 0"))
    calls = []

    def op(dev):
        calls.append(dev)
        raise DeviceLost("serial link lost")

    with pytest.raises(DeviceError, match="protocol 0"):
        keeper.run(op)
    assert len(calls) == 1


def test_get_falls_back_to_any_port_after_the_com_number_changes():
    bus = Bus()
    keeper = make_keeper(bus)
    keeper.connect("COM5")
    keeper.device.alive = False
    real_open = bus.open
    bus.open = lambda port: (_ for _ in ()).throw(DeviceLost("cannot open COM5")) if port == "COM5" else real_open("COM7")
    keeper._open_device = bus.open
    assert keeper.get().port == "COM7"
    assert keeper.port == "COM7"
