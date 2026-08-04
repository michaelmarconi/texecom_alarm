"""Asyncio Texecom Connect protocol client: login, keepalive, frame resync."""

from __future__ import annotations

import asyncio
import logging

from texecom_alarm.protocol.frame import (
    ACK,
    CMD_GETDATETIME,
    CMD_LOGIN,
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

    async def send_command(
        self,
        cmd: int,
        body: bytes = b"",
        *,
        retries: int = 1,
    ) -> bytes:
        if self._writer is None or self._reader is None:
            raise ProtocolError("not connected")

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
