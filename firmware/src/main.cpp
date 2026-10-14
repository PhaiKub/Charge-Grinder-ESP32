// Charge-Grinder-ESP32-Edition firmware.
// Serial (CDC) in, HID (absolute + relative mouse, keyboard) out, on the
// native USB port. Protocol: docs/protocol.md.
#include <Arduino.h>
#include "USB.h"
#include "USBHIDKeyboard.h"

#include "led.h"
#include "pointer.h"
#include "protocol.h"

#ifndef FW_VERSION
#define FW_VERSION "dev"
#endif
#ifndef FW_BOARD
#define FW_BOARD "unknown"
#endif

using namespace proto;

static Pointer pointer;
static USBHIDKeyboard keyboard;
static StatusLed led;
static Parser parser;

// ── Glide: absolute move spread over time, one report per millisecond ─────
static struct {
  bool active = false;
  uint16_t x0, y0, x1, y1;
  unsigned long start, duration;
} glide;

static float easeInOut(float t) { return t < 0.5f ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t); }

static void glideStep() {
  if (!glide.active)
    return;
  unsigned long elapsed = millis() - glide.start;
  if (elapsed >= glide.duration) {
    glide.active = false;
    pointer.moveAbs(glide.x1, glide.y1);
    return;
  }
  float k = easeInOut((float)elapsed / glide.duration);
  pointer.moveAbs(glide.x0 + (int32_t)((glide.x1 - glide.x0) * k),
                  glide.y0 + (int32_t)((glide.y1 - glide.y0) * k));
}

// Every pointer command runs after any glide in progress, so commands keep
// their order. While we wait here the host is limited by its in-flight window,
// which fits the CDC RX buffer, so nothing overflows.
static void finishGlide() {
  while (glide.active) {
    glideStep();
    led.update();
    delay(1);
  }
}

// ── Replies ───────────────────────────────────────────────────────────────
static void reply(uint8_t seq, uint8_t status, const uint8_t *payload = nullptr,
                  uint8_t len = 0) {
  uint8_t buf[5 + MAX_PAYLOAD];
  size_t n = buildReply(buf, seq, status, payload, len);
  Serial.write(buf, n);
}

static bool needLen(const Frame &f, uint8_t len) {
  if (f.len == len)
    return true;
  reply(f.seq, Status::BAD_LEN);
  led.set(StatusLed::ERROR);
  return false;
}

// ── Command dispatch ─────────────────────────────────────────────────────
static void handle(const Frame &f) {
  const uint8_t *p = f.payload;
  switch (f.cmd) {
  case HELLO: {
    // "<fw version> <board id>", e.g. "0.2.0 esp32s3"; the board id is the
    // PlatformIO env, so the app knows which firmware image fits this board.
    static const char ver[] = FW_VERSION " " FW_BOARD;
    uint8_t out[1 + sizeof(ver)];
    out[0] = VERSION;
    memcpy(out + 1, ver, sizeof(ver) - 1);
    led.set(StatusLed::ACTIVE);
    return reply(f.seq, Status::OK, out, sizeof(ver)); // proto byte + text without NUL
  }
  case PING:
    return reply(f.seq, Status::OK);

  case MOVE_ABS:
    if (!needLen(f, 4)) return;
    finishGlide();
    if (!pointer.moveAbs(u16(p), u16(p + 2)))
      log_w("MOVE_ABS report not sent");
    break;
  case MOVE_REL:
    if (!needLen(f, 4)) return;
    finishGlide();
    pointer.moveRel(i16(p), i16(p + 2));
    break;
  case GLIDE_ABS:
    if (!needLen(f, 6)) return;
    finishGlide();
    glide.x0 = pointer.x();
    glide.y0 = pointer.y();
    glide.x1 = u16(p);
    glide.y1 = u16(p + 2);
    glide.duration = u16(p + 4);
    glide.start = millis();
    glide.active = glide.duration > 0;
    if (!glide.active)
      pointer.moveAbs(glide.x1, glide.y1);
    finishGlide(); // reply only once the pointer has arrived, so host flush() means "done"
    break;

  case BUTTON_DOWN:
    if (!needLen(f, 1)) return;
    finishGlide();
    pointer.press(p[0]);
    break;
  case BUTTON_UP:
    if (!needLen(f, 1)) return;
    finishGlide();
    pointer.release(p[0]);
    break;
  case CLICK:
    if (!needLen(f, 3)) return;
    finishGlide();
    pointer.press(p[0]);
    delay(u16(p + 1));
    pointer.release(p[0]);
    break;
  case SCROLL:
    if (!needLen(f, 1)) return;
    finishGlide();
    pointer.scroll((int8_t)p[0]);
    break;

  case KEY_DOWN:
    if (!needLen(f, 1)) return;
    keyboard.pressRaw(p[0]);
    break;
  case KEY_UP:
    if (!needLen(f, 1)) return;
    keyboard.releaseRaw(p[0]);
    break;
  case KEY_TAP:
    if (!needLen(f, 3)) return;
    keyboard.pressRaw(p[0]);
    delay(u16(p + 1));
    keyboard.releaseRaw(p[0]);
    break;
  case RELEASE_ALL:
    glide.active = false;
    keyboard.releaseAll();
    pointer.releaseAll();
    break;

  default:
    led.set(StatusLed::ERROR);
    return reply(f.seq, Status::BAD_CMD);
  }
  led.activity();
  reply(f.seq, Status::OK);
}

void setup() {
  led.update();
#if CORE_DEBUG_LEVEL > 0
  // Debug builds: core/USB logs and crash dumps go to the UART port.
  Serial0.begin(115200);
  Serial0.setDebugOutput(true);
#endif
  USB.productName("Charge-Grinder-ESP32");
  USB.manufacturerName("Charge-Grinder");
  pointer.begin();
  keyboard.begin();
  USB.begin();
  Serial.begin(115200);
  // A host that stops reading must never stall loop() for long.
  Serial.setTxTimeoutMs(20);
  led.set(StatusLed::READY);
}

void loop() {
  while (Serial.available()) {
    int r = parser.feed((uint8_t)Serial.read());
    if (r == 1) {
      handle(parser.frame);
    } else if (r < 0) {
      led.set(StatusLed::ERROR);
      reply(parser.frame.seq, parser.error);
    }
  }
  glideStep();
  led.update();
  delay(1);
}
