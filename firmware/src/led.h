// Onboard status LED. The board's env in platformio.ini sets the pin:
//   LED_PIN  GPIO of the LED, -1 for none (default 48, ESP32-S3-DevKitC-1)
//   LED_RGB  1 = WS2812 RGB LED, 0 = plain single-colour LED (on/off only)
// Colours (a plain LED shows only on/off and the blinks):
//   yellow blink  booting
//   purple        ready, no host yet
//   blue          host said HELLO, commands flowing
//   green blink   host connected but idle > 5 s
//   red flash     a frame was rejected (bad CRC / length / command)
// The app can switch the LED off (SET_LED); main.cpp keeps that in flash.
#pragma once
#include <Arduino.h>

#ifndef LED_PIN
#define LED_PIN 48
#endif
#ifndef LED_RGB
#define LED_RGB 1
#endif

class StatusLed {
public:
  enum State { BOOTING, READY, ACTIVE, ERROR };

  void set(State s) {
    if (s == ERROR)
      errorAt_ = millis();
    else
      state_ = s;
  }
  void enable(bool on) { enabled_ = on; }

  void activity() {
    lastActivity_ = millis();
    if (state_ == READY)
      state_ = ACTIVE;
  }

  void update() {
    if (!enabled_)
      return write(0, 0, 0);
    unsigned long now = millis();
    if (errorAt_ && now - errorAt_ < 200)
      return write(B, 0, 0);
    errorAt_ = 0;
    bool blink = (now / 500) % 2;
    switch (state_) {
    case BOOTING:
      return write(blink ? B : 0, blink ? B / 2 : 0, 0);
    case READY:
      return write(B / 2, 0, B);
    case ACTIVE:
      if (now - lastActivity_ > 5000)
        return write(0, blink ? B : B / 6, 0);
      return write(0, 0, B);
    default:
      return;
    }
  }

private:
  static constexpr uint8_t B = 10;

  void write(uint8_t r, uint8_t g, uint8_t b) {
    if (r == r_ && g == g_ && b == b_)
      return; // only touch the RMT peripheral on a real change
    r_ = r, g_ = g, b_ = b;
#if LED_PIN >= 0
#if LED_RGB
    neopixelWrite(LED_PIN, r, g, b);
#else
    static bool ready = false;
    if (!ready) {
      pinMode(LED_PIN, OUTPUT);
      ready = true;
    }
    digitalWrite(LED_PIN, (r | g | b) ? HIGH : LOW);
#endif
#endif
  }

  bool enabled_ = true;
  State state_ = BOOTING;
  unsigned long lastActivity_ = 0;
  unsigned long errorAt_ = 0;
  uint8_t r_ = 1, g_ = 1, b_ = 1;
};
