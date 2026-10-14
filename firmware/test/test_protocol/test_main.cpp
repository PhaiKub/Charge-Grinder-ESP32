// Protocol parser tests; run on the PC with: pio test -e native
#include <unity.h>

#include "protocol.h"

using namespace proto;

void setUp() {}
void tearDown() {}

static int feedAll(Parser &parser, const uint8_t *data, size_t n) {
  int last = 0;
  for (size_t i = 0; i < n; i++) {
    int r = parser.feed(data[i]);
    if (r != 0)
      last = r;
  }
  return last;
}

static void test_crc8_check_value() {
  const uint8_t s[] = "123456789";
  TEST_ASSERT_EQUAL_HEX8(0xF4, crc8(s, 9));
}

// Bytes produced by host/cg_esp32/protocol.py:
//   encode_request(7, Cmd.GLIDE_ABS, p_glide(100, 200, 300))
static const uint8_t kGlide[] = {0xA5, 0x07, 0x12, 0x06, 0x64, 0x00,
                                 0xC8, 0x00, 0x2C, 0x01, 0x13};

static void test_parses_frame_from_host() {
  Parser parser;
  const uint8_t noise[] = {0x00, 0x13, 0x5A};
  TEST_ASSERT_EQUAL(0, feedAll(parser, noise, sizeof(noise)));
  TEST_ASSERT_EQUAL(1, feedAll(parser, kGlide, sizeof(kGlide)));
  TEST_ASSERT_EQUAL(7, parser.frame.seq);
  TEST_ASSERT_EQUAL(GLIDE_ABS, parser.frame.cmd);
  TEST_ASSERT_EQUAL(100, u16(parser.frame.payload));
  TEST_ASSERT_EQUAL(200, u16(parser.frame.payload + 2));
  TEST_ASSERT_EQUAL(300, u16(parser.frame.payload + 4));
}

static void test_bad_crc_reports_seq_and_recovers() {
  Parser parser;
  uint8_t bad[sizeof(kGlide)];
  for (size_t i = 0; i < sizeof(bad); i++)
    bad[i] = kGlide[i];
  bad[sizeof(bad) - 1] ^= 0xFF;
  TEST_ASSERT_EQUAL(-1, feedAll(parser, bad, sizeof(bad)));
  TEST_ASSERT_EQUAL(BAD_CRC, parser.error);
  TEST_ASSERT_EQUAL(7, parser.frame.seq);
  TEST_ASSERT_EQUAL(1, feedAll(parser, kGlide, sizeof(kGlide)));
}

static void test_oversized_length_is_rejected() {
  Parser parser;
  const uint8_t big[] = {SYNC_REQ, 1, PING, MAX_PAYLOAD + 1};
  TEST_ASSERT_EQUAL(-1, feedAll(parser, big, sizeof(big)));
  TEST_ASSERT_EQUAL(BAD_LEN, parser.error);
}

static void test_reply_layout() {
  uint8_t out[5 + MAX_PAYLOAD];
  const uint8_t payload[] = {1, 'x'};
  size_t n = buildReply(out, 9, OK, payload, 2);
  TEST_ASSERT_EQUAL(7, n);
  TEST_ASSERT_EQUAL_HEX8(SYNC_REPLY, out[0]);
  TEST_ASSERT_EQUAL(9, out[1]);
  TEST_ASSERT_EQUAL_HEX8(crc8(out + 1, 5), out[6]);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_crc8_check_value);
  RUN_TEST(test_parses_frame_from_host);
  RUN_TEST(test_bad_crc_reports_seq_and_recovers);
  RUN_TEST(test_oversized_length_is_rejected);
  RUN_TEST(test_reply_layout);
  return UNITY_END();
}
