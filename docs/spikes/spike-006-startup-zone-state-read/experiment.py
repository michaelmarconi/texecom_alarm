#!/usr/bin/env python3
"""
Spike experiment: SPIKE-006 startup zone-state read feasibility.

Read-only probe against a live Texecom Premier Elite panel (Connect protocol,
ComIP transport) to test whether current per-zone open/closed state can be
retrieved after LOGIN via GetZoneState (cmd=2).

Candidate framing came from research (published MQTT-bridge image strings /
embedded JS naming GetZoneState=2). This script is the experiment — Actuals
come only from live panel output.

Sends only LOGIN, GETPANELIDENTIFICATION, and GetZoneState (cmd 2). Never sends
arm/disarm/omit/reset (cmds 4/5/6/8/9).

Env:
  TEXECOM_HOST            default 192.168.1.183
  TEXECOM_PORT            default 10001
  TEXECOM_UDL_PASSWORD    default 1234
  TEXECOM_FLIP_ZONE       optional zone number; if set, pause for open then
                          close and re-query that zone for Active/Secure flip
"""

from __future__ import annotations

import os
import socket
import sys
import time

HOST = os.environ.get("TEXECOM_HOST", "192.168.1.183")
PORT = int(os.environ.get("TEXECOM_PORT", "10001"))
UDL_PASSWORD = os.environ.get("TEXECOM_UDL_PASSWORD", "1234")
FLIP_ZONE = os.environ.get("TEXECOM_FLIP_ZONE")

HEADER_START = ord("t")
TYPE_COMMAND = ord("C")
TYPE_RESPONSE = ord("R")
TYPE_MESSAGE = ord("M")

CMD_LOGIN = 1
CMD_GET_ZONE_STATE = 2
CMD_GETPANELIDENTIFICATION = 22

ACK = 0x06
NAK = 0x15

CMD_TIMEOUT = 3.0
CMD_RETRIES = 3
MAX_ZONES_PER_REQUEST = 168

ZONE_STATE_LABELS = {0: "secure", 1: "active", 2: "tamper", 3: "short"}


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


def decode_bitmap(b: int) -> dict:
    return {
        "state": ZONE_STATE_LABELS.get(b & 0x3, f"unknown({b & 0x3})"),
        "state_bits": b & 0x3,
        "fault": bool(b & (1 << 2)),
        "failed_test": bool(b & (1 << 3)),
        "alarmed": bool(b & (1 << 4)),
        "manual_bypass": bool(b & (1 << 5)),
        "auto_bypass": bool(b & (1 << 6)),
        "masked": bool(b & (1 << 7)),
        "raw": b,
    }


def get_zone_state(probe: TexecomProbe, zone_count: int, start: int, count: int) -> bytes:
    # Elite 88 → zone numbers fit in 1 byte (zone_count <= 256).
    if zone_count > 256:
        body = start.to_bytes(2, "little") + bytes([count])
    else:
        body = bytes([start, count])
    return probe.send_command(CMD_GET_ZONE_STATE, body)


def summarise(payload: bytes, start: int) -> None:
    labels = [decode_bitmap(b)["state"] for b in payload]
    from collections import Counter

    counts = Counter(labels)
    log(f"GetZoneState summary start={start} len={len(payload)} counts={dict(counts)}")
    for i, b in enumerate(payload):
        info = decode_bitmap(b)
        extras = [
            k
            for k in ("fault", "failed_test", "alarmed", "manual_bypass", "auto_bypass", "masked")
            if info[k]
        ]
        extra = f" [{','.join(extras)}]" if extras else ""
        if info["state"] != "secure" or extras:
            log(f"  zone {start + i}: {info['state']} raw=0x{b:02x}{extra}")


def main() -> int:
    log(f"SPIKE-006 GetZoneState probe")
    log(f"Target: {HOST}:{PORT}")
    flip = int(FLIP_ZONE) if FLIP_ZONE else None
    if flip is not None:
        log(f"Physical flip corroboration enabled for zone {flip}")

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
        log(f"GETPANELIDENTIFICATION: {ident!r} → zone_count={zone_count}")

        # Full panel poll in batches of MAX_ZONES_PER_REQUEST (published MQTT-bridge pattern).
        all_bytes = bytearray()
        remaining = zone_count
        start = 1
        while remaining > 0:
            batch = min(remaining, MAX_ZONES_PER_REQUEST)
            payload = get_zone_state(probe, zone_count, start, batch)
            log(
                f"GetZoneState start={start} count={batch} "
                f"payload_len={len(payload)} hex={payload.hex()}"
            )
            if len(payload) != batch:
                log(
                    f"LENGTH MISMATCH: expected {batch} status bytes, got {len(payload)}"
                )
            summarise(payload, start)
            all_bytes.extend(payload)
            start += batch
            remaining -= batch

        log(f"TOTAL status bytes received: {len(all_bytes)} (expected {zone_count})")

        if flip is not None:
            input(
                f"\n>>> Open zone {flip} now, then press Enter to re-query...\n"
            )
            open_payload = get_zone_state(probe, zone_count, flip, 1)
            log(f"flip-open zone {flip}: {open_payload.hex()} → {decode_bitmap(open_payload[0])}")
            input(
                f"\n>>> Close zone {flip} now, then press Enter to re-query...\n"
            )
            close_payload = get_zone_state(probe, zone_count, flip, 1)
            log(
                f"flip-close zone {flip}: {close_payload.hex()} → {decode_bitmap(close_payload[0])}"
            )
            open_state = decode_bitmap(open_payload[0])["state"]
            close_state = decode_bitmap(close_payload[0])["state"]
            if open_state == "active" and close_state == "secure":
                log("FLIP CORROBORATION: PASS (active then secure)")
            else:
                log(
                    f"FLIP CORROBORATION: unexpected open={open_state} close={close_state}"
                )
        else:
            log("FLIP CORROBORATION: skipped (TEXECOM_FLIP_ZONE unset)")

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
