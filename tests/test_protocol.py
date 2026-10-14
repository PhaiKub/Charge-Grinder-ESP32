from cg_esp32 import protocol as p


def test_crc8_check_value():
    # Standard check value for CRC-8/ATM ("123456789").
    assert p.crc8(b"123456789") == 0xF4


def test_request_layout():
    frame = p.encode_request(7, p.Cmd.MOVE_ABS, p.p_xy(1, 2))
    assert frame[:4] == bytes((0xA5, 7, 0x10, 4))
    assert frame[4:8] == bytes((1, 0, 2, 0))
    assert frame[-1] == p.crc8(frame[1:-1])


def test_parser_handles_split_and_garbage():
    a = p.encode_reply(1, p.Status.OK)
    b = p.encode_reply(2, p.Status.OK, b"hi")
    parser = p.ReplyParser()
    stream = b"\x00\x5a\x13" + a + b
    out = []
    for i in range(len(stream)):
        out += parser.feed(stream[i:i + 1])
    assert [(r.seq, r.payload) for r in out] == [(1, b""), (2, b"hi")]


def test_parser_skips_bad_crc():
    bad = bytearray(p.encode_reply(1, p.Status.OK))
    bad[-1] ^= 0xFF
    good = p.encode_reply(2, p.Status.OK)
    assert [r.seq for r in p.ReplyParser().feed(bytes(bad) + good)] == [2]
