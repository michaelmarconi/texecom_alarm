"""Texecom Connect protocol package: framing, CRC, and asyncio panel client."""

from texecom_alarm.protocol.client import ForcedDisconnect, PanelClient, ProtocolError
from texecom_alarm.protocol.crc import crc8
from texecom_alarm.protocol.frame import (
    ACK,
    CMD_GETDATETIME,
    CMD_LOGIN,
    NAK,
    Frame,
    encode_command,
    encode_frame,
    try_decode_frame,
)

__all__ = [
    "ACK",
    "CMD_GETDATETIME",
    "CMD_LOGIN",
    "ForcedDisconnect",
    "Frame",
    "NAK",
    "PanelClient",
    "ProtocolError",
    "crc8",
    "encode_command",
    "encode_frame",
    "try_decode_frame",
]
