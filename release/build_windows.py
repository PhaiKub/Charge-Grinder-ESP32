"""Build build/Charge-Grinder-ESP32.exe with Nuitka (run it on Windows).

One file holds the app, esptool and every board's firmware image
(firmware/dist/<env>.bin + <env>.json), so the device window can flash a board
without PlatformIO installed.

    uv run --with-requirements requirements-build.txt python release/build_windows.py

--firmware runs `pio run` in firmware/ first. --console builds
Charge-Grinder-ESP32-console.exe, which keeps a console window for logs and
tracebacks.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "host"  # the cg_esp32 package, not installed
ENTRY = ROOT / "App.py"
VERSION_FILE = ROOT / "version"
ICON = ROOT / "ImageAssets" / "app_icon.ico"
MODEL = HOST / "cg_esp32" / "motion" / "model.npz"
FIRMWARE_DIR = ROOT / "firmware"
FIRMWARE_DIST = FIRMWARE_DIR / "dist"
BUILD_DIR = ROOT / "build"

COMPANY = "PhaiKub"
PRODUCT = "Charge-Grinder-ESP32"
DESCRIPTION = "Charge-Grinder-ESP32-Edition"

RUN_COMMAND = "uv run --with-requirements requirements-build.txt python release/build_windows.py"


def read_version(path: Path = VERSION_FILE) -> str:
    return path.read_text(encoding="utf-8").strip()


def numeric_version(version: str) -> str:
    """The leading numbers of `version`, at most four ('0.2.0-rc1' -> '0.2.0').

    Windows version resources (Nuitka --file-version/--product-version) take
    numbers only.
    """
    match = re.match(r"\d+(?:\.\d+){0,3}", version.strip())
    if not match:
        raise ValueError(f"version {version!r} does not start with a number")
    return ".".join(str(int(part)) for part in match.group(0).split("."))


def windows_version(version: str) -> str:
    """'0.1.0' -> '0.1.0.0': the file version always has four numbers."""
    parts = numeric_version(version).split(".")
    return ".".join(parts + ["0"] * (4 - len(parts)))


def output_name(console: bool = False) -> str:
    return f"{PRODUCT}-console.exe" if console else f"{PRODUCT}.exe"


# ── Firmware images ───────────────────────────────────────────────────────────

def firmware_envs() -> list[str]:
    """PlatformIO envs whose images ship in the exe: each Board.firmware once."""
    if str(HOST) not in sys.path:
        sys.path.insert(0, str(HOST))
    from cg_esp32.boards import BOARDS

    return list(dict.fromkeys(board.firmware for board in BOARDS))


def firmware_files(envs: list[str], dist: Path) -> list[Path]:
    return [dist / f"{env}{ext}" for env in envs for ext in (".bin", ".json")]


def missing_firmware(envs: list[str], dist: Path) -> list[str]:
    """Names of the <env>.bin / <env>.json files that are not in `dist`."""
    return [path.name for path in firmware_files(envs, dist) if not path.is_file()]


def firmware_hint(missing: list[str], *, built: bool) -> str:
    text = f"firmware/dist is missing {', '.join(missing)}."
    if built:
        return text + ("\n`pio run` did not write them: check that default_envs in "
                       "firmware/platformio.ini lists every board's env.")
    return text + ("\nBuild the firmware images first (needs PlatformIO):\n"
                   "    cd firmware\n"
                   "    pio run\n"
                   "or run this script with --firmware.")


def build_firmware() -> None:
    """`pio run` in firmware/: builds every env in default_envs into firmware/dist."""
    pio = shutil.which("pio") or shutil.which("platformio")
    if pio is None:
        sys.exit("PlatformIO (pio) is not on PATH. Install it with: uv tool install platformio")
    print(f"Building firmware: pio run in {FIRMWARE_DIR}", flush=True)
    result = subprocess.run([pio, "run"], cwd=FIRMWARE_DIR)
    if result.returncode:
        sys.exit(f"pio run failed (exit code {result.returncode})")


# ── Nuitka ────────────────────────────────────────────────────────────────────

def data_dirs() -> list[tuple[Path, str]]:
    return [(ROOT / "ImageAssets" / name, f"ImageAssets/{name}") for name in ("UI", "AppUI")]


def data_files(envs: list[str]) -> list[tuple[Path, str]]:
    """(source, path inside the exe) for single files.

    The paths inside match what the app reads next to sys.executable:
    source/utils/paths.py (assets, version), source_app/device_panel.py
    (firmware/dist) and cg_esp32/motion/builder.py (move_assets).
    """
    files = [
        (ICON, "ImageAssets/app_icon.ico"),
        (VERSION_FILE, "version"),
        (MODEL, "move_assets/model.npz"),
    ]
    # One by one: --include-data-dir would skip the .bin files as code.
    files += [(path, f"firmware/dist/{path.name}") for path in firmware_files(envs, FIRMWARE_DIST)]
    return files


def missing_inputs(envs: list[str]) -> list[str]:
    """Build inputs that are not there, relative to the repo root."""
    paths = [ENTRY] + [src for src, _ in data_dirs()] + [src for src, _ in data_files(envs)]
    return [str(path.relative_to(ROOT)) for path in paths if not path.exists()]


def nuitka_args(version: str, envs: list[str], *, console: bool = False) -> list[str]:
    """Nuitka options for the onefile build, ending with the entry script."""
    args = [
        "--onefile",
        # zstd level 3, single-threaded, instead of level 22: packing the
        # PySide6 payload at the default can run a 16 GB machine out of RAM.
        "--low-memory",
        "--remove-output",
        "--enable-plugin=pyside6",
        "--assume-yes-for-downloads",
        f"--company-name={COMPANY}",
        f"--product-name={PRODUCT}",
        f"--file-description={DESCRIPTION}",
        f"--file-version={windows_version(version)}",
        f"--product-version={numeric_version(version)}",
        # Unpacked once per version and reused on later starts.
        f"--onefile-tempdir-spec={{CACHE_DIR}}/{COMPANY}/{PRODUCT}/{{VERSION}}",
        f"--output-dir={BUILD_DIR}",
        f"--output-filename={output_name(console)}",
        f"--windows-console-mode={'force' if console else 'disable'}",
        f"--windows-icon-from-ico={ICON}",
        # Found through PYTHONPATH (build_env); the app only adds host/ to
        # sys.path when it runs from source.
        "--include-package=cg_esp32",
        # Flashing runs esptool in-process; its stub flashers are data files.
        "--include-package=esptool",
        "--include-package-data=esptool",
    ]
    args += [f"--include-data-dir={src}={dest}" for src, dest in data_dirs()]
    args += [f"--include-data-files={src}={dest}" for src, dest in data_files(envs)]
    args.append(str(ENTRY))
    return args


def nuitka_command(version: str, envs: list[str], *, console: bool = False) -> list[str]:
    return [sys.executable, "-m", "nuitka", *nuitka_args(version, envs, console=console)]


def build_env(base: Mapping[str, str]) -> dict[str, str]:
    """`base` with host/ first on PYTHONPATH, so Nuitka finds cg_esp32."""
    env = dict(base)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(HOST), base.get("PYTHONPATH")) if p)
    return env


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=f"Build build/{output_name()} with Nuitka.")
    parser.add_argument("--firmware", action="store_true",
                        help="build the firmware images first (pio run in firmware/)")
    parser.add_argument("--console", action="store_true",
                        help="console build for debugging (the -console.exe)")
    args = parser.parse_args(argv)

    envs = firmware_envs()
    if args.firmware:
        build_firmware()
    missing = missing_firmware(envs, FIRMWARE_DIST)
    if missing:
        sys.exit(firmware_hint(missing, built=args.firmware))
    missing = missing_inputs(envs)
    if missing:
        sys.exit("Missing build inputs:\n    " + "\n    ".join(missing))
    if sys.platform != "win32":
        sys.exit("Run this on Windows: Nuitka builds an executable for the OS it runs on.")
    if importlib.util.find_spec("nuitka") is None:
        sys.exit(f"Nuitka is not installed. Run:\n    {RUN_COMMAND}")

    cmd = nuitka_command(read_version(), envs, console=args.console)
    print("Running:", subprocess.list2cmdline(cmd), flush=True)
    result = subprocess.run(cmd, cwd=ROOT, env=build_env(os.environ))
    if result.returncode:
        sys.exit(result.returncode)
    print(f"Built {BUILD_DIR / output_name(args.console)}")


if __name__ == "__main__":
    main()
