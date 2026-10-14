# Serial protocol v1

The ESP32-S3 shows up on one USB cable as two things: a CDC serial port (commands
in) and a composite HID device (absolute mouse, relative mouse, keyboard out).

Everything on the serial link is a binary frame. No text, no `println`.

## Frames

Host → device (request):

| byte | field   | notes                                   |
|------|---------|-----------------------------------------|
| 0    | `0xA5`  | sync                                    |
| 1    | seq     | 0–255, wraps; echoed in the reply       |
| 2    | cmd     | see table below                         |
| 3    | len     | payload length, 0–32                    |
| 4…   | payload | little-endian                           |
| last | crc8    | CRC-8/ATM (poly 0x07, init 0) over seq…payload |

Device → host (reply), one per request:

| byte | field   | notes                          |
|------|---------|--------------------------------|
| 0    | `0x5A`  | sync                           |
| 1    | seq     | the request's seq              |
| 2    | status  | see below                      |
| 3    | len     | payload length                 |
| 4…   | payload |                                |
| last | crc8    | over seq…payload               |

Status: `0` OK, `1` BAD_CRC, `2` BAD_CMD, `3` BAD_LEN, `4` BUSY (queue full).

A frame with a bad CRC is answered with BAD_CRC **when the seq byte is readable**;
the device then resyncs by scanning for the next `0xA5`. It never locks itself.

## Flow control

The protocol allows up to `WINDOW = 8` requests in flight (the largest frame is
37 bytes, so 8 fit the 256-byte CDC RX buffer). Replies are matched by seq.

**The host currently uses 1** (`DEFAULT_WINDOW`). Measured 2026-10-14 on the
ESP32-S3 with Arduino core 2.0.17 (`tools/stress.py`):

| in flight | result |
|-----------|--------|
| 1 | 5000 moves OK, ~2 ms per command (~500/s) |
| 2 | stalls after ~5 commands |
| 8 | stalls after ~100 commands |

In a stall the board keeps reading commands but both USB IN endpoints stop:
`SendReport()` logs "report wait failed" then "not ready", and CDC replies stop.
Only a replug recovers. Likely a TinyUSB/core issue when a HID IN transfer and
CDC traffic overlap. One in flight is fast enough for the bot, so pipelining
stays off until a firmware/core change is shown to survive `tools/stress.py`.

## Commands

| cmd  | name          | payload                              | reply payload            |
|------|---------------|--------------------------------------|--------------------------|
| 0x01 | HELLO         | –                                    | proto u8, fw version (ASCII) |
| 0x02 | PING          | –                                    | –                        |
| 0x10 | MOVE_ABS      | x u16, y u16 (0–32767)               | –                        |
| 0x11 | MOVE_REL      | dx i16, dy i16                       | –                        |
| 0x12 | GLIDE_ABS     | x u16, y u16, duration_ms u16        | –                        |
| 0x20 | BUTTON_DOWN   | mask u8 (1 L, 2 R, 4 M)              | –                        |
| 0x21 | BUTTON_UP     | mask u8                              | –                        |
| 0x22 | CLICK         | mask u8, hold_ms u16                 | –                        |
| 0x23 | SCROLL        | wheel i8                             | –                        |
| 0x30 | KEY_DOWN      | usage u8 (HID usage id)              | –                        |
| 0x31 | KEY_UP        | usage u8                             | –                        |
| 0x32 | KEY_TAP       | usage u8, hold_ms u16                | –                        |
| 0x33 | RELEASE_ALL   | –                                    | –                        |

Notes:

- `MOVE_ABS` uses the absolute-mouse HID collection. Windows maps 0–32767 onto
  the primary monitor, so Windows pointer speed and "Enhance pointer precision"
  have no effect and the host never has to touch those settings.
- `MOVE_REL` splits large deltas into ±127 steps on the device.
- `GLIDE_ABS` moves from the current absolute position to the target over
  `duration_ms`, one report per USB frame (1 ms), with ease-in-out. It replies
  when the pointer has arrived, so the host's `flush()` means the move is done.
- `CLICK` / `KEY_TAP` hold on the device, so timing is not affected by serial
  latency.
- Keys use raw HID usage ids (the same table the original `bridge.py` used), not
  Arduino `KEY_*` values.

## Versioning

`HELLO` returns `PROTO_VERSION`. If it differs from what the host expects, the
host refuses to run and offers to flash. The device keeps answering normally;
there is no hard lock and no auth timeout.
