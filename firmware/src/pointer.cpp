#include "pointer.h"

#if CONFIG_TINYUSB_HID_ENABLED

namespace {

constexpr uint8_t REPORT_ABS = 0x10;
constexpr uint8_t REPORT_REL = 0x11;

// clang-format off
const uint8_t kDescriptor[] = {
  // ── Absolute mouse ──
  0x05, 0x01, 0x09, 0x02, 0xA1, 0x01,       // Generic Desktop / Mouse / Application
  0x85, REPORT_ABS,
  0x09, 0x01, 0xA1, 0x00,                   //   Pointer / Physical
  0x05, 0x09, 0x19, 0x01, 0x29, 0x03,       //     Buttons 1-3
  0x15, 0x00, 0x25, 0x01, 0x95, 0x03, 0x75, 0x01, 0x81, 0x02,
  0x95, 0x01, 0x75, 0x05, 0x81, 0x03,       //     padding
  0x05, 0x01, 0x09, 0x30, 0x09, 0x31,       //     X, Y
  0x15, 0x00, 0x26, 0xFF, 0x7F,             //     0..32767
  0x75, 0x10, 0x95, 0x02, 0x81, 0x02,       //     absolute
  0x09, 0x38, 0x15, 0x81, 0x25, 0x7F,       //     Wheel -127..127
  0x75, 0x08, 0x95, 0x01, 0x81, 0x06,       //     relative
  0xC0, 0xC0,
  // ── Relative mouse ──
  0x05, 0x01, 0x09, 0x02, 0xA1, 0x01,
  0x85, REPORT_REL,
  0x09, 0x01, 0xA1, 0x00,
  0x05, 0x09, 0x19, 0x01, 0x29, 0x03,
  0x15, 0x00, 0x25, 0x01, 0x95, 0x03, 0x75, 0x01, 0x81, 0x02,
  0x95, 0x01, 0x75, 0x05, 0x81, 0x03,
  0x05, 0x01, 0x09, 0x30, 0x09, 0x31,
  0x15, 0x81, 0x25, 0x7F, 0x75, 0x08, 0x95, 0x02, 0x81, 0x06,
  0xC0, 0xC0,
};
// clang-format on

} // namespace

Pointer::Pointer() {
  static bool added = false;
  if (!added) {
    added = true;
    USBHID::addDevice(this, sizeof(kDescriptor));
  }
}

void Pointer::begin() { hid_.begin(); }

uint16_t Pointer::_onGetDescriptor(uint8_t *buffer) {
  memcpy(buffer, kDescriptor, sizeof(kDescriptor));
  return sizeof(kDescriptor);
}

bool Pointer::sendAbs(int8_t wheel) {
  uint8_t r[6] = {buttons_, (uint8_t)x_, (uint8_t)(x_ >> 8), (uint8_t)y_, (uint8_t)(y_ >> 8),
                  (uint8_t)wheel};
  return hid_.SendReport(REPORT_ABS, r, sizeof(r));
}

bool Pointer::sendRel(int8_t dx, int8_t dy) {
  uint8_t r[3] = {buttons_, (uint8_t)dx, (uint8_t)dy};
  return hid_.SendReport(REPORT_REL, r, sizeof(r));
}

bool Pointer::moveAbs(uint16_t x, uint16_t y) {
  x_ = x > ABS_MAX ? ABS_MAX : x;
  y_ = y > ABS_MAX ? ABS_MAX : y;
  return sendAbs();
}

bool Pointer::moveRel(int16_t dx, int16_t dy) {
  bool ok = true;
  while (dx || dy) {
    int8_t sx = dx > 127 ? 127 : dx < -127 ? -127 : dx;
    int8_t sy = dy > 127 ? 127 : dy < -127 ? -127 : dy;
    ok &= sendRel(sx, sy);
    dx -= sx;
    dy -= sy;
  }
  return ok;
}

bool Pointer::scroll(int8_t wheel) { return sendAbs(wheel); }

bool Pointer::press(uint8_t mask) {
  buttons_ |= (mask & 0x07);
  return sendAbs();
}

bool Pointer::release(uint8_t mask) {
  buttons_ &= ~mask;
  return sendAbs();
}

#endif
