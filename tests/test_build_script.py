import importlib.util
import os
import sys
from pathlib import Path

import pytest

from cg_esp32 import boards

_SCRIPT = Path(__file__).resolve().parents[1] / "release" / "build_windows.py"
_spec = importlib.util.spec_from_file_location("build_windows", _SCRIPT)
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

ENVS = build.firmware_envs()


def data_files_in(args):
    """{path inside the exe: source} from the --include-data-files options."""
    found = {}
    for arg in args:
        if arg.startswith("--include-data-files="):
            src, dest = arg.removeprefix("--include-data-files=").rsplit("=", 1)
            found[dest] = src
    return found


def test_firmware_envs_cover_every_board_once():
    assert sorted(ENVS) == sorted({b.firmware for b in boards.BOARDS})
    assert len(ENVS) == len(set(ENVS))


def test_windows_version_has_four_numbers():
    assert build.windows_version("0.1.0") == "0.1.0.0"
    assert build.windows_version("2") == "2.0.0.0"
    assert build.windows_version("1.2.3.4") == "1.2.3.4"
    assert build.windows_version("0.2.0-rc1\n") == "0.2.0.0"
    assert build.numeric_version("0.2.0-rc1") == "0.2.0"
    with pytest.raises(ValueError):
        build.windows_version("dev")


def test_args_ship_every_firmware_image_the_model_and_esptool():
    args = build.nuitka_args("0.1.0", ENVS)
    files = data_files_in(args)
    for env in ENVS:
        for ext in (".bin", ".json"):
            dest = f"firmware/dist/{env}{ext}"
            assert Path(files[dest]) == build.FIRMWARE_DIST / f"{env}{ext}"
    assert Path(files["move_assets/model.npz"]) == build.MODEL
    assert build.MODEL.is_file()
    assert files["version"] and "ImageAssets/app_icon.ico" in files
    assert "--include-package=cg_esp32" in args
    assert "--include-package=esptool" in args
    assert "--include-package-data=esptool" in args
    assert "--file-version=0.1.0.0" in args
    assert "--onefile-tempdir-spec={CACHE_DIR}/PhaiKub/Charge-Grinder-ESP32/{VERSION}" in args
    assert f"--include-data-dir={build.ROOT / 'ImageAssets' / 'UI'}=ImageAssets/UI" in args
    assert args[-1] == str(build.ENTRY)


def test_output_name_and_console_mode():
    args = build.nuitka_args("0.1.0", ENVS)
    assert "--output-filename=Charge-Grinder-ESP32.exe" in args
    assert "--windows-console-mode=disable" in args
    args = build.nuitka_args("0.1.0", ENVS, console=True)
    assert "--output-filename=Charge-Grinder-ESP32-console.exe" in args
    assert "--windows-console-mode=force" in args


def test_nuitka_runs_with_this_python_and_host_on_pythonpath():
    assert build.nuitka_command("0.1.0", ENVS)[:3] == [sys.executable, "-m", "nuitka"]
    assert build.build_env({})["PYTHONPATH"] == str(build.HOST)
    env = build.build_env({"PYTHONPATH": "other", "PATH": "x"})
    assert env["PYTHONPATH"] == os.pathsep.join([str(build.HOST), "other"])
    assert env["PATH"] == "x"


def test_missing_firmware_is_listed(tmp_path):
    envs = ["esp32s3", "lolin_s2_mini"]
    assert build.missing_firmware(envs, tmp_path) == [
        "esp32s3.bin", "esp32s3.json", "lolin_s2_mini.bin", "lolin_s2_mini.json"]
    (tmp_path / "esp32s3.bin").write_bytes(b"\xe9")
    (tmp_path / "esp32s3.json").write_text("{}")
    assert build.missing_firmware(envs, tmp_path) == ["lolin_s2_mini.bin", "lolin_s2_mini.json"]


def test_main_stops_with_build_hint_when_firmware_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "FIRMWARE_DIST", tmp_path)
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: pytest.fail("must not run anything"))
    with pytest.raises(SystemExit) as exc:
        build.main([])
    message = str(exc.value.code)
    assert f"{ENVS[0]}.bin" in message
    assert "pio run" in message and "--firmware" in message
