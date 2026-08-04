#!/usr/bin/env python3
"""
Spike experiment: SPIKE-007 area/arm-state startup read feasibility.

Read-only probe (by default) against a live Texecom Premier Elite panel
(Connect protocol, ComIP transport) to test whether current area arm state
can be retrieved after LOGIN via GetAreaFlags (cmd=11).

Candidate framing came from research (published the prior MQTT bridge image strings /
embedded JS naming GetAreaFlags=11). This script is the experiment — Actuals
come only from live panel output.

Default path sends only LOGIN, GETPANELIDENTIFICATION, and GetAreaFlags
(cmd 11). Never sends omit/reset (cmds 4/5/9). Arm/disarm only if
TEXECOM_ARM_MODE is set (optional corroboration).

Env:
  TEXECOM_HOST            default 192.168.1.183
  TEXECOM_PORT            default 10001
  TEXECOM_UDL_PASSWORD    default 1234
  TEXECOM_ARM_MODE        optional 0/1/2 (Away/Night/Home); if set, arm,
                          re-poll, then disarm for before/after corroboration
  TEXECOM_AREA_NUMBER     default 1 (HOUSE on this panel)
  TEXECOM_SETTLE_SECONDS  default 35 (exit timer + margin when arming)
"""

from __future__ import annotations

import os
import socket
import sys
import time

HOST = os.environ.get("TEXECOM_HOST", "192.168.1.183")
PORT = int(os.environ.get("TEXECOM_PORT", "10001"))
UDL_PASSWORD = os.environ.get("TEXECOM_UDL_PASSWORD", "1234")
ARM_MODE = os.environ.get("TEXECOM_ARM_MODE")
AREA_NUMBER = int(os.environ.get("TEXECOM_AREA_NUMBER", "1"))
SETTLE_SECONDS = float(os.environ.get("TEXECOM_SETTLE_SECONDS", "35"))

HEADER_START = ord("t")
TYPE_COMMAND = ord("C")
TYPE_RESPONSE = ord("R")
TYPE_MESSAGE = ord("M")

CMD_LOGIN = 1
CMD_GET_AREA_FLAGS = 11
CMD_SET_AREA_ARM = 6
CMD_SET_AREA_DISARM = 8
CMD_GETPANELIDENTIFICATION = 22

ACK = 0x06
NAK = 0x15

CMD_TIMEOUT = 3.0
CMD_RETRIES = 3

# areaMap from the prior MQTT bridge image: zones → number of areas (bits in area bitmap)
AREA_MAP = {12: 2, 24: 2, 48: 4, 64: 4, 88: 8, 168: 16, 640: 64}

# Flag indices used by the prior MQTT bridge updateAreaStates decode
FLAG_ALARM = 0
FLAG_ARMED = 21
FLAG_FULL_ARMED = 22
FLAG_PART_ARMED = 23
FLAG_FORCE_ARMED = 26
FLAG_PART_ARM_1 = 50
FLAG_PART_ARM_2 = 51
FLAG_PART_ARM_3 = 52


def crc8(data: bytes) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x85) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


class ProtocolError(Exception):
    pass


class TexecomProbe:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.seq = 0
        self._buf = bytearray()

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(CMD_TIMEOUT)
        self.sock.connect((self.host, self.port))
        time.sleep(0.5)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.sock.close()
            self.sock = None

    def _next_seq(self) -> int:
        seq = self.seq
        self.seq = (self.seq + 1) % 256
        return seq

    def _fill(self, n: int) -> None:
        assert self.sock is not None
        while len(self._buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ProtocolError("connection closed by panel")
            self._buf.extend(chunk)

    def _recv_frame(self) -> tuple[int, int, bytes]:
        """Return (msg_type, sequence, body); resync past non-frame bytes."""
        skipped = 0
        while True:
            self._fill(4)
            if bytes(self._buf[:3]) == b"+++":
                del self._buf[:3]
                raise ProtocolError("panel sent +++")
            if self._buf[0] != HEADER_START:
                del self._buf[0]
                skipped += 1
                continue
            msg_type = self._buf[1]
            length = self._buf[2]
            seq = self._buf[3]
            if not (5 <= length <= 255):
                del self._buf[0]
                skipped += 1
                continue
            self._fill(length)
            frame = bytes(self._buf[:length])
            if frame[-1] != crc8(frame[:-1]):
                del self._buf[0]
                skipped += 1
                continue
            del self._buf[:length]
            if skipped:
                log(f"  [resync] skipped {skipped} non-frame byte(s)")
            return msg_type, seq, frame[4:-1]

    def send_command(self, cmd: int, body: bytes = b"") -> bytes:
        assert self.sock is not None
        seq = self._next_seq()
        payload = bytes([cmd]) + body
        header = bytes([HEADER_START, TYPE_COMMAND, len(payload) + 5, seq])
        frame = header + payload
        frame += bytes([crc8(frame)])
        attempt = 0
        while True:
            self.sock.sendall(frame)
            log(
                f"TX cmd={cmd} seq={seq} attempt={attempt} body={body.hex() or '(empty)'}"
            )
            deadline = time.time() + CMD_TIMEOUT
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self.sock.settimeout(max(remaining, 0.05))
                try:
                    msg_type, msg_seq, msg_body = self._recv_frame()
                except socket.timeout:
                    continue
                if msg_type == TYPE_MESSAGE:
                    log(f"  [interleaved M] body={msg_body.hex()}")
                    continue
                if msg_type != TYPE_RESPONSE:
                    log(f"  [unexpected type {msg_type}] body={msg_body.hex()}")
                    continue
                if msg_seq != seq:
                    log(f"  [stale seq {msg_seq} != {seq}] body={msg_body.hex()}")
                    continue
                if not msg_body or msg_body[0] != cmd:
                    raise ProtocolError(
                        f"response cmd mismatch: got {msg_body[:1]!r}, expected {cmd}"
                    )
                return msg_body[1:]
            attempt += 1
            if attempt > CMD_RETRIES:
                raise TimeoutError(f"no response to cmd {cmd} after {CMD_RETRIES} retries")
            log(f"  timeout — retrying same sequence {seq}")


def parse_zone_count(ident: bytes) -> int:
    text = ident.decode("ascii", errors="replace")
    parts = text.split()
    if len(parts) < 2:
        raise ProtocolError(f"cannot parse zone count from {text!r}")
    return int(parts[1])


def area_size_for_zones(zone_count: int) -> int:
    areas = AREA_MAP.get(zone_count)
    if areas is None:
        raise ProtocolError(f"no areaMap entry for zone_count={zone_count}")
    return (areas + 7) // 8  # ceil(areas / 8)


def get_area_flags(probe: TexecomProbe, start: int, count: int) -> bytes:
    return probe.send_command(CMD_GET_AREA_FLAGS, bytes([start, count]))


def flag_bit(flags: bytes, flag_index: int, area_size: int, area_number: int) -> bool:
    offset = flag_index * area_size
    chunk = flags[offset : offset + area_size]
    if len(chunk) < area_size:
        return False
    value = int.from_bytes(chunk, "little")
    return bool(value & (1 << (area_number - 1)))


def decode_area_status(
    flags: bytes,
    *,
    area_size: int,
    area_number: int,
    part_arm_flags: bytes | None = None,
) -> dict:
    alarm = flag_bit(flags, FLAG_ALARM, area_size, area_number)
    armed = flag_bit(flags, FLAG_ARMED, area_size, area_number)
    full_armed = flag_bit(flags, FLAG_FULL_ARMED, area_size, area_number)
    part_armed = flag_bit(flags, FLAG_PART_ARMED, area_size, area_number)
    force_armed = flag_bit(flags, FLAG_FORCE_ARMED, area_size, area_number)

    if part_arm_flags is not None:
        part1 = flag_bit(part_arm_flags, 0, area_size, area_number)
        part2 = flag_bit(part_arm_flags, 1, area_size, area_number)
        part3 = flag_bit(part_arm_flags, 2, area_size, area_number)
    else:
        part1 = flag_bit(flags, FLAG_PART_ARM_1, area_size, area_number)
        part2 = flag_bit(flags, FLAG_PART_ARM_2, area_size, area_number)
        part3 = flag_bit(flags, FLAG_PART_ARM_3, area_size, area_number)

    part_arm = 1 if part1 else 2 if part2 else 3 if part3 else None

    if alarm:
        status = "InAlarm"
    elif armed or full_armed or part_armed or force_armed:
        status = "PartArmed" if part_arm else "Armed"
    else:
        status = "Disarmed"

    return {
        "status": status,
        "alarm": alarm,
        "armed": armed,
        "full_armed": full_armed,
        "part_armed": part_armed,
        "force_armed": force_armed,
        "part_arm": part_arm,
        "part_arm_1": part1,
        "part_arm_2": part2,
        "part_arm_3": part3,
    }


def poll_and_decode(probe: TexecomProbe, area_size: int, area_number: int, label: str) -> dict:
    if area_size == 8:
        max_flag = 30
        flags = get_area_flags(probe, 0, max_flag)
        expected = max_flag * area_size
        log(
            f"GetAreaFlags[{label}] start=0 count={max_flag} "
            f"payload_len={len(flags)} (expected {expected}) hex={flags.hex()}"
        )
        if len(flags) != expected:
            log(f"LENGTH MISMATCH: expected {expected}, got {len(flags)}")
        part_arm_flags = get_area_flags(probe, 50, 3)
        expected_pa = 3 * area_size
        log(
            f"GetAreaFlags[{label}] part-arm start=50 count=3 "
            f"payload_len={len(part_arm_flags)} (expected {expected_pa}) "
            f"hex={part_arm_flags.hex()}"
        )
        decoded = decode_area_status(
            flags,
            area_size=area_size,
            area_number=area_number,
            part_arm_flags=part_arm_flags,
        )
    else:
        max_flag = 72
        flags = get_area_flags(probe, 0, max_flag)
        expected = max_flag * area_size
        log(
            f"GetAreaFlags[{label}] start=0 count={max_flag} "
            f"payload_len={len(flags)} (expected {expected}) hex={flags.hex()}"
        )
        if len(flags) != expected:
            log(f"LENGTH MISMATCH: expected {expected}, got {len(flags)}")
        decoded = decode_area_status(
            flags, area_size=area_size, area_number=area_number, part_arm_flags=None
        )

    log(f"GetAreaFlags[{label}] area={area_number} decode={decoded}")
    return decoded


def arm_body(mode: int, area_number: int, area_size: int) -> bytes:
    """Confirmed SPIKE-005 arm body: [mode] + area bitmap (area bit set)."""
    bitmap = (1 << (area_number - 1)).to_bytes(area_size, "little")
    return bytes([mode]) + bitmap


def disarm_body(area_number: int, area_size: int) -> bytes:
    return (1 << (area_number - 1)).to_bytes(area_size, "little")


def main() -> int:
    log("SPIKE-007 GetAreaFlags probe")
    log(f"Target: {HOST}:{PORT}")
    log(f"Area number under test: {AREA_NUMBER}")
    if ARM_MODE is not None:
        log(f"Arm corroboration enabled: mode_byte={ARM_MODE}")
    else:
        log("Arm corroboration: skipped unless TEXECOM_ARM_MODE is set")

    probe = TexecomProbe(HOST, PORT)
    try:
        probe.connect()
        log("TCP connected; waiting done; sending LOGIN")
        login = probe.send_command(CMD_LOGIN, UDL_PASSWORD.encode("ascii"))
        if login != bytes([ACK]):
            log(f"LOGIN failed: {login.hex()}")
            return 1
        log("LOGIN ACK")

        ident = probe.send_command(CMD_GETPANELIDENTIFICATION)
        zone_count = parse_zone_count(ident)
        area_size = area_size_for_zones(zone_count)
        log(
            f"GETPANELIDENTIFICATION: {ident!r} → zone_count={zone_count} "
            f"area_size={area_size}"
        )

        before = poll_and_decode(probe, area_size, AREA_NUMBER, "initial")

        if ARM_MODE is not None:
            mode = int(ARM_MODE)
            if mode not in (0, 1, 2):
                log(f"TEXECOM_ARM_MODE must be 0/1/2, got {ARM_MODE!r}")
                return 1
            arm_payload = probe.send_command(
                CMD_SET_AREA_ARM, arm_body(mode, AREA_NUMBER, area_size)
            )
            log(f"ARM response: {arm_payload.hex()}")
            log(f"Waiting {SETTLE_SECONDS}s for exit settle...")
            time.sleep(SETTLE_SECONDS)
            after = poll_and_decode(probe, area_size, AREA_NUMBER, "after-arm")
            disarm_payload = probe.send_command(
                CMD_SET_AREA_DISARM, disarm_body(AREA_NUMBER, area_size)
            )
            log(f"DISARM response: {disarm_payload.hex()}")
            time.sleep(2.0)
            final = poll_and_decode(probe, area_size, AREA_NUMBER, "after-disarm")
            log(
                f"ARM CORROBORATION: before={before['status']} "
                f"after_arm={after['status']} part_arm={after['part_arm']} "
                f"after_disarm={final['status']}"
            )
        else:
            log("ARM CORROBORATION: skipped (TEXECOM_ARM_MODE unset)")

        log("DONE")
        return 0
    except Exception as exc:
        log(f"EXPERIMENT FAILED: {type(exc).__name__}: {exc}")
        return 1
    finally:
        probe.close()
        log("socket closed")


if __name__ == "__main__":
    sys.exit(main())
