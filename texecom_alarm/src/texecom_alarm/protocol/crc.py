"""CRC-8 for Texecom Connect framing (poly=0x185, init=0xff, non-reflected)."""

from __future__ import annotations


def crc8(data: bytes) -> int:
    """Non-reflected CRC-8; working polynomial 0x85 (crcmod poly=0x185)."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x85) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc
