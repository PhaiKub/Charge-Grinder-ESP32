# Charge-Grinder-ESP32-Edition

A rewrite of [Charge-Grinder](https://github.com/Walpth/Charge-Grinder) by Walpth
that drives the mouse and keyboard through an **ESP32-S3** acting as a USB HID
device, instead of a mouse-driver DLL.

- Platform: **Windows**
- Boards: **ESP32-S3** (DevKitC-1 with 2 USB ports, or 1-port boards such as
  Super Mini) and **ESP32-S2** (LOLIN S2 Mini). The board needs a native USB
  port, so the classic ESP32 and ESP32-C3/C6 can't be used.
- License: GPL-3.0, same as the original

> Status: early. The bot code from Charge-Grinder v3.5.3 runs on top of the
> ESP32 input backend (`source/utils/os_esp32_backend.py`) and has completed a
> Mirror Dungeon run on an ESP32-S3. ESP32-S2 support is untested.

The game window must be on the **primary monitor**: the board moves the pointer
in absolute coordinates over that screen only.

## Layout

```
App.py, Bot.py       the app (PySide6 UI) and bot entry, from the original
source/              bot logic (battle, shop, teams, …), from the original
  utils/os_esp32_backend.py   moveTo/click/press/… sent through the board
source_app/          UI helpers, from the original; device_dialog.py (connect,
                     status, flash firmware) and check_device.py are new
ImageAssets/         template images and UI assets, from the original
firmware/            board firmware (PlatformIO, Arduino core), one env per board
  src/               main.cpp, protocol.h, pointer.* (abs + rel mouse HID), led.h
  scripts/           merge_bin.py: writes dist/<env>.bin, the image the app flashes
  test/              protocol tests that run on the PC (pio test -e native)
host/cg_esp32/       Python package used by the app
  protocol.py        frame encode/decode, kept in sync with firmware/src/protocol.h
  keys.py            the single HID key table
  device/            InputDevice interface, Esp32Device, MockDevice
  boards.py          supported boards, firmware images, USB port detection
  flasher.py         flashes dist/<env>.bin with esptool
  motion/            human-like paths (from the original) replayed as absolute moves
docs/protocol.md     serial protocol spec
tests/               host tests (pytest), including a fake firmware
```

## How it talks to the board

One USB cable to the board's **native USB (OTG)** port carries both a serial
port (commands in) and a HID mouse + keyboard (input out). Commands are small
binary frames with a CRC. The app waits for each reply before sending the next
command (more than one in flight stalls the board's USB, see the protocol doc),
which takes about 2 ms, and the board does the timing-sensitive parts itself (click hold,
key hold, glides). The mouse uses absolute coordinates, so Windows pointer speed
and acceleration settings don't matter and are never changed. See
[docs/protocol.md](docs/protocol.md).

## Firmware

Build the images once with PlatformIO; each build also writes
`firmware/dist/<env>.bin` and `<env>.json`, which the app flashes:

```powershell
uv tool install --python 3.12 platformio
cd firmware
pio test -e native          # protocol tests on the PC
pio run                     # build every board (esp32s3, lolin_s2_mini)
```

Then flash from the app: the device window opens at startup (and from the dot
next to the title on the main window). Pick the board and the flash port, then
**Flash Firmware**.

- 2-port boards (ESP32-S3 DevKitC-1): flash through the **COM/UART** port; the
  bot runs on the **USB** (native) port.
- 1-port boards: put the board in download mode first (hold BOOT/0, press RST,
  release), Re-scan, pick the port, then Flash.

Flashing from PlatformIO still works:
`pio run -e esp32s3 -t upload --upload-port COM6` (the UART port).

## Run the app

```powershell
uv run --with-requirements requirements.txt python App.py
```

## Host tests

```powershell
pip install -r requirements-dev.txt
pytest
```

## Credits

Original bot by **Walpth** — <https://github.com/Walpth/Charge-Grinder>.
