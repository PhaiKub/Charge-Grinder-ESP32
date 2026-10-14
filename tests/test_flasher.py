import sys
import types

import pytest

from cg_esp32 import flasher


def test_args_write_merged_image_at_zero():
    args = flasher.esptool_args("COM6", "fw.bin", "esp32s3")
    assert args[:4] == ["--chip", "esp32s3", "--port", "COM6"]
    assert args[args.index("--before") + 1] == "default_reset"
    assert args[-4:] == ["write_flash", "-z", "0x0", "fw.bin"]
    assert "no_reset" in flasher.esptool_args("COM5", "fw.bin", "esp32s2", reset=False)


def fake_esptool(monkeypatch, body):
    mod = types.ModuleType("esptool")

    class FatalError(RuntimeError):
        pass

    mod.FatalError = FatalError
    mod.main = lambda argv: body(mod, argv)
    monkeypatch.setitem(sys.modules, "esptool", mod)
    return mod


def test_flash_reports_lines_and_progress(monkeypatch):
    def body(mod, argv):
        print("Connecting....")
        print("Writing at 0x00010000... (9 %)")
        sys.stdout.write("Writing at 0x0005620b... (100 %)\nHash of data verified.\n")
    fake_esptool(monkeypatch, body)
    lines, progress = [], []
    flasher.flash("COM6", "fw.bin", "esp32s3", on_line=lines.append, on_progress=progress.append)
    assert lines == ["Connecting....", "Writing at 0x00010000... (9 %)",
                     "Writing at 0x0005620b... (100 %)", "Hash of data verified."]
    assert progress == [9, 100, 100]


def test_flash_turns_esptool_errors_into_flash_error(monkeypatch):
    def body(mod, argv):
        print("Connecting......")
        raise mod.FatalError("Failed to connect to ESP32-S3: Wrong boot mode detected (0x2b)!")
    fake_esptool(monkeypatch, body)
    lines = []
    with pytest.raises(flasher.FlashError, match="Wrong boot mode"):
        flasher.flash("COM6", "fw.bin", "esp32s3", on_line=lines.append)
    assert lines == ["Connecting......"]


def test_flash_wraps_serial_errors(monkeypatch):
    def body(mod, argv):
        raise OSError("could not open port 'COM6': PermissionError(13, 'Access is denied.')")
    fake_esptool(monkeypatch, body)
    with pytest.raises(flasher.FlashError, match="Access is denied"):
        flasher.flash("COM6", "fw.bin", "esp32s3")


def test_download_mode_waits_for_the_port_to_come_back(monkeypatch):
    import serial
    touched = []
    monkeypatch.setattr(serial, "Serial", lambda port, baud: touched.append((port, baud)) or types.SimpleNamespace(dtr=True, close=lambda: None))
    # COM5 stays for one poll, vanishes, then the ROM port shows up as COM7.
    states = iter([["COM5"], [], [], ["COM7"]])
    port = flasher.enter_download_mode("COM5", list_native=lambda: next(states, ["COM7"]), sleep=lambda s: None)
    assert touched == [("COM5", 1200)]
    assert port == "COM7"


def test_download_mode_keeps_a_port_already_in_download_mode(monkeypatch):
    import serial
    monkeypatch.setattr(serial, "Serial", lambda port, baud: types.SimpleNamespace(dtr=True, close=lambda: None))
    port = flasher.enter_download_mode("COM5", list_native=lambda: ["COM5"], settle=1.0, sleep=lambda s: None)
    assert port == "COM5"


def test_download_mode_gives_up(monkeypatch):
    import serial
    monkeypatch.setattr(serial, "Serial", lambda port, baud: types.SimpleNamespace(dtr=True, close=lambda: None))
    with pytest.raises(flasher.FlashError, match="did not come back"):
        flasher.enter_download_mode("COM5", list_native=lambda: [], timeout=1.0, sleep=lambda s: None)
