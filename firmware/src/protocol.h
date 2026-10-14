// Serial protocol v1. Spec: docs/protocol.md. Keep in sync with host/cg_esp32/protocol.py.
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace proto {

constexpr uint8_t VERSION = 1;
constexpr uint8_t SYNC_REQ = 0xA5;
constexpr uint8_t SYNC_REPLY = 0x5A;
constexpr uint8_t MAX_PAYLOAD = 32;

enum Cmd : uint8_t {
  HELLO = 0x01,
  PING = 0x02,
  MOVE_ABS = 0x10,
  MOVE_REL = 0x11,
  GLIDE_ABS = 0x12,
  BUTTON_DOWN = 0x20,
  BUTTON_UP = 0x21,
  CLICK = 0x22,
  SCROLL = 0x23,
  KEY_DOWN = 0x30,
  KEY_UP = 0x31,
  KEY_TAP = 0x32,
  RELEASE_ALL = 0x33,
};

enum Status : uint8_t {
  OK = 0,
  BAD_CRC = 1,
  BAD_CMD = 2,
  BAD_LEN = 3,
  BUSY = 4,
};

// CRC-8/ATM: poly 0x07, init 0, no reflection, no xorout.
inline uint8_t crc8(const uint8_t *data, size_t len, uint8_t crc = 0) {
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (int b = 0; b < 8; b++)
      crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
  }
  return crc;
}

inline uint16_t u16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
inline int16_t i16(const uint8_t *p) { return (int16_t)u16(p); }

struct Frame {
  uint8_t seq;
  uint8_t cmd;
  uint8_t len;
  uint8_t payload[MAX_PAYLOAD];
};

// Byte-at-a-time request parser. feed() returns:
//   1  a complete, CRC-valid frame is in `frame`
//  -1  a frame was dropped (bad CRC or bad length); `frame.seq` holds its seq
//   0  need more bytes
class Parser {
public:
  int feed(uint8_t b) {
    switch (state_) {
    case WAIT_SYNC:
      if (b == SYNC_REQ)
        state_ = SEQ;
      return 0;
    case SEQ:
      frame.seq = b;
      state_ = CMD;
      return 0;
    case CMD:
      frame.cmd = b;
      state_ = LEN;
      return 0;
    case LEN:
      if (b > MAX_PAYLOAD) {
        state_ = WAIT_SYNC;
        error = BAD_LEN;
        return -1;
      }
      frame.len = b;
      got_ = 0;
      state_ = b ? PAYLOAD : CRC;
      return 0;
    case PAYLOAD:
      frame.payload[got_++] = b;
      if (got_ == frame.len)
        state_ = CRC;
      return 0;
    case CRC: {
      state_ = WAIT_SYNC;
      uint8_t hdr[3] = {frame.seq, frame.cmd, frame.len};
      uint8_t crc = crc8(frame.payload, frame.len, crc8(hdr, 3));
      if (crc != b) {
        error = BAD_CRC;
        return -1;
      }
      return 1;
    }
    }
    return 0;
  }

  Frame frame{};
  Status error = OK;

private:
  enum State { WAIT_SYNC, SEQ, CMD, LEN, PAYLOAD, CRC } state_ = WAIT_SYNC;
  uint8_t got_ = 0;
};

// Writes a reply frame into out (needs 5 + len bytes). Returns its size.
inline size_t buildReply(uint8_t *out, uint8_t seq, uint8_t status, const uint8_t *payload,
                         uint8_t len) {
  out[0] = SYNC_REPLY;
  out[1] = seq;
  out[2] = status;
  out[3] = len;
  for (uint8_t i = 0; i < len; i++)
    out[4 + i] = payload[i];
  out[4 + len] = crc8(out + 1, 3 + len);
  return 5 + len;
}

} // namespace proto
