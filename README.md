# Charge-Grinder-ESP32-Edition

A rewrite of [Charge-Grinder](https://github.com/Walpth/Charge-Grinder) by Walpth
that drives the mouse and keyboard through an **ESP32-S3** acting as a USB HID
device, instead of a mouse-driver DLL.

- Platform: **Windows**
- Board: **ESP32-S3** (DevKitC-1 style, native USB + onboard WS2812 on GPIO 48)
- License: GPL-3.0, same as the original

> Status: early scaffold. The device layer and protocol are in place; the bot
> logic has not been ported yet.

## Layout

```
firmware/            ESP32-S3 firmware (PlatformIO, Arduino core)
  src/               main.cpp, protocol.h, pointer.* (abs + rel mouse HID), led.h
  test/              protocol tests that run on the PC (pio test -e native)
host/cg_esp32/       Python package used by the app
  protocol.py        frame encode/decode, kept in sync with firmware/src/protocol.h
  keys.py            the single HID key table
  device/            InputDevice interface, Esp32Device, MockDevice
  motion/            human-like paths (from the original) replayed as absolute moves
assets/              images used by the app (to be moved over from the original)
docs/protocol.md     serial protocol spec
tests/               host tests (pytest), including a fake firmware
```

Planned next, as the original code is ported:
`vision/`, `bot/` (battle, shop, teams, …), `ui/`.

## How it talks to the board

One USB cable to the board's **native USB (OTG)** port carries both a serial
port (commands in) and a HID mouse + keyboard (input out). Commands are small
binary frames with a CRC; the app keeps up to 8 in flight instead of waiting for
each reply, and the board does the timing-sensitive parts itself (click hold,
key hold, glides). The mouse uses absolute coordinates, so Windows pointer speed
and acceleration settings don't matter and are never changed. See
[docs/protocol.md](docs/protocol.md).

## Firmware

```powershell
pip install platformio
cd firmware
pio test -e native          # protocol tests on the PC
pio run -e esp32s3          # build
pio run -e esp32s3 -t upload   # flash through the board's COM/UART port
```

## Host tests

```powershell
pip install -r requirements-dev.txt
pytest
```

## Credits

Original bot by **Walpth** — <https://github.com/Walpth/Charge-Grinder>.
