#!/usr/bin/env python3
"""
SPIKE-002 experiment: observe arm_home (part_arm_2) and a full triggered-alarm
event over the Texecom Connect protocol, and stress-test TX/RX collision
safety, WITHOUT ever sending a guessed/experimental command to the panel.

This reimplements only the framing already independently confirmed safe by
SPIKE-001 (LOGIN, GETPANELIDENTIFICATION) plus two more commands documented in
publicly inspected prior art (SETEVENTMESSAGES, GETDATETIME) - it is written
from first principles against those documented byte values, not copied from
any GPL/Apache-licensed source, per RISK-008.

It never sends an arm/disarm command itself. The household member is expected
to physically arm/disarm and trigger the alarm via the wall keypad while this
script listens.

Collision handling follows the pattern documented in publicly inspected prior
art (see SPIKE.md ## Research): an unsolicited message ('M'-type frame) can
legitimately arrive while we are waiting for a command's response. That is
not an error - it must be decoded and the wait for the actual response must
continue (bounded by the same CMD_TIMEOUT/retry budget). Only a genuine
timeout, a forced +++ disconnect, or a socket close counts as a collision
failure worth recording.

Iteration 2 (post first live run): the first full run showed the panel
injecting non-Connect-protocol bytes onto this same TCP session around an
arm-adjacent event (see SPIKE.md ## Results), which a "first unexpected byte
= fatal" parser cannot survive. The frame reader below is now resync-capable:
on an unexpected start byte, an implausible length, or a CRC mismatch, it
discards exactly one byte and keeps scanning the stream for the next valid
Connect-protocol frame, instead of raising and tearing down the connection.
This is deliberately conservative (one byte at a time) so it can never skip
past the start of a genuinely valid frame.

Usage:
    TEXECOM_HOST=192.168.1.183 TEXECOM_PORT=10001 TEXECOM_UDL_PASSWORD=1234 \
        TEXECOM_OBSERVE_SECONDS=600 TEXECOM_IDLE_INTERVAL_SECONDS=3 \
        python3 experiment.py
"""

import os
import socket
import sys
import time
import traceback

HOST = os.environ.get("TEXECOM_HOST", "192.168.1.183")
PORT = int(os.environ.get("TEXECOM_PORT", "10001"))
UDL_PASSWORD = os.environ.get("TEXECOM_UDL_PASSWORD", "1234")
OBSERVE_SECONDS = float(os.environ.get("TEXECOM_OBSERVE_SECONDS", "600"))
IDLE_INTERVAL_SECONDS = float(os.environ.get("TEXECOM_IDLE_INTERVAL_SECONDS", "3"))
CMD_TIMEOUT = 2.0
CMD_RETRIES = 3

HEADER_START = ord("t")
HEADER_TYPE_COMMAND = ord("C")
HEADER_TYPE_RESPONSE = ord("R")
HEADER_TYPE_MESSAGE = ord("M")
LENGTH_HEADER = 4

CMD_LOGIN = 1
CMD_GETDATETIME = 23
CMD_GETPANELIDENTIFICATION = 22
CMD_SETEVENTMESSAGES = 37

RESP_ACK = 0x06
RESP_NAK = 0x15

MSG_DEBUG = 0
MSG_ZONEEVENT = 1
MSG_AREAEVENT = 2
MSG_OUTPUTEVENT = 3
MSG_USEREVENT = 4
MSG_LOGEVENT = 5

AREA_STATES = ["disarmed", "in exit", "in entry", "armed", "part armed", "in alarm"]

# Reproduced from Texecom Connect protocol documentation cross-referenced
# publicly (see SPIKE.md ## Research) - independently retyped, not copied
# from any single source file.
LOG_EVENT_TYPES = {
    27: "Alarm Active",
    28: "Bell Active",
    29: "Re-arm",
    32: "Exit Started",
    33: "Exit Error (Arming Failed)",
    34: "Entry Started",
    35: "Part Arm Suite",
    37: "Open/Close (Away Armed)",
    38: "Part Armed",
    43: "Quick Arm",
    45: "Reset After Alarm",
    53: "Download Start",
    54: "Download End",
    78: "Part Arm 1",
    79: "Part Arm 2",
    80: "Part Arm 3",
    81: "Auto Arming Started",
    82: "Confirmed Alarm",
    85: "Arm Failed",
    100: "Site Data Changed",
    113: "Remote Command",
}


def crc8(data: bytes) -> int:
    """CRC-8, poly=0x185 (crcmod convention: leading bit implicit, so the
    working 8-bit polynomial is 0x85), non-reflected, init=0xFF - as
    documented for the Connect protocol and confirmed working in SPIKE-001."""
    poly = 0x85
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


class ProtocolError(Exception):
    pass


class ForcedDisconnect(Exception):
    pass


class Stats:
    def __init__(self):
        self.idle_sent = 0
        self.idle_acked_first_try = 0
        self.idle_recovered_via_interleaved_message = 0
        self.idle_timed_out_then_retried_ok = 0
        self.idle_failed = 0
        self.messages_seen = 0
        self.area_events = []
        self.log_events = []
        self.forced_disconnects = 0
        self.reconnects_ok = 0
        self.exceptions = []
        self.resync_events = 0
        self.resync_bytes_skipped = 0


def decode_message(payload: bytes, stats: Stats) -> str:
    if not payload:
        return "empty message payload"
    msg_type, body = payload[0], payload[1:]
    stats.messages_seen += 1

    if msg_type == MSG_AREAEVENT and len(body) >= 2:
        area_number, area_state = body[0], body[1]
        state_str = AREA_STATES[area_state] if area_state < len(AREA_STATES) else f"unknown({area_state})"
        stats.area_events.append((time.time(), area_number, state_str))
        return f"AREA event: area={area_number} state={state_str}"

    if msg_type == MSG_LOGEVENT and len(body) >= 4:
        event_type, group_type_msg = body[0], body[1]
        group_type = group_type_msg & 0b00111111
        event_str = LOG_EVENT_TYPES.get(event_type, f"unknown log event type {event_type}")
        stats.log_events.append((time.time(), event_type, event_str, group_type))
        return f"LOG event: type={event_type} ({event_str}) group={group_type}"

    if msg_type == MSG_ZONEEVENT and len(body) >= 2:
        zone_number, zone_bitmap = body[0], body[1]
        zone_str = ["secure", "active", "tamper", "short"][zone_bitmap & 0x3]
        return f"ZONE event: zone={zone_number} state={zone_str} bitmap={zone_bitmap:#04x}"

    if msg_type == MSG_OUTPUTEVENT:
        return f"OUTPUT event: raw={body.hex()}"
    if msg_type == MSG_USEREVENT:
        return f"USER event: raw={body.hex()}"
    if msg_type == MSG_DEBUG:
        return f"DEBUG message: raw={body.hex()}"
    return f"unknown message type {msg_type}: raw={body.hex()}"


class TexecomSession:
    """Connect-protocol session. Mirrors the collision-handling shape already
    proven safe by publicly inspected prior art: while waiting for a specific
    command's response, any unsolicited message frame that arrives first is
    decoded and the wait continues, rather than being treated as an error."""

    def __init__(self, host, port, password, stats: Stats):
        self.host = host
        self.port = port
        self.password = password
        self.stats = stats
        self.sock = None
        self.seq = 0
        self._buf = bytearray()

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(CMD_TIMEOUT)
        self.sock.connect((self.host, self.port))
        time.sleep(0.5)

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _next_seq(self):
        s = self.seq
        self.seq = (self.seq + 1) % 256
        return s

    def _fill_buffer(self, min_bytes):
        while len(self._buf) < min_bytes:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ForcedDisconnect("socket closed by peer")
            self._buf += chunk

    def _recv_frame(self):
        """Read the next valid Connect-protocol frame, resyncing past any
        non-conforming bytes instead of treating them as fatal (see the
        Iteration 2 module docstring). Discards exactly one byte at a time
        so a genuine frame boundary is never skipped over."""
        skipped = bytearray()
        while True:
            self._fill_buffer(LENGTH_HEADER)
            if bytes(self._buf[:3]) == b"+++":
                del self._buf[:3]
                raise ForcedDisconnect("panel sent +++ (forced disconnect)")

            if self._buf[0] != HEADER_START:
                skipped.append(self._buf.pop(0))
                continue

            header = bytes(self._buf[:LENGTH_HEADER])
            msg_type, msg_length, msg_seq = header[1], header[2], header[3]
            if not (LENGTH_HEADER + 1 <= msg_length <= 255):
                skipped.append(self._buf.pop(0))
                continue

            self._fill_buffer(msg_length)
            frame = bytes(self._buf[:msg_length])
            payload, msg_crc = frame[LENGTH_HEADER:-1], frame[-1]
            expected_crc = crc8(frame[:-1])
            if msg_crc != expected_crc:
                skipped.append(self._buf.pop(0))
                continue

            del self._buf[:msg_length]
            if skipped:
                self.stats.resync_events += 1
                self.stats.resync_bytes_skipped += len(skipped)
                log(f"  [resync] skipped {len(skipped)} non-frame byte(s) before next valid frame: {bytes(skipped).hex()}")
            return msg_type, msg_seq, payload

    def _send_command(self, cmd_byte, body=b""):
        seq = self._next_seq()
        cmd_payload = bytes([cmd_byte]) + body
        header = bytes([HEADER_START, HEADER_TYPE_COMMAND, len(cmd_payload) + LENGTH_HEADER + 1, seq])
        frame = header + cmd_payload
        frame += bytes([crc8(frame)])
        self.sock.send(frame)
        return seq, frame

    def send_command(self, cmd_byte, body=b""):
        """Send a command and wait for its response, decoding (and recording)
        any unsolicited messages that interleave while we wait. Retries up
        to CMD_RETRIES times on timeout, reusing the same sequence number,
        matching the pattern documented in inspected prior art."""
        seq, frame = self._send_command(cmd_byte, body)
        deadline = time.time() + CMD_TIMEOUT
        interleaved = 0
        attempt = 0

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                attempt += 1
                if attempt > CMD_RETRIES:
                    self.stats.idle_failed += 1
                    raise TimeoutError(f"no response to cmd {cmd_byte} after {CMD_RETRIES} retries")
                self.stats.idle_timed_out_then_retried_ok += 1
                log(f"  timeout waiting for response to cmd {cmd_byte}, resending (attempt {attempt}/{CMD_RETRIES})")
                self.sock.send(frame)
                deadline = time.time() + CMD_TIMEOUT
                continue

            self.sock.settimeout(remaining)
            try:
                msg_type, msg_seq, payload = self._recv_frame()
            except socket.timeout:
                continue

            if msg_type == HEADER_TYPE_MESSAGE:
                interleaved += 1
                decoded = decode_message(payload, self.stats)
                log(f"  [interleaved while awaiting cmd {cmd_byte} response] {decoded} (raw={payload.hex()})")
                continue

            if msg_type != HEADER_TYPE_RESPONSE:
                raise ProtocolError(f"unexpected frame type {msg_type:#x} while awaiting response")
            if msg_seq != seq:
                # stale/duplicate response for an earlier retry - keep waiting
                continue

            if interleaved:
                self.stats.idle_recovered_via_interleaved_message += 1
            else:
                self.stats.idle_acked_first_try += 1
            resp_cmd, resp_payload = payload[0], payload[1:]
            if resp_cmd != cmd_byte:
                raise ProtocolError(f"response cmd id {resp_cmd} != expected {cmd_byte}")
            return resp_payload

    def wait_for_message(self, timeout):
        """Block up to `timeout` seconds for a single unsolicited message
        frame (used in the main listen loop, outside of any command)."""
        self.sock.settimeout(timeout)
        msg_type, _msg_seq, payload = self._recv_frame()
        return msg_type, payload

    def login(self):
        payload = self.send_command(CMD_LOGIN, self.password.encode("ascii"))
        if len(payload) == 1 and payload[0] == RESP_NAK:
            raise ProtocolError("panel NAK'd login")
        if len(payload) != 1 or payload[0] != RESP_ACK:
            raise ProtocolError(f"unexpected LOGIN response: {payload!r}")

    def get_panel_identification(self):
        payload = self.send_command(CMD_GETPANELIDENTIFICATION)
        return payload.decode("ascii", errors="replace")

    def set_event_messages(self):
        debug_flag = 1
        zone_flag = 1 << 1
        area_flag = 1 << 2
        output_flag = 1 << 3
        user_flag = 1 << 4
        log_flag = 1 << 5
        events = debug_flag | zone_flag | area_flag | output_flag | user_flag | log_flag
        body = bytes([events & 0xFF, (events >> 8) & 0xFF])
        payload = self.send_command(CMD_SETEVENTMESSAGES, body)
        if len(payload) >= 1 and payload[0] == RESP_NAK:
            raise ProtocolError("panel NAK'd SETEVENTMESSAGES")

    def get_date_time(self):
        return self.send_command(CMD_GETDATETIME)


def connect_and_prepare(stats: Stats) -> TexecomSession:
    session = TexecomSession(HOST, PORT, UDL_PASSWORD, stats)
    session.connect()
    log("TCP connected")
    session.login()
    log(f"LOGIN ok (password={'*' * len(UDL_PASSWORD)})")
    panel_id = session.get_panel_identification()
    log(f"GETPANELIDENTIFICATION raw: {panel_id!r}")
    session.set_event_messages()
    log("SETEVENTMESSAGES ok (subscribed to zone/area/output/user/log events)")
    return session


def run_experiment():
    stats = Stats()

    print("=== SPIKE-002 experiment: arm_home / triggered-event observation + collision stress ===")
    print(f"Target: {HOST}:{PORT}")
    print(f"Observation window: {OBSERVE_SECONDS:.0f}s, idle command every {IDLE_INTERVAL_SECONDS:.0f}s")
    print()
    print(">>> ACTION NEEDED: once you see 'Listening for events...' below, please:")
    print("    0. Make sure the Texecom Connect app is fully closed on all devices for this run.")
    print("    1. Arm the panel to HOME mode via the wall keypad ONLY, wait ~15s, then disarm.")
    print("    2. Deliberately trigger the alarm and let it run through to a manual reset.")
    print("    This run will try to survive/resync through any corrupted frames rather than")
    print("    crashing, so it's OK to proceed even if you see '[resync]' log lines.")
    print()

    session = connect_and_prepare(stats)

    print()
    print("Listening for events...")
    print()

    start = time.time()
    last_idle_sent = 0.0

    while time.time() - start < OBSERVE_SECONDS:
        now = time.time()

        if now - last_idle_sent >= IDLE_INTERVAL_SECONDS:
            last_idle_sent = now
            stats.idle_sent += 1
            try:
                session.get_date_time()
            except TimeoutError as exc:
                log(f"idle GETDATETIME permanently failed: {exc}")
            except (ForcedDisconnect, ProtocolError, OSError) as exc:
                stats.forced_disconnects += 1
                log(f"connection error during idle command: {exc}")
                session = _reconnect(stats)
                if session is None:
                    break
            continue

        try:
            msg_type, payload = session.wait_for_message(timeout=0.5)
            if msg_type == HEADER_TYPE_MESSAGE:
                decoded = decode_message(payload, stats)
                log(f"UNSOLICITED: {decoded} (raw={payload.hex()})")
            else:
                log(f"unexpected frame type {msg_type:#x} outside of a command/response cycle, raw={payload.hex()}")
        except socket.timeout:
            continue
        except (ForcedDisconnect, ProtocolError, OSError) as exc:
            stats.forced_disconnects += 1
            log(f"connection error while listening: {exc}")
            session = _reconnect(stats)
            if session is None:
                break
        except Exception as exc:  # noqa: BLE001 - want to record any unexpected crash, not hide it
            stats.exceptions.append(("recv_loop", str(exc)))
            log(f"UNEXPECTED EXCEPTION in recv loop: {exc}")
            traceback.print_exc()

    if session is not None:
        session.close()
    _print_summary(stats)
    return stats


RECONNECT_ATTEMPTS = 5
RECONNECT_BACKOFF_SECONDS = 5.0


def _reconnect(stats: Stats):
    """Retry reconnecting several times with a short backoff - a single
    other-client-holding-the-session window (e.g. a remote UDL/download
    session) may outlast one immediate retry."""
    reconnect_start = time.time()
    for attempt in range(1, RECONNECT_ATTEMPTS + 1):
        log(f"attempting reconnect (attempt {attempt}/{RECONNECT_ATTEMPTS})...")
        try:
            session = connect_and_prepare(stats)
            stats.reconnects_ok += 1
            log(f"reconnect succeeded in {time.time() - reconnect_start:.2f}s")
            return session
        except Exception as exc:  # noqa: BLE001
            log(f"reconnect attempt {attempt} failed: {exc}")
            if attempt < RECONNECT_ATTEMPTS:
                time.sleep(RECONNECT_BACKOFF_SECONDS)
    stats.exceptions.append(("reconnect", f"failed after {RECONNECT_ATTEMPTS} attempts"))
    log(f"reconnect FAILED after {RECONNECT_ATTEMPTS} attempts")
    return None


def _print_summary(stats: Stats):
    print()
    print("=== Summary ===")
    print(f"Idle commands sent: {stats.idle_sent}")
    print(f"Idle commands ACKed first try (no collision): {stats.idle_acked_first_try}")
    print(f"Idle commands ACKed after an interleaved message (collision handled cleanly): {stats.idle_recovered_via_interleaved_message}")
    print(f"Idle commands that timed out then succeeded on retry: {stats.idle_timed_out_then_retried_ok}")
    print(f"Idle commands that failed permanently: {stats.idle_failed}")
    print(f"Unsolicited messages seen: {stats.messages_seen}")
    print(f"Forced disconnects: {stats.forced_disconnects}")
    print(f"Successful reconnects: {stats.reconnects_ok}")
    print(f"Frame resync events (non-conforming bytes skipped, not fatal): {stats.resync_events}")
    print(f"Total non-frame bytes skipped via resync: {stats.resync_bytes_skipped}")
    print(f"Unhandled exceptions: {len(stats.exceptions)}")
    print()
    print("=== Area events observed ===")
    for ts, area, state in stats.area_events:
        print(f"  {time.strftime('%H:%M:%S', time.localtime(ts))}  area={area}  state={state}")
    print()
    print("=== Log events observed ===")
    for ts, event_type, event_str, group in stats.log_events:
        print(f"  {time.strftime('%H:%M:%S', time.localtime(ts))}  type={event_type} ({event_str})  group={group}")
    if stats.exceptions:
        print()
        print("=== Exceptions ===")
        for where, msg in stats.exceptions:
            print(f"  [{where}] {msg}")


if __name__ == "__main__":
    try:
        run_experiment()
    except Exception as exc:  # noqa: BLE001 - top-level: report, don't hide
        print(f"FATAL: experiment crashed: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
