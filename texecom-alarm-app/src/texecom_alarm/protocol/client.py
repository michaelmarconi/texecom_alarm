"""Asyncio Texecom Connect protocol client: login, keepalive, frame resync."""

from __future__ import annotations

import asyncio
import logging

from texecom_alarm.protocol.frame import (
    ACK,
    AREA_FLAGS_COUNT,
    CMD_GET_AREA_FLAGS,
    CMD_GET_ZONE_STATE,
    CMD_GETDATETIME,
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
        self._message_queue: asyncio.Queue[Frame] = asyncio.Queue()
        self._io_lock = asyncio.Lock()

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    async def connect(self) -> None:
        logger.debug(
            "panel_connect",
            extra={"host": self.host, "port": self.port},
        )
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._buf.clear()
        self._authenticated = False
        self._message_queue = asyncio.Queue()
        if self.login_delay > 0:
            await asyncio.sleep(self.login_delay)

    async def close(self) -> None:
        logger.debug("panel_close")
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
        raise ProtocolError(f"LOGIN failed: {payload!r}")

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
                raise ProtocolError("GetZoneState NAK")
            raise ProtocolError(f"GetZoneState: expected {count} status bytes, got {len(payload)}")
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
                raise ProtocolError("GetAreaFlags NAK")
            raise ProtocolError(f"GetAreaFlags: expected {expected} flag bytes, got {len(payload)}")
        return payload

    async def set_event_messages(self) -> None:
        """SETEVENTMESSAGES (cmd 37): subscribe to DEBUG|ZONE|AREA|OUTPUT|USER|LOG."""
        events = 1 | (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)
        body = bytes([events & 0xFF, (events >> 8) & 0xFF])
        logger.debug("panel_set_event_messages", extra={"mask": events})
        payload = await self.send_command(CMD_SETEVENTMESSAGES, body)
        if len(payload) >= 1 and payload[0] == NAK:
            raise ProtocolError("SETEVENTMESSAGES NAK")
        logger.debug("panel_set_event_messages_ok")

    async def set_area_arm(self, mode: int) -> None:
        """SETAREAARM (cmd 6): shared arm command; mode byte from Settings mapping."""
        body = bytes([mode & 0xFF, 0x01])
        logger.debug("panel_set_area_arm", extra={"mode": mode & 0xFF})
        payload = await self.send_command(CMD_SET_AREA_ARM, body)
        if len(payload) >= 1 and payload[0] == NAK:
            raise ProtocolError("SETAREAARM NAK")
        logger.debug("panel_set_area_arm_ok", extra={"mode": mode & 0xFF})

    async def set_area_disarm(self) -> None:
        """SETAREADISARM (cmd 8): mode-independent disarm / cancel-during-exit."""
        logger.debug("panel_set_area_disarm")
        payload = await self.send_command(CMD_SET_AREA_DISARM, bytes([0x01]))
        if len(payload) >= 1 and payload[0] == NAK:
            raise ProtocolError("SETAREADISARM NAK")
        logger.debug("panel_set_area_disarm_ok")

    async def recv_message(self, *, timeout: float | None = None) -> Frame:
        """Return the next queued unsolicited ``'M'`` frame, or wait for one."""
        if not self._message_queue.empty():
            return self._message_queue.get_nowait()
        if self._reader is None:
            raise ProtocolError("not connected")
        wait_timeout = self.response_timeout if timeout is None else timeout
        deadline = asyncio.get_running_loop().time() + wait_timeout
        # Poll in short slices so MQTT-driven send_command can acquire _io_lock.
        _poll = 0.05
        while True:
            if not self._message_queue.empty():
                return self._message_queue.get_nowait()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for message")
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
        if self._writer is None or self._reader is None:
            raise ProtocolError("not connected")

        async with self._io_lock:
            seq = self._next_seq()
            frame = encode_command(cmd, body, sequence=seq)
            attempt = 0
            while True:
                self._writer.write(frame)
                await self._writer.drain()
                logger.debug(
                    "panel_command_sent",
                    extra={"cmd": cmd, "seq": seq, "attempt": attempt},
                )
                try:
                    return await self._await_response(cmd, seq)
                except TimeoutError:
                    attempt += 1
                    if attempt > retries:
                        raise
                    logger.debug(
                        "panel_command_retry",
                        extra={"cmd": cmd, "seq": seq, "attempt": attempt},
                    )

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq = (self._seq + 1) % 256
        return seq

    async def _await_response(self, expected_cmd: int, expected_seq: int) -> bytes:
        deadline = asyncio.get_running_loop().time() + self.response_timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"no response to cmd {expected_cmd}")
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
                raise ProtocolError(f"response cmd {frame.body[:1]!r} != expected {expected_cmd}")
            return frame.body[1:]

    async def _recv_frame(self, *, timeout: float) -> Frame:
        """Read the next valid frame, skipping non-protocol bytes (ADR-002)."""
        reader = self._reader
        if reader is None:
            raise ProtocolError("not connected")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        skipped = 0
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("timed out waiting for frame")

            frame, consumed = try_decode_frame(self._buf)
            if consumed > 0:
                if frame is None and consumed == 3 and bytes(self._buf[:3]) == b"+++":
                    del self._buf[:consumed]
                    raise ForcedDisconnect("panel sent +++")
                del self._buf[:consumed]
                if frame is None:
                    skipped += consumed
                    logger.debug(
                        "panel_frame_resync",
                        extra={"skipped_total": skipped},
                    )
                    continue
                if skipped:
                    logger.debug(
                        "panel_frame_resync_complete",
                        extra={"bytes_skipped": skipped},
                    )
                return frame

            # Need more bytes.
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=remaining)
            except TimeoutError:
                raise TimeoutError("timed out waiting for frame") from None
            if not chunk:
                raise ForcedDisconnect("socket closed by peer")
            self._buf.extend(chunk)
