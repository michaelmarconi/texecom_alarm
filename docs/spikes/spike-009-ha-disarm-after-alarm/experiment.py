#!/usr/bin/env python3
"""
SPIKE-009 experiment: after a real alarm, does Disarm stop it?

Sends the same Disarm bytes Home Assistant uses (command 8, body 01).
Never sends Reset (command 9).

The add-on (and anything else using ComIP) must be stopped first — one
TCP login at a time.

This will sound the alarm. The person running it arms, then triggers a
zone. The script waits until the panel is in alarm (or drops the link),
reconnects, then Disarms. You then say whether the sirens actually stopped.

Usage:
    TEXECOM_HOST=192.0.2.10 TEXECOM_PORT=10001 TEXECOM_UDL_PASSWORD=1234 \
        python3 experiment.py
"""

from __future__ import annotations

import os
import socket
import sys
import time
import traceback

HOST = os.environ.get("TEXECOM_HOST", "192.0.2.10")
PORT = int(os.environ.get("TEXECOM_PORT", "10001"))
UDL_PASSWORD = os.environ.get("TEXECOM_UDL_PASSWORD", "1234")
AREA_NUMBER = int(os.environ.get("TEXECOM_AREA_NUMBER", "1"))
WAIT_FOR_ALARM_SECONDS = float(os.environ.get("TEXECOM_WAIT_FOR_ALARM_SECONDS", "180"))
AFTER_DISARM_LISTEN_SECONDS = float(
    os.environ.get("TEXECOM_AFTER_DISARM_LISTEN_SECONDS", "20")
)
IDLE_INTERVAL_SECONDS = float(os.environ.get("TEXECOM_IDLE_INTERVAL_SECONDS", "8"))
RECONNECT_ATTEMPTS = int(os.environ.get("TEXECOM_RECONNECT_ATTEMPTS", "18"))
RECONNECT_INTERVAL_SECONDS = float(
    os.environ.get("TEXECOM_RECONNECT_INTERVAL_SECONDS", "5")
)

HEADER_START = ord("t")
HEADER_TYPE_COMMAND = ord("C")
HEADER_TYPE_RESPONSE = ord("R")
HEADER_TYPE_MESSAGE = ord("M")
LENGTH_HEADER = 4

CMD_LOGIN = 1
CMD_SET_AREA_DISARM = 8
CMD_GET_AREA_FLAGS = 11
CMD_GETPANELIDENTIFICATION = 22
CMD_GETDATETIME = 23
CMD_SETEVENTMESSAGES = 37

RESP_ACK = 0x06
RESP_NAK = 0x15

MSG_ZONEEVENT = 1
MSG_AREAEVENT = 2
MSG_LOGEVENT = 5

AREA_STATES = ["disarmed", "in exit", "in entry", "armed", "part armed", "in alarm"]
AREA_MAP = {12: 2, 24: 2, 48: 4, 64: 4, 88: 8, 168: 16, 640: 64}
FLAG_ALARM = 0
FLAG_ARMED = 21
FLAG_FULL_ARMED = 22
FLAG_PART_ARMED = 23
FLAG_FORCE_ARMED = 26

CMD_TIMEOUT = 3.0
CMD_RETRIES = 3


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


class ForcedDisconnect(Exception):
    pass


class Stats:
    def __init__(self) -> None:
        self.saw_in_alarm = False
        self.forced_disconnects = 0
        self.reconnects_ok = 0
        self.disarm_result = "not sent"
        self.flags_before_disarm: dict | None = None
        self.flags_after_disarm: dict | None = None
        self.area_after_disarm: list[str] = []
        self.sirens_stopped: str = "not asked"
        self.exceptions: list[tuple[str, str]] = []


class Session:
    def __init__(self, stats: Stats) -> None:
        self.stats = stats
        self.sock: socket.socket | None = None
        self.seq = 0
        self._buf = bytearray()
        self.zone_count: int | None = None

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(CMD_TIMEOUT)
        self.sock.connect((HOST, PORT))
        time.sleep(0.5)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
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
                raise ForcedDisconnect("socket closed by peer")
            self._buf.extend(chunk)

    def _recv_frame(self) -> tuple[int, int, bytes]:
        skipped = bytearray()
        while True:
            self._fill(LENGTH_HEADER)
            if bytes(self._buf[:3]) == b"+++":
                del self._buf[:3]
                raise ForcedDisconnect("panel sent +++")
            if self._buf[0] != HEADER_START:
                skipped.append(self._buf.pop(0))
                continue
            length = self._buf[2]
            if not (LENGTH_HEADER + 1 <= length <= 255):
                skipped.append(self._buf.pop(0))
                continue
            self._fill(length)
            frame = bytes(self._buf[:length])
            if frame[-1] != crc8(frame[:-1]):
                skipped.append(self._buf.pop(0))
                continue
            del self._buf[:length]
            if skipped:
                log(f"  [resync] skipped {len(skipped)} byte(s): {bytes(skipped).hex()}")
            return frame[1], frame[3], frame[LENGTH_HEADER:-1]

    def send_command(self, cmd: int, body: bytes = b"") -> bytes:
        assert self.sock is not None
        seq = self._next_seq()
        payload = bytes([cmd]) + body
        header = bytes(
            [HEADER_START, HEADER_TYPE_COMMAND, len(payload) + LENGTH_HEADER + 1, seq]
        )
        frame = header + payload + bytes([crc8(header + payload)])
        attempt = 0
        while True:
            self.sock.sendall(frame)
            log(f"TX cmd={cmd} seq={seq} attempt={attempt} body={body.hex() or '(empty)'}")
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
                if msg_type == HEADER_TYPE_MESSAGE:
                    decoded = decode_message(msg_body, self.stats)
                    log(f"  [interleaved] {decoded}")
                    continue
                if msg_type != HEADER_TYPE_RESPONSE or msg_seq != seq:
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

    def wait_message(self, timeout: float) -> bytes:
        assert self.sock is not None
        self.sock.settimeout(timeout)
        msg_type, _seq, payload = self._recv_frame()
        if msg_type != HEADER_TYPE_MESSAGE:
            raise ProtocolError(f"unexpected frame type {msg_type} while listening")
        return payload

    def login_and_prepare(self) -> None:
        self.connect()
        login = self.send_command(CMD_LOGIN, UDL_PASSWORD.encode("ascii"))
        if login != bytes([RESP_ACK]):
            raise ProtocolError(f"LOGIN failed: {login.hex()}")
        log("LOGIN ACK")
        ident = self.send_command(CMD_GETPANELIDENTIFICATION)
        text = ident.decode("ascii", errors="replace")
        parts = text.split()
        self.zone_count = int(parts[1]) if len(parts) >= 2 else None
        log(f"GETPANELIDENTIFICATION: {text!r} zone_count={self.zone_count}")
        events = (1 << 1) | (1 << 2) | (1 << 5)  # zone + area + log
        body = bytes([events & 0xFF, (events >> 8) & 0xFF])
        sub = self.send_command(CMD_SETEVENTMESSAGES, body)
        if sub[:1] == bytes([RESP_NAK]):
            raise ProtocolError("SETEVENTMESSAGES NAK")
        log("SETEVENTMESSAGES ok (zone/area/log)")


def decode_message(payload: bytes, stats: Stats) -> str:
    if not payload:
        return "empty message"
    kind, body = payload[0], payload[1:]
    if kind == MSG_AREAEVENT and len(body) >= 2:
        state = body[1]
        label = AREA_STATES[state] if state < len(AREA_STATES) else f"unknown({state})"
        if label == "in alarm":
            stats.saw_in_alarm = True
        return f"AREA area={body[0]} state={label}"
    if kind == MSG_LOGEVENT and len(body) >= 1:
        return f"LOG type={body[0]}"
    if kind == MSG_ZONEEVENT and len(body) >= 2:
        return f"ZONE zone={body[0]} bitmap={body[1]:#04x}"
    return f"msg type={kind} hex={payload.hex()}"


def area_size_for_zones(zone_count: int) -> int:
    areas = AREA_MAP.get(zone_count)
    if areas is None:
        raise ProtocolError(f"no area map for zone_count={zone_count}")
    return (areas + 7) // 8


def flag_bit(flags: bytes, flag_index: int, area_size: int) -> bool:
    offset = flag_index * area_size
    chunk = flags[offset : offset + area_size]
    if len(chunk) < area_size:
        return False
    return bool(int.from_bytes(chunk, "little") & (1 << (AREA_NUMBER - 1)))


def poll_flags(session: Session, label: str) -> dict:
    if session.zone_count is None:
        raise ProtocolError("no zone count")
    area_size = area_size_for_zones(session.zone_count)
    count = 72 if area_size != 8 else 30
    flags = session.send_command(CMD_GET_AREA_FLAGS, bytes([0, count]))
    log(f"GetAreaFlags[{label}] len={len(flags)} hex={flags.hex()}")
    alarm = flag_bit(flags, FLAG_ALARM, area_size)
    armed = (
        flag_bit(flags, FLAG_ARMED, area_size)
        or flag_bit(flags, FLAG_FULL_ARMED, area_size)
        or flag_bit(flags, FLAG_PART_ARMED, area_size)
        or flag_bit(flags, FLAG_FORCE_ARMED, area_size)
    )
    if alarm:
        status = "InAlarm"
    elif armed:
        status = "Armed"
    else:
        status = "Disarmed"
    decoded = {"status": status, "alarm": alarm, "armed": armed}
    log(f"GetAreaFlags[{label}] {decoded}")
    return decoded


def connect_ready(stats: Stats) -> Session:
    session = Session(stats)
    session.login_and_prepare()
    return session


def reconnect(stats: Stats) -> Session | None:
    for attempt in range(1, RECONNECT_ATTEMPTS + 1):
        log(f"reconnect {attempt}/{RECONNECT_ATTEMPTS}...")
        try:
            session = connect_ready(stats)
            stats.reconnects_ok += 1
            log("reconnect ok")
            return session
        except Exception as exc:  # noqa: BLE001 — record every failed attempt
            log(f"reconnect failed: {exc}")
            if attempt < RECONNECT_ATTEMPTS:
                time.sleep(RECONNECT_INTERVAL_SECONDS)
    stats.exceptions.append(("reconnect", f"failed after {RECONNECT_ATTEMPTS} attempts"))
    return None


def _after_drop(stats: Stats) -> Session:
    nxt = reconnect(stats)
    if nxt is None:
        raise ProtocolError("could not reconnect after the panel dropped the link")
    flags = poll_flags(nxt, "after-drop")
    if flags["status"] == "Disarmed":
        raise ProtocolError(
            "reconnected but the panel is already disarmed — someone cleared "
            "it (keypad/app) before this script could Disarm"
        )
    if flags["alarm"]:
        stats.saw_in_alarm = True
    return nxt


def wait_until_alarm(session: Session, stats: Stats) -> Session:
    """Wait until the alarm is on, then return a live session.

    SPIKE-002: a real trigger often drops ComIP before we see much else.
    A drop during this wait, then flags still InAlarm, counts as the alarm.
    """
    log(
        f"Waiting up to {WAIT_FOR_ALARM_SECONDS:.0f}s for in-alarm "
        "(arm, then trigger a zone so sirens start)"
    )
    deadline = time.time() + WAIT_FOR_ALARM_SECONDS
    last_idle = 0.0
    current = session
    while time.time() < deadline:
        if stats.saw_in_alarm:
            return current
        now = time.time()
        if now - last_idle >= IDLE_INTERVAL_SECONDS:
            last_idle = now
            try:
                current.send_command(CMD_GETDATETIME)
            except (ForcedDisconnect, ProtocolError, OSError, TimeoutError) as exc:
                stats.forced_disconnects += 1
                log(f"link dropped while waiting: {exc}")
                return _after_drop(stats)
        try:
            payload = current.wait_message(timeout=0.5)
            decoded = decode_message(payload, stats)
            log(f"UNSOLICITED {decoded}")
        except socket.timeout:
            continue
        except (ForcedDisconnect, ProtocolError, OSError) as exc:
            stats.forced_disconnects += 1
            log(f"link dropped while listening: {exc}")
            return _after_drop(stats)
    raise ProtocolError(
        "timed out waiting for in-alarm — trigger did not happen, or the "
        "link never dropped and no AREA in-alarm message arrived"
    )


def ask_sirens_stopped() -> str:
    print()
    print(">>> Did the sirens stop after Disarm?")
    print("    Type yes or no, then Enter.")
    try:
        answer = input().strip().lower()
    except EOFError:
        return "unanswered (no tty)"
    if answer in {"y", "yes"}:
        return "yes"
    if answer in {"n", "no"}:
        return "no"
    return f"unrecognised ({answer!r})"


def run() -> int:
    stats = Stats()
    print("=== SPIKE-009: does Disarm stop an alarm that is already going off? ===")
    print(f"Target: {HOST}:{PORT}")
    print()
    print("This will sound the alarm. Stop the Texecom Alarm add-on first")
    print("(and anything else logged into the panel).")
    print()
    print("When listening starts:")
    print("  1. Arm the panel (keypad or Texecom app).")
    print("  2. Open a zone so the alarm actually goes off.")
    print("  3. Leave the sirens running — do not enter your code yet.")
    print("The script then sends the same Disarm Home Assistant would send.")
    print("It never sends Reset.")
    print()

    session = connect_ready(stats)
    try:
        session = wait_until_alarm(session, stats)
        try:
            stats.flags_before_disarm = poll_flags(session, "before-disarm")
        except (ForcedDisconnect, ProtocolError, OSError, TimeoutError) as exc:
            stats.forced_disconnects += 1
            log(f"link dropped before Disarm: {exc}")
            session = _after_drop(stats)
            stats.flags_before_disarm = poll_flags(session, "before-disarm")
        try:
            payload = session.send_command(CMD_SET_AREA_DISARM, b"\x01")
        except TimeoutError as exc:
            stats.disarm_result = f"timeout: {exc}"
            log(stats.disarm_result)
        else:
            if payload[:1] == bytes([RESP_NAK]) or payload == bytes([RESP_NAK]):
                stats.disarm_result = "NAK"
            else:
                stats.disarm_result = f"ACK payload={payload.hex() or '(empty)'}"
            log(f"Disarm result: {stats.disarm_result}")

        listen_until = time.time() + AFTER_DISARM_LISTEN_SECONDS
        while time.time() < listen_until:
            try:
                payload = session.wait_message(timeout=0.5)
                decoded = decode_message(payload, stats)
                log(f"AFTER DISARM {decoded}")
                if decoded.startswith("AREA "):
                    stats.area_after_disarm.append(decoded)
            except socket.timeout:
                continue
            except (ForcedDisconnect, ProtocolError, OSError) as exc:
                log(f"link dropped after Disarm: {exc}")
                break

        try:
            stats.flags_after_disarm = poll_flags(session, "after-disarm")
        except (ForcedDisconnect, ProtocolError, OSError, TimeoutError) as exc:
            log(f"could not poll flags after Disarm: {exc}")

        stats.sirens_stopped = ask_sirens_stopped()
    finally:
        session.close()

    print()
    print("=== Summary (fill Actuals from these lines) ===")
    print(f"Saw AREA in alarm: {stats.saw_in_alarm}")
    print(f"Forced disconnects: {stats.forced_disconnects}")
    print(f"Reconnects ok: {stats.reconnects_ok}")
    print(f"Flags before Disarm: {stats.flags_before_disarm}")
    print(f"Disarm result: {stats.disarm_result}")
    print(f"AREA after Disarm: {stats.area_after_disarm}")
    print(f"Flags after Disarm: {stats.flags_after_disarm}")
    print(f"Sirens stopped (you): {stats.sirens_stopped}")
    if stats.exceptions:
        print("Exceptions:")
        for where, msg in stats.exceptions:
            print(f"  [{where}] {msg}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as exc:  # noqa: BLE001 — top-level: report, don't hide
        print(f"FATAL: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
