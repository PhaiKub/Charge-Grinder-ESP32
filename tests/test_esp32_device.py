import pytest

from cg_esp32 import protocol as p
from cg_esp32.device import DeviceError, Esp32Device, MockDevice
from cg_esp32.device import esp32
from fake_device import FakeLink


def make(link=None, size=(1920, 1080)):
    return Esp32Device(screen_size=size, link=link or FakeLink(fw="0.1.0"))


def test_hello_reads_firmware_version():
    dev = make()
    assert dev.firmware_version == "0.1.0"
    dev.close()


def test_hello_splits_version_and_board():
    dev = make(FakeLink(fw="0.2.0 esp32s3"))
    assert (dev.firmware_version, dev.firmware_board) == ("0.2.0", "esp32s3")
    dev.close()
    dev = make(FakeLink(fw="0.1.0"))
    assert dev.firmware_board is None
    dev.close()


def test_protocol_mismatch_refuses_and_releases_the_port():
    link = FakeLink(proto_version=9)
    with pytest.raises(DeviceError, match="protocol 9"):
        make(link)
    assert link.closed


def test_commands_reach_device_in_order():
    link = FakeLink()
    dev = make(link)
    dev.move_to(0, 0)
    dev.move_to(1919, 1079)
    dev.glide_to(960, 540, 120)
    dev.click("right", hold_ms=40)
    dev.key_tap("esc")
    dev.scroll(-3)
    dev.flush()
    assert link.executed == [
        ("MOVE_ABS", 1, 1),
        ("MOVE_ABS", 32767, 32767),
        ("GLIDE_ABS", 16393, 16399, 120),
        ("CLICK", 2, 40),
        ("KEY_TAP", 0x29, 35),
        ("SCROLL", -3),
    ]
    dev.close()


def test_default_window_is_one_in_flight():
    link = FakeLink()
    dev = make(link)
    for _ in range(20):
        dev.move_by(1, 0)
    dev.flush()
    assert link.max_in_flight == 1
    dev.close()


def test_window_limits_in_flight():
    link = FakeLink()
    dev = Esp32Device(screen_size=(1920, 1080), link=link, window=p.WINDOW)
    for i in range(200):
        dev.move_by(1, 0)
    dev.flush()
    assert len(link.executed) == 200
    assert link.max_in_flight <= p.WINDOW
    dev.close()


def test_rejected_frame_surfaces_as_error():
    link = FakeLink()
    dev = make(link)
    link.corrupt_next = 1
    dev.move_to(10, 10)
    with pytest.raises(DeviceError, match="BAD_CRC"):
        dev.flush()
    dev.move_to(20, 20)  # link keeps working after a bad frame
    dev.flush()
    dev.close()


def test_silent_device_times_out(monkeypatch):
    monkeypatch.setattr(esp32, "REPLY_TIMEOUT", 0.2)
    link = FakeLink()
    dev = make(link)
    link.drop_replies = True
    dev.move_to(5, 5)
    with pytest.raises(DeviceError, match="stopped responding"):
        dev.flush()


def test_unknown_key_is_rejected_before_sending():
    dev = make()
    with pytest.raises(ValueError):
        dev.key_tap("nope")
    dev.close()


def test_mock_device_tracks_state():
    dev = MockDevice()
    dev.key_down("shift")
    dev.button_down()
    dev.release_all()
    assert dev.keys == set() and dev.buttons == 0
