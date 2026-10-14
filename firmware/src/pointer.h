// Composite pointer HID device: one absolute mouse report and one relative
// mouse report, sharing a single button state so the two never disagree.
#pragma once
#include "USBHID.h"

class Pointer : public USBHIDDevice {
public:
  static constexpr uint16_t ABS_MAX = 32767;

  Pointer();
  void begin();
  uint16_t _onGetDescriptor(uint8_t *buffer) override;

  bool moveAbs(uint16_t x, uint16_t y);
  bool moveRel(int16_t dx, int16_t dy); // splits into ±127 steps
  bool scroll(int8_t wheel);
  bool press(uint8_t mask);
  bool release(uint8_t mask);
  bool releaseAll() { return release(0xFF); }

  uint16_t x() const { return x_; }
  uint16_t y() const { return y_; }

private:
  bool sendAbs(int8_t wheel = 0);
  bool sendRel(int8_t dx, int8_t dy);

  USBHID hid_;
  uint8_t buttons_ = 0;
  uint16_t x_ = ABS_MAX / 2;
  uint16_t y_ = ABS_MAX / 2;
};
