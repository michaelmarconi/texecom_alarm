"""Asyncio Texecom Connect protocol client: login, keepalive, frame resync."""

from __future__ import annotations

import asyncio
import logging

from texecom_alarm.logging_setup import TRACE_LEVEL
from texecom_alarm.protocol.frame import (
    ACK,
    AREA_FLAGS_COUNT,
    CMD_GET_AREA_FLAGS,
    CMD_GET_ZONE_STATE,
    CMD_GETDATETIME,
    CMD_GETPANELIDENTIFICATION,
    CMD_GETZONEDETAILS,
    CMD_LOGIN,
    CMD_SET_AREA_ARM,
    CMD_SET_AREA_DISARM,
    CMD_SETEVENTMESSAGES,
    MAX_ZONES_PER_STATE_REQUEST,
    NAK,
    TYPE_MESSAGE,
    TYPE_RESPONSE,
    Frame,
    encode_command,
    try_decode_frame,
)

logger = logging.getLogger(__name__)

# Human labels for panel commands that appear in operator-facing errors.
_CMD_LABELS: dict[int, str] = {
    CMD_LOGIN: "LOGIN",
    CMD_GET_ZONE_STATE: "GetZoneState",
    CMD_GETZONEDETAILS: "GETZONEDETAILS",
    CMD_GETPANELIDENTIFICATION: "GETPANELIDENTIFICATION",
    CMD_GETDATETIME: "GETDATETIME (keepalive)",
    CMD_GET_AREA_FLAGS: "GetAreaFlags",
    CMD_SET_AREA_ARM: "SETAREAARM",
    CMD_SET_AREA_DISARM: "SETAREADISARM",
    CMD_SETEVENTMESSAGES: "SETEVENTMESSAGES",
}


class ProtocolError(Exception):
    """Raised for protocol-level failures that are not recoverable by resync."""


class ForcedDisconnect(Exception):
    """Panel ended the session (``+++`` or peer close)."""


class PanelClient:
    """TCP Connect-protocol session with resync and same-sequence retries."""

    def __init__(
        self,
        host: str,
        port: int,
        udl_password: str,
        *,
        login_delay: float = 0.5,
        response_timeout: float = 2.0,
        keepalive_retries: int = 1,
    ) -> None:
        self.host = host
        self.port = port
        self.udl_password = udl_password
        self.login_delay = login_delay
        self.response_timeout = response_timeout
        self.keepalive_retries = keepalive_retries
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._buf = bytearray()
        self._seq = 0
        self._authenticated = False
        self._had_transport = False
        self._message_queue: asyncio.Queue[Frame] = asyncio.Queue()
        self._io_lock = asyncio.Lock()
        self._pending_cmd: int | None = None

    def _not_connected_error(self, *, action: str) -> Exception:
        """ProtocolError if never connected; ForcedDisconnect after a torn-down session."""
        if self._had_transport:
            return ForcedDisconnect(
                f"Panel session at {self.host}:{self.port} is gone — cannot {action}. "
                "The add-on will reconnect."
            )
        return ProtocolError(
            f"Not connected to the panel — cannot {action}. "
            "Wait for a successful login or check panel_host."
        )

    @staticmethod
    def command_label(cmd: int) -> str:
        return _CMD_LABELS.get(cmd, f"command {cmd}")

    @staticmethod
    def timeout_message(cmd: int, *, host: str, port: int) -> str:
        """Operator-readable timeout for a panel command that got no reply."""
        label = PanelClient.command_label(cmd)
        if cmd == CMD_LOGIN:
            return (
                f"Panel at {host}:{port} did not answer LOGIN in time. "
                "Usually another device still holds the single ComIP connection "
                "(Texecom app, another add-on, or a stuck previous session), "
                "or the panel is briefly busy — stop other clients and retry."
            )
        if cmd == CMD_GETDATETIME:
            return (
                f"Panel at {host}:{port} did not answer keepalive ({label}). "
                "The session may be dead or the panel overloaded."
            )
        return (
            f"Panel at {host}:{port} did not answer {label} in time. "
            "Check panel power/network and that nothing else holds ComIP."
        )

    @staticmethod
    def login_failure_message(payload: bytes) -> str:
        """Operator-readable LOGIN rejection (panel answered but did not accept)."""
        return (
            "Panel rejected LOGIN — check the UDL password in add-on Configuration. "
            f"(panel reply: {payload!r})"
        )

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    async def connect(self) -> None:
        logger.debug(
            "panel_connect",
            extra={"host": self.host, "port": self.port},
        )
        try:
            self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        except OSError as exc:
            raise OSError(
                f"Could not open a network connection to the panel at "
                f"{self.host}:{self.port}: {exc}. "
                "Check panel_host/panel_port, LAN routing, and that the panel is powered."
            ) from exc
        self._buf.clear()
        self._authenticated = False
        self._had_transport = True
        self._message_queue = asyncio.Queue()
        if self.login_delay > 0:
            await asyncio.sleep(self.login_delay)

    async def close(self) -> None:
        """Tear down the TCP session after any in-flight ``send_command`` finishes.

        Acquires ``_io_lock`` so reconnect teardown cannot null reader/writer
        under a concurrent arm/disarm or keepalive command.
        """
        logger.debug("panel_close")
        async with self._io_lock:
            self._authenticated = False
            writer = self._writer
            self._reader = None
            self._writer = None
            self._buf.clear()
        if writer is not None:
            writer.close()
            await writer.wait_closed()

    async def login(self) -> None:
        logger.debug("panel_login")
        payload = await self.send_command(
            CMD_LOGIN,
            self.udl_password.encode("ascii"),
            retries=self.keepalive_retries,
        )
        if len(payload) == 1 and payload[0] == ACK:
            self._authenticated = True
            logger.debug("panel_login_ok")
            return
        raise ProtocolError(self.login_failure_message(payload))

    async def keepalive(self) -> bytes:
        """Send GETDATETIME; on short timeout retry once with the same sequence."""
        logger.debug("panel_keepalive")
        return await self.send_command(
            CMD_GETDATETIME,
            retries=self.keepalive_retries,
        )

    async def get_zone_state(self, start: int, count: int) -> bytes:
        """GetZoneState (cmd 2): return exactly ``count`` status bytes.

        Uses 1-byte ``startZone`` (panels with ≤256 zones). Batches must be
        at most ``MAX_ZONES_PER_STATE_REQUEST`` (168).
        """
        if count < 1 or count > MAX_ZONES_PER_STATE_REQUEST:
            raise ProtocolError(
                f"GetZoneState: count {count} out of range 1..{MAX_ZONES_PER_STATE_REQUEST}"
            )
        if not (1 <= start <= 255):
            raise ProtocolError(f"GetZoneState: start {start} out of 1-byte range")
        logger.debug("panel_get_zone_state", extra={"start": start, "count": count})
        payload = await self.send_command(CMD_GET_ZONE_STATE, bytes([start, count]))
        # Success is exactly ``count`` status bytes. A status byte may be NAK (0x15)
        # when higher bits are set (e.g. Active+fault+alarmed) — so only treat a
        # single-byte NAK as failure when length does not match the requested count
        # (same length-first pattern as multi-byte reads like GETZONEDETAILS).
        if len(payload) != count:
            if len(payload) == 1 and payload[0] == NAK:
                raise ProtocolError(
                    "Panel rejected reading zone states (GetZoneState NAK). "
                    "Try again; if it keeps failing, check the panel connection."
                )
            raise ProtocolError(
                f"Panel returned an unexpected zone-state reply "
                f"(wanted {count} status bytes, got {len(payload)})."
            )
        return payload

    async def get_area_flags(self, start: int, count: int, *, area_size: int = 1) -> bytes:
        """GetAreaFlags (cmd 11): return exactly ``count * area_size`` flag bytes.

        Elite 88 path (ADR-007 / SPIKE-007): ``area_size=1``, ``start=0``,
        ``count=72`` (``AREA_FLAGS_COUNT``). Dual-request ``area_size==8`` panels
        are out of scope for this task.
        """
        if count < 1 or count > AREA_FLAGS_COUNT:
            raise ProtocolError(f"GetAreaFlags: count {count} out of range 1..{AREA_FLAGS_COUNT}")
        if not (0 <= start <= 255):
            raise ProtocolError(f"GetAreaFlags: start {start} out of 1-byte range")
        if area_size < 1:
            raise ProtocolError(f"GetAreaFlags: area_size {area_size} must be >= 1")
        expected = count * area_size
        logger.debug(
            "panel_get_area_flags",
            extra={"start": start, "count": count, "area_size": area_size},
        )
        payload = await self.send_command(CMD_GET_AREA_FLAGS, bytes([start, count]))
        if len(payload) != expected:
            if len(payload) == 1 and payload[0] == NAK:
                raise ProtocolError(
                    "Panel rejected reading area/arm flags (GetAreaFlags NAK). "
                    "Try again; if it keeps failing, check the panel connection."
                )
            raise ProtocolError(
                f"Panel returned an unexpected area-flags reply "
                f"(wanted {expected} bytes, got {len(payload)})."
            )
        return payload

    async def set_event_messages(self) -> None:
        """SETEVENTMESSAGES (cmd 37): subscribe to DEBUG|ZONE|AREA|OUTPUT|USER|LOG."""
        events = 1 | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)
        body = bytes([events & 0xFF, (events >> 8) & 0xFF])
        logger.debug("panel_set_event_messages", extra={"mask": events})
        payload = await self.send_command(CMD_SETEVENTMESSAGES, body)
        if len(payload) >= 1 and payload[0] == NAK:
            raise ProtocolError(
                "Panel rejected event subscription (SETEVENTMESSAGES NAK). "
                "Zone/area live updates may not arrive until this succeeds."
            )
        logger.debug("panel_set_event_messages_ok")

    async def set_area_arm(self, mode: int) -> None:
        """SETAREAARM (cmd 6): shared arm command; mode byte from Settings mapping."""
        body = bytes([mode & 0xFF, 0x01])
        logger.debug("panel_set_area_arm mode=%s", mode & 0xFF)
        payload = await self.send_command(CMD_SET_AREA_ARM, body)
        if len(payload) >= 1 and payload[0] == NAK:
            raise ProtocolError(
                "Panel rejected the arm command (SETAREAARM NAK). "
                "The panel may be busy, already armed differently, or blocking the request."
            )
        logger.debug("panel_set_area_arm_ok mode=%s", mode & 0xFF)

    async def set_area_disarm(self) -> None:
        """SETAREADISARM (cmd 8): mode-independent disarm / cancel-during-exit."""
        logger.debug("panel_set_area_disarm")
        payload = await self.send_command(CMD_SET_AREA_DISARM, bytes([0x01]))
        if len(payload) >= 1 and payload[0] == NAK:
            raise ProtocolError(
                "Panel rejected the disarm command (SETAREADISARM NAK). "
                "The panel may be busy or already disarmed."
            )
        logger.debug("panel_set_area_disarm_ok")

    async def recv_message(self, *, timeout: float | None = None) -> Frame:
        """Return the next queued unsolicited ``'M'`` frame, or wait for one."""
        if not self._message_queue.empty():
            return self._message_queue.get_nowait()
        if self._reader is None:
            raise ProtocolError("Not connected to the panel — cannot wait for zone/area messages.")
        wait_timeout = self.response_timeout if timeout is None else timeout
        deadline = asyncio.get_running_loop().time() + wait_timeout
        # Poll in short slices so MQTT-driven send_command can acquire _io_lock.
        _poll = 0.05
        while True:
            if not self._message_queue.empty():
                return self._message_queue.get_nowait()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    f"No panel message within {wait_timeout:g}s "
                    f"(idle wait on {self.host}:{self.port})."
                )
            slice_timeout = min(remaining, _poll)
            async with self._io_lock:
                if not self._message_queue.empty():
                    return self._message_queue.get_nowait()
                try:
                    frame = await self._recv_frame(timeout=slice_timeout)
                except TimeoutError:
                    continue
            if frame.msg_type == TYPE_MESSAGE:
                return frame
            logger.debug(
                "panel_recv_message_skip",
                extra={"msg_type": frame.msg_type},
            )

    async def send_command(
        self,
        cmd: int,
        body: bytes = b"",
        *,
        retries: int = 1,
    ) -> bytes:
        async with self._io_lock:
            if self._writer is None or self._reader is None:
                raise self._not_connected_error(action="send commands")
            if cmd != CMD_LOGIN and not self._authenticated:
                raise ProtocolError(
                    "Not authenticated to the panel — cannot send commands before LOGIN. "
                    "Wait for a successful login."
                )
            seq = self._next_seq()
            frame = encode_command(cmd, body, sequence=seq)
            attempt = 0
            self._pending_cmd = cmd
            try:
                while True:
                    self._writer.write(frame)
                    await self._writer.drain()
                    logger.log(
                        TRACE_LEVEL,
                        "panel_tx %s seq=%s attempt=%s %s bytes",
                        self.command_label(cmd),
                        seq,
                        attempt,
                        len(frame),
                    )
                    try:
                        return await self._await_response(cmd, seq)
                    except TimeoutError:
                        attempt += 1
                        if attempt > retries:
                            raise TimeoutError(
                                self.timeout_message(cmd, host=self.host, port=self.port)
                            ) from None
                        logger.debug(
                            "panel_command_retry",
                            extra={"cmd": cmd, "seq": seq, "attempt": attempt},
                        )
            finally:
                self._pending_cmd = None

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq = (self._seq + 1) % 256
        return seq

    async def _await_response(self, expected_cmd: int, expected_seq: int) -> bytes:
        deadline = asyncio.get_running_loop().time() + self.response_timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    self.timeout_message(expected_cmd, host=self.host, port=self.port)
                )
            frame = await self._recv_frame(timeout=remaining)
            if frame.msg_type == TYPE_MESSAGE:
                logger.debug(
                    "panel_interleaved_message",
                    extra={"seq": frame.sequence, "body": frame.body.hex()},
                )
                self._message_queue.put_nowait(frame)
                continue
            if frame.msg_type != TYPE_RESPONSE:
                logger.debug(
                    "panel_unexpected_type_resync_continue",
                    extra={"msg_type": frame.msg_type},
                )
                continue
            if frame.sequence != expected_seq:
                continue
            if not frame.body or frame.body[0] != expected_cmd:
                raise ProtocolError(
                    f"Panel reply did not match the waiting command "
                    f"(got {frame.body[:1]!r}, expected {self.command_label(expected_cmd)})."
                )
            return frame.body[1:]

    async def _recv_frame(self, *, timeout: float) -> Frame:
        """Read the next valid frame, skipping non-protocol bytes (ADR-002)."""
        reader = self._reader
        if reader is None:
            raise self._not_connected_error(action="read from the session")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        skipped = 0
        skipped_bytes = bytearray()
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                pending = self._pending_cmd
                if pending is not None:
                    raise TimeoutError(
                        self.timeout_message(pending, host=self.host, port=self.port)
                    )
                raise TimeoutError(
                    f"Timed out waiting for data from the panel at {self.host}:{self.port}."
                )

            frame, consumed = try_decode_frame(self._buf)
            if consumed > 0:
                if frame is None and consumed == 3 and bytes(self._buf[:3]) == b"+++":
                    del self._buf[:consumed]
                    raise ForcedDisconnect(
                        f"Panel at {self.host}:{self.port} ended the session (sent +++). "
                        "The add-on will reconnect. Session drops around arm/disarm or a "
                        "real trigger are mainly expected when Home Assistant shares the "
                        "alarm-reporting module — not on a dedicated local ComIP."
                    )
                discarded = bytes(self._buf[:consumed])
                del self._buf[:consumed]
                if frame is None:
                    # Non-frame bytes (modem piping, bad CRC lead-in, etc.): silent at
                    # WARNING–DEBUG; one compact TRACE notice (count + hex) when a
                    # valid frame follows — not a continuous stream dump.
                    skipped += consumed
                    skipped_bytes.extend(discarded)
                    continue
                if skipped:
                    # Cap hex so a long skip stays one compact line (TRACE hunt aid).
                    _hex_cap = 64
                    hex_part = bytes(skipped_bytes[:_hex_cap]).hex()
                    if len(skipped_bytes) > _hex_cap:
                        hex_part = f"{hex_part}…(+{len(skipped_bytes) - _hex_cap}B)"
                    logger.log(
                        TRACE_LEVEL,
                        "panel_resync skipped %s bytes hex=%s",
                        skipped,
                        hex_part,
                    )
                logger.log(
                    TRACE_LEVEL,
                    "panel_rx type=%r seq=%s %s bytes",
                    chr(frame.msg_type) if 32 <= frame.msg_type < 127 else frame.msg_type,
                    frame.sequence,
                    len(frame.body),
                )
                return frame

            # Need more bytes. TimeoutError is an OSError subclass — catch it first.
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=remaining)
            except TimeoutError:
                pending = self._pending_cmd
                if pending is not None:
                    raise TimeoutError(
                        self.timeout_message(pending, host=self.host, port=self.port)
                    ) from None
                raise TimeoutError(
                    f"Timed out waiting for data from the panel at {self.host}:{self.port}."
                ) from None
            except (OSError, asyncio.IncompleteReadError) as exc:
                raise ForcedDisconnect(
                    f"Panel at {self.host}:{self.port} dropped the network connection "
                    f"({exc}). The add-on will reconnect."
                ) from exc
            if not chunk:
                raise ForcedDisconnect(
                    f"Panel at {self.host}:{self.port} closed the network connection. "
                    "Another client may have taken ComIP, or the panel restarted; "
                    "the add-on will reconnect."
                )
            self._buf.extend(chunk)
