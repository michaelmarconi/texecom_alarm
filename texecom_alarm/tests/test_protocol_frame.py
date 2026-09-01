"""Unit tests for Connect-protocol CRC-8 and frame encode/decode."""

from __future__ import annotations

import pytest

from texecom_alarm.protocol.crc import crc8
from texecom_alarm.protocol.frame import (
    HEADER_START,
    TYPE_COMMAND,
    TYPE_MESSAGE,
    TYPE_RESPONSE,
    Frame,
    decode_miss_detail,
    encode_command,
    encode_frame,
    try_decode_frame,
)


def test_crc8_matches_known_login_frame() -> None:
    # LOGIN cmd=1 body="1234" seq=0 → length = 5 + 5 = 10
    header_and_body = bytes([HEADER_START, TYPE_COMMAND, 10, 0, 1]) + b"1234"
    assert crc8(header_and_body) == 0x34


def test_encode_command_builds_valid_frame() -> None:
    frame = encode_command(cmd=1, body=b"1234", sequence=0)
    assert frame[0] == HEADER_START
    assert frame[1] == TYPE_COMMAND
    assert frame[2] == len(frame)
    assert frame[3] == 0
    assert frame[4] == 1
    assert frame[5:9] == b"1234"
    assert frame[-1] == crc8(frame[:-1])


def test_encode_decode_round_trip() -> None:
    raw = encode_frame(TYPE_RESPONSE, sequence=7, body=bytes([1, 0x06]))
    buf = bytearray(raw)
    decoded, consumed = try_decode_frame(buf)
    assert consumed == len(raw)
    assert decoded == Frame(msg_type=TYPE_RESPONSE, sequence=7, body=bytes([1, 0x06]))


def test_try_decode_skips_leading_garbage_byte() -> None:
    good = encode_frame(TYPE_RESPONSE, sequence=1, body=bytes([23, 0x06]))
    buf = bytearray(b"X" + good)
    decoded, consumed = try_decode_frame(buf)
    assert decoded is None
    assert consumed == 1  # discard one non-header byte
    del buf[:consumed]
    decoded, consumed = try_decode_frame(buf)
    assert decoded is not None
    assert decoded.sequence == 1
    assert decoded.body == bytes([23, 0x06])


def test_encode_rejects_overlong_body() -> None:
    with pytest.raises(ValueError, match="frame length"):
        encode_frame(TYPE_COMMAND, sequence=0, body=b"x" * 252)


def test_encode_rejects_bad_sequence() -> None:
    with pytest.raises(ValueError, match="sequence"):
        encode_frame(TYPE_COMMAND, sequence=256, body=b"\x01")


def test_try_decode_forced_disconnect_marker() -> None:
    decoded, consumed = try_decode_frame(bytearray(b"+++junk"))
    assert decoded is None
    assert consumed == 3


def test_try_decode_implausible_length() -> None:
    buf = bytearray([HEADER_START, TYPE_RESPONSE, 3, 0])  # length < header+crc
    assert try_decode_frame(buf) == (None, 1)


def test_try_decode_needs_more_bytes() -> None:
    partial = encode_frame(TYPE_MESSAGE, sequence=0, body=b"\x01\x02")[:-1]
    assert try_decode_frame(bytearray(partial)) == (None, 0)


def test_try_decode_bad_crc() -> None:
    raw = bytearray(encode_frame(TYPE_RESPONSE, sequence=0, body=bytes([1, 0x06])))
    raw[-1] ^= 0xFF
    assert try_decode_frame(raw) == (None, 1)


def test_try_decode_unknown_type_after_valid_crc() -> None:
    body = b"\x01"
    length = len(body) + 5
    header_and_body = bytes([HEADER_START, ord("Z"), length, 0]) + body
    raw = bytearray(header_and_body + bytes([crc8(header_and_body)]))
    assert try_decode_frame(raw) == (None, 1)


def test_decode_miss_reason_not_t_includes_leading_hex() -> None:
    reason, leading_hex = decode_miss_detail(bytearray(b"ATH0\rATZ\r"))
    assert reason == "not 't'"
    assert "41544830" in leading_hex.replace(" ", "")


def test_decode_miss_reason_bad_length() -> None:
    buf = bytearray([HEADER_START, TYPE_RESPONSE, 3, 0])
    reason, leading_hex = decode_miss_detail(buf)
    assert reason == "bad length"
    assert leading_hex.replace(" ", "").startswith("74")


def test_decode_miss_reason_bad_crc() -> None:
    raw = bytearray(encode_frame(TYPE_RESPONSE, sequence=0, body=bytes([1, 0x06])))
    raw[-1] ^= 0xFF
    reason, leading_hex = decode_miss_detail(raw)
    assert reason == "bad CRC"
    assert leading_hex.replace(" ", "").startswith("74")


def test_decode_miss_reason_unknown_type() -> None:
    body = b"\x01"
    length = len(body) + 5
    header_and_body = bytes([HEADER_START, ord("Z"), length, 0]) + body
    raw = bytearray(header_and_body + bytes([crc8(header_and_body)]))
    reason, leading_hex = decode_miss_detail(raw)
    assert reason == "unknown type"
    assert leading_hex.replace(" ", "").startswith("74")


def test_decode_miss_reason_end_of_session_marker_is_distinct() -> None:
    reason, leading_hex = decode_miss_detail(bytearray(b"+++junk"))
    assert reason == "+++"
    assert "2b2b2b" in leading_hex.replace(" ", "")
