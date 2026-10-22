<div align="center">
  <h1>Charge-Grinder-ESP32</h1>
  <p><b>A Limbus Company Mirror Dungeon bot that moves the mouse and types through an ESP32 USB HID board.</b></p>
  <p><i>A rewrite of <a href="https://github.com/Walpth/Charge-Grinder">Walpth/Charge-Grinder</a>, and the successor of my earlier ESP32 port, Activision</i></p>
</div>

---

> ⚠️ **Use at your own risk.** Using a bot may break Limbus Company's terms of service, and what happens to your account is on you. This project isn't affiliated with Project Moon and comes with no warranty (see `LICENSE`).

> **Status: early.** The bot code from Charge-Grinder v3.5.5 runs on the ESP32 input backend and has completed a Mirror Dungeon run on an ESP32-S3. The ESP32-S2 (LOLIN S2 Mini) is untested. **Windows only.**

---

## 🔄 Coming from Activision?

Activision was my first ESP32 port of Charge-Grinder. It worked, but it had too many problems (slow input, USB drops, version lock-ups) to keep patching, so I started over on a new codebase. **Charge-Grinder-ESP32 (Charge-Grinder-ESP32-Edition) replaces it**: the bot is taken fresh from Charge-Grinder v3.5.5 and runs on new firmware and a new device layer. Activision is now private, and new releases happen here.

What's new:

* **One file to download.** `Charge-Grinder-ESP32.exe` with the board firmware inside. No Python needed.
* **Flash with one cable.** The app flashes over the COM (UART) port, or over the native USB port alone.
* **More boards.** ESP32-S3 DevKitC-1, 1-port ESP32-S3 boards and the LOLIN S2 Mini.
* **Absolute mouse.** The board puts the pointer exactly where it's sent, so Windows pointer speed and acceleration don't matter and are never changed.
* **Survives a loose cable.** If the USB cable comes out mid-run, the bot pauses and carries on once the board is back.
* **Status LED switch.** Turn the board's light off from the app.

> The Activision firmware speaks a different protocol, so this app won't find a board that still runs it. Flash this project's firmware once (see [Firmware Setup](#-firmware-setup)).

---

## 💖 Support the Project

Honestly, I'd love to test and support more boards (the LOLIN S2 Mini is still untested). However, due to limited budget and the high price of hardware in my country, I can't do it alone. Every contribution goes directly toward buying new development boards to further improve this project.

Thank you so much for your support! 🙏

* [Donate via Ko-fi](https://ko-fi.com/phaikub)
* [Donate via EasyDonate](https://easydonate.app/phaikub_990l)

---

## 🔌 Boards & USB Ports

The board needs a native USB port that can act as a mouse and keyboard (USB-OTG).

| Board | Chip | USB ports | Notes |
|-------|------|-----------|-------|
| **ESP32-S3 DevKitC-1** | ESP32-S3 | 2 (USB + COM) | Runs the bot on USB, flashes on COM (or USB) |
| **1-port ESP32-S3 boards** (Super Mini, Zero, ...) | ESP32-S3 | 1 | One port runs the bot and flashes |
| **LOLIN S2 Mini** | ESP32-S2 | 1 | ⚠️ Untested |
| Classic ESP32, ESP32-C3, ESP32-C6 | — | — | ❌ Can't work: no USB-OTG, so no HID mouse/keyboard |

The ESP32-S3 DevKitC-1 has **two separate USB ports** used for different purposes:

| Port | Role | When to use |
|------|------|-------------|
| 🔵 **USB** (Native OTG) | Runs the bot: commands in, HID mouse & keyboard out | Every normal session |
| 🟡 **COM** (UART, CH340/CP210x) | Flashes the firmware with esptool | First-time setup or firmware update (optional: USB can flash too) |

> Always run the bot on the **USB (Native OTG)** port. The app's bot port list leaves UART ports out on purpose: opening one resets the chip.
> On 1-port boards the single USB port does both jobs.

---

## ⚡ Firmware Setup

### Option A — Flash from the App (Recommended)

The firmware is **already bundled inside `Charge-Grinder-ESP32.exe`**, so there's nothing to compile or download separately.

1. Plug in the board.
2. Launch `Charge-Grinder-ESP32.exe`. The app starts on the main page and opens the **Board** page by itself only when something is wrong (no board found, or no answer). Open it any time with the **BOARD** button in the title bar.
3. Pick your **Board**, then the flash port:
   * DevKitC-1: the **COM** (UART) port, or the **USB** port if that's your only cable.
   * 1-port ESP32-S3 boards and the S2 Mini: the **USB** port.
4. Click **⚡ Flash Firmware** and don't unplug the board until it's done. The app reconnects by itself afterwards.

Flashing over the **USB (native) port**: the app restarts the board into download mode (the Arduino 1200-baud reset) and flashes it there, even if it comes back on another COM number. If the board doesn't restart, put it in download mode by hand: hold **BOOT** (**0** on the S2 Mini), press and release **RST**, release **BOOT**, then **Re-scan** and **Flash** again. The S2 Mini needs a press of **RST** when flashing is done.

When the app carries newer firmware than the board, the **BOARD** button turns gold and the Board page shows **Firmware Update Available**. The bot still works, so flash when convenient.

### Option B — Build & Flash with PlatformIO (for rebuilding firmware)

```powershell
# Install PlatformIO (once)
uv tool install --python 3.12 platformio

cd firmware
pio test -e native          # protocol tests on the PC, no board needed
pio run                     # build every board (esp32s3, lolin_s2_mini)
```

Each build writes `firmware/dist/<env>.bin` (one merged image, flashed at 0x0) and `<env>.json` with its version. The app flashes from there when you run it from source, and the exe build bundles them.

Flashing straight from PlatformIO still works:

```powershell
pio run -e esp32s3 -t upload --upload-port COM6   # the UART (COM) port
```

There's also an `esp32s3-debug` env that prints ESP-IDF/Arduino logs on the UART port.

### LED Status Indicators

| Color | Meaning |
|-------|---------|
| 🟡 Blinking Yellow | Booting |
| 🟣 Solid Purple | Ready — waiting for the app |
| 🔵 Solid Blue | Active — the app is connected and sending commands |
| 🟢 Blinking Green | Idle — connected, but no commands for more than 5 s |
| 🔴 Red Flash | Error — a command frame was rejected (bad CRC, length or command) |

The `esp32s3` image drives a WS2812 RGB LED on GPIO 48 (the DevKitC-1's). The S2 Mini has a plain blue LED on GPIO 15, which shows only on/off and the blinks.

Don't want the light? Switch **Status LED** to **OFF** on the Board page (firmware **0.3.0+**). The board remembers the setting in its flash, so it stays off after a restart.

---

## 🚀 Running the Bot

### For Users
1. Download `Charge-Grinder-ESP32.exe` from the [Releases](https://github.com/PhaiKub/Charge-Grinder-ESP32/releases) page. It's a single Windows file with the board firmware inside; no Python needed.
2. Plug in your board via the **USB (Native OTG)** 🔵 port.
3. Keep **Limbus Company** running in English, windowed or fullscreen at 16:9 (`1920×1080` or `1280×720`), on the **primary monitor**. The board moves the pointer in absolute coordinates over the primary monitor only.
4. Launch `Charge-Grinder-ESP32.exe`. The app scans for the board in the background:
   * **Found:** the **BOARD** button turns cyan (gold if a firmware update is waiting).
   * **Not found:** the Board page opens: pick the port and **Connect**, or use **⚡ Flash Firmware** if the board has no firmware yet.
5. Configure your team and click **Start**.

> 🔌 **Cable came out mid-run?** The bot pauses and shows *USB board disconnected*. Plug the board back in and it carries on by itself. **Stop** still works while it waits.

### For Developers
Run from source on Windows with [uv](https://docs.astral.sh/uv/):

```powershell
git clone https://github.com/PhaiKub/Charge-Grinder-ESP32.git
cd Charge-Grinder-ESP32
uv run --with-requirements requirements.txt python App.py
```

The Board page flashes from `firmware/dist/`, so build the firmware first ([Option B](#option-b--build--flash-with-platformio-for-rebuilding-firmware)) if you want to flash from source.

Host tests:

```powershell
pip install -r requirements-dev.txt
pytest
```

To build the standalone exe (on Windows, via Nuitka):

```powershell
# Bundles the images in firmware/dist; add --firmware to run `pio run` first
uv run --with-requirements requirements-build.txt python release/build_windows.py
# Output: build/Charge-Grinder-ESP32.exe
# --console builds build/Charge-Grinder-ESP32-console.exe, with a console for logs
```

### CI & Releases

GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the host tests and builds the firmware on every push to `main` and every pull request. Pushing a `v*` tag also builds the exe and publishes a GitHub Release with `Charge-Grinder-ESP32.exe` and the firmware images (`firmware-<env>-<version>.bin`):

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The tag must match the `version` file (CI stops the release otherwise); the app compares that version with the latest release and shows an update button when a newer one is out. Running the workflow by hand builds the exe as a download without releasing.

---

## 🔗 How It Talks to the Board

One USB cable to the board's **native USB (OTG)** port carries both a serial port (commands in) and a HID mouse + keyboard (input out). Commands are small binary frames with a CRC. The app waits for each reply before sending the next command (more than one in flight stalls the board's USB, see the protocol doc), which takes about 2 ms, and the board does the timing-sensitive parts itself (click hold, key hold, glides). The mouse uses absolute coordinates, so Windows pointer speed and acceleration settings don't matter and are never changed. See [docs/protocol.md](docs/protocol.md).

## 🗂️ Layout

```
App.py, Bot.py       the app (PySide6 UI) and bot entry, from the original
stats.py             turns game.log into game.csv, from the original
source/              bot logic (battle, shop, teams, …), from the original
  utils/os_esp32_backend.py   moveTo/click/press/… sent through the board
source_app/          UI helpers, from the original; device_panel.py (the Device
                     page: connect, status, LED switch, flash) and check_device.py are new
ImageAssets/         template images and UI assets, from the original
firmware/            board firmware (PlatformIO, Arduino core), one env per board
  src/               main.cpp, protocol.h, pointer.* (abs + rel mouse HID), led.h
  scripts/           merge_bin.py: writes dist/<env>.bin, the image the app flashes
  test/              protocol tests that run on the PC (pio test -e native)
host/cg_esp32/       Python package used by the app
  protocol.py        frame encode/decode, kept in sync with firmware/src/protocol.h
  keys.py            the single HID key table
  device/            InputDevice interface, Esp32Device, MockDevice
    keeper.py        keeps the board open; pauses the bot while it's unplugged
  boards.py          supported boards, firmware images, USB port detection
  flasher.py         flashes dist/<env>.bin with esptool (COM, or USB via download mode)
  motion/            human-like paths (from the original) replayed as absolute moves
release/
  build_windows.py   builds build/Charge-Grinder-ESP32.exe (Nuitka) with the firmware inside
docs/protocol.md     serial protocol spec
tests/               host tests (pytest), including a fake firmware
tools/               checks on a real board: smoke_test.py, stress.py, motion_demo.py
.github/workflows/ci.yml   tests + firmware on pushes to main and PRs; release on v* tags
requirements.txt     app dependencies (requirements-dev.txt adds pytest,
                     requirements-build.txt the exe build tools)
version              app version, compared with the latest release
```

---

## 📜 License & Credits

This project is licensed under the **GNU General Public License v3.0**, same as the original. See `LICENSE` for details.

- **Original Framework:** [Walpth/Charge-Grinder](https://github.com/Walpth/Charge-Grinder) by **Walpth** (GPL-3.0). The bot code, UI and image assets come from Charge-Grinder v3.5.5, and the human-like mouse paths are Walpth's work too ([trainer](https://github.com/Walpth/ideal-mouse-movements)).
- **Earlier ESP32 Port:** Activision by PhaiKub & Colors (now private), which this project replaces.
- **ESP32 Edition:** Developed by PhaiKub (2026). New firmware and binary serial protocol, the ESP32 input backend with absolute mouse moves, more boards, the Board page with built-in firmware flasher and LED switch, and pausing through a lost USB connection.
