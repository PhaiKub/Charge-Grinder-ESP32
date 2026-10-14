"""Boards the app supports, their firmware images, and how to tell USB ports apart.

A board needs a native USB port that can act as a mouse and keyboard (USB-OTG),
which rules out the classic ESP32 and the ESP32-C3/C6. Each board points at a
firmware image built by PlatformIO (firmware/platformio.ini env of the same
name) into firmware/dist/<env>.bin with its version in <env>.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import serial.tools.list_ports

ESPRESSIF_VID = 0x303A

# USB-to-UART bridge chips found next to the ESP32 on dev boards.
UART_BRIDGES = {
    0x1A86: "CH340",
    0x10C4: "CP210x",
    0x0403: "FTDI",
}


@dataclass(frozen=True)
class Board:
    id: str
    name: str
    chip: str          # esptool --chip
    firmware: str      # PlatformIO env, also the image name in firmware/dist
    two_ports: bool    # True: a separate UART port is used for flashing
    ports_help: str    # shown in the device window
    flash_help: str


BOARDS: list[Board] = [
    Board(
        id="esp32s3-devkitc",
        name="ESP32-S3 DevKitC-1 (2 USB ports)",
        chip="esp32s3",
        firmware="esp32s3",
        two_ports=True,
        ports_help=(
            "USB (native OTG): runs the bot.\n"
            "COM (UART, CH340/CP210x): flashes the firmware. Only one cable? Pick the USB port to flash."
        ),
        flash_help=("Pick the COM (UART) port, or with only the USB cable pick the USB port, "
                    "then Flash Firmware."),
    ),
    Board(
        id="esp32s3-single",
        name="ESP32-S3, 1 USB port (Super Mini, Zero, ...)",
        chip="esp32s3",
        firmware="esp32s3",
        two_ports=False,
        ports_help="One USB port: runs the bot and flashes the firmware.",
        flash_help=(
            "Pick the USB port, then Flash Firmware; the app restarts the board into download mode. "
            "If that fails: hold BOOT, press and release RST, release BOOT, Re-scan, Flash again."
        ),
    ),
    Board(
        id="lolin_s2_mini",
        name="LOLIN S2 Mini (ESP32-S2)",
        chip="esp32s2",
        firmware="lolin_s2_mini",
        two_ports=False,
        ports_help="One USB port: runs the bot and flashes the firmware.",
        flash_help=(
            "Pick the USB port, then Flash Firmware; the app restarts the board into download mode. "
            "If that fails: hold 0, press and release RST, release 0, Re-scan, Flash again. "
            "Press RST when flashing is done."
        ),
    ),
]

BOARDS_BY_ID = {b.id: b for b in BOARDS}
DEFAULT_BOARD = BOARDS[0]


def board_for_firmware(firmware_board: str | None, preferred: Board | None = None) -> Board | None:
    """The board a running firmware reports (HELLO), keeping `preferred` if it fits."""
    if not firmware_board:
        return None
    env = firmware_board.removesuffix("-debug")
    if preferred is not None and preferred.firmware == env:
        return preferred
    return next((b for b in BOARDS if b.firmware == env), None)


# ── Firmware images ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FirmwareImage:
    path: Path
    version: str
    chip: str


def find_image(board: Board, dist_dir: str | Path) -> FirmwareImage | None:
    dist = Path(dist_dir)
    path = dist / f"{board.firmware}.bin"
    if not path.is_file():
        return None
    version, chip = "unknown", board.chip
    try:
        info = json.loads((dist / f"{board.firmware}.json").read_text(encoding="utf-8"))
        version = str(info.get("version", version))
        chip = str(info.get("chip", chip))
    except (OSError, ValueError):
        pass
    return FirmwareImage(path, version, chip)


def version_tuple(version: str | None) -> tuple[int, ...]:
    parts = []
    for piece in (version or "").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def is_newer(candidate: str | None, current: str | None) -> bool:
    a, b = version_tuple(candidate), version_tuple(current)
    return bool(a) and a > b


# ── Serial ports ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PortInfo:
    device: str      # "COM5"
    kind: str        # "native" (Espressif USB), "uart" (bridge chip) or "other"
    description: str

    @property
    def label(self) -> str:
        return f"{self.device}  ({self.description})" if self.description else self.device


def _sort_key(device: str):
    digits = "".join(ch for ch in device if ch.isdigit())
    return (device.rstrip("0123456789"), int(digits) if digits else 0)


def classify(vid: int | None) -> str:
    if vid == ESPRESSIF_VID:
        return "native"
    if vid in UART_BRIDGES:
        return "uart"
    return "other"


def list_ports() -> list[PortInfo]:
    """All serial ports, Espressif native USB first, then UART bridges, then the rest."""
    found = []
    for info in serial.tools.list_ports.comports():
        kind = classify(info.vid)
        if kind == "uart":
            desc = UART_BRIDGES[info.vid]
        elif kind == "native":
            desc = info.product or "Espressif"
        else:
            desc = info.description or ""
            desc = desc.replace(f"({info.device})", "").strip()
        found.append(PortInfo(info.device, kind, desc))
    order = {"native": 0, "uart": 1, "other": 2}
    return sorted(found, key=lambda p: (order[p.kind], _sort_key(p.device)))
