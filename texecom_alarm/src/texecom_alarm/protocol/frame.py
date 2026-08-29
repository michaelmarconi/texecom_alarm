"""Connect-protocol frame encode/decode (ADR-019: unexpected bytes fault, not resync)."""

from __future__ import annotations

from dataclasses import dataclass

from texecom_alarm.protocol.crc import crc8

HEADER_START = ord("t")
TYPE_COMMAND = ord("C")
TYPE_RESPONSE = ord("R")
TYPE_MESSAGE = ord("M")
HEADER_LEN = 4

CMD_LOGIN = 1
CMD_GET_ZONE_STATE = 2
CMD_GETZONEDETAILS = 3
CMD_SET_AREA_ARM = 6
CMD_SET_AREA_DISARM = 8
CMD_GET_AREA_FLAGS = 11
CMD_GETPANELIDENTIFICATION = 22
CMD_GETDATETIME = 23
CMD_SETEVENTMESSAGES = 37

# GetAreaFlags: Elite 88 uses area_size=1 and requests this many flag indices.
AREA_FLAGS_COUNT = 72
# zone_count → number of areas (bits in the area bitmap); from observed areaMap (SPIKE-007).
AREA_MAP = {12: 2, 24: 2, 48: 4, 64: 4, 88: 8, 168: 16, 640: 64}

# Unsolicited 'M' frame subtypes (first body byte after SETEVENTMESSAGES).
MSG_DEBUG = 0
MSG_ZONE = 1
MSG_AREA = 2
MSG_OUTPUT = 3
MSG_USER = 4
MSG_LOG = 5

ACK = 0x06
NAK = 0x15

# GetZoneState batches at most this many zones per request (observed add-on).
MAX_ZONES_PER_STATE_REQUEST = 168


@dataclass(frozen=True, slots=True)
class Frame:
    msg_type: int
    sequence: int
    body: bytes


def encode_frame(msg_type: int, sequence: int, body: bytes) -> bytes:
    """Build a full wire frame (header + body + CRC)."""
    length = len(body) + HEADER_LEN + 1
    if not (0 <= length <= 255):
        raise ValueError(f"frame length {length} out of range")
    if not (0 <= sequence <= 255):
        raise ValueError(f"sequence {sequence} out of range")
    header = bytes([HEADER_START, msg_type, length, sequence])
    without_crc = header + body
    return without_crc + bytes([crc8(without_crc)])


def encode_command(cmd: int, body: bytes = b"", *, sequence: int) -> bytes:
    """Encode a command frame with command byte prefixed to body."""
    return encode_frame(TYPE_COMMAND, sequence, bytes([cmd]) + body)


def try_decode_frame(buf: bytearray | bytes) -> tuple[Frame | None, int]:
    """Try to decode one frame from the front of ``buf``.

    Returns ``(frame, consumed)``:
    - valid frame → ``(Frame, frame_length)``
    - need more bytes → ``(None, 0)``
    - non-conforming leading byte / bad length / bad CRC → ``(None, 1)``;
      the caller treats this as a session fault and reconnects rather than
      skipping past it (ADR-019).
    """
    if len(buf) >= 3 and bytes(buf[:3]) == b"+++":
        # Forced-disconnect signal — treat as needing caller attention by
        # consuming the marker without returning a frame. Checked ahead of
        # the HEADER_LEN wait below: the 3-byte marker must be recognised on
        # its own, not only once a 4th byte happens to arrive afterwards
        # (e.g. from a same-sequence retry) — a session ending with exactly
        # these 3 bytes and nothing else must still end the session promptly.
        return None, 3

    if len(buf) < HEADER_LEN:
        return None, 0

    if buf[0] != HEADER_START:
        return None, 1

    msg_type = buf[1]
    msg_length = buf[2]
    msg_seq = buf[3]

    if not (HEADER_LEN + 1 <= msg_length <= 255):
        return None, 1

    if len(buf) < msg_length:
        return None, 0

    frame_bytes = bytes(buf[:msg_length])
    body = frame_bytes[HEADER_LEN:-1]
    msg_crc = frame_bytes[-1]
    if msg_crc != crc8(frame_bytes[:-1]):
        return None, 1

    if msg_type not in (TYPE_COMMAND, TYPE_RESPONSE, TYPE_MESSAGE):
        return None, 1

    return Frame(msg_type=msg_type, sequence=msg_seq, body=body), msg_length
