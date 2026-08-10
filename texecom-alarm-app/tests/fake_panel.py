"""Asyncio FakePanel test double — Connect-protocol login, keepalive, garbage."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from texecom_alarm.protocol.crc import crc8
from texecom_alarm.protocol.frame import (
    ACK,
    AREA_FLAGS_COUNT,
    AREA_MAP,
    CMD_GET_AREA_FLAGS,
    CMD_GET_ZONE_STATE,
    CMD_GETDATETIME,
    CMD_GETPANELIDENTIFICATION,
    CMD_GETZONEDETAILS,
    CMD_LOGIN,
    CMD_SET_AREA_ARM,
    CMD_SET_AREA_DISARM,
    CMD_SETEVENTMESSAGES,
    HEADER_START,
    MSG_AREA,
    MSG_ZONE,
    NAK,
    TYPE_COMMAND,
    TYPE_MESSAGE,
    TYPE_RESPONSE,
    Frame,
    encode_frame,
    try_decode_frame,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FakeZone:
    """Configured zone slot for FakePanel enumeration responses."""

    number: int
    zone_type: int
    name: str
    status: int = 0


class FakePanel:
    """Minimal asyncio TCP panel double for protocol-client tests."""

    def __init__(
        self,
        udl_password: str = "1234",
        *,
        zones: Sequence[FakeZone] | None = None,
        zone_count: int | None = None,
    ) -> None:
        self.udl_password = udl_password
        self.host = "127.0.0.1"
        self.port = 0
        self._server: asyncio.Server | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.authenticated = False
        self.inject_bytes: bytes = b""
        self.drop_next_command_responses = 0
        self.drop_login_responses = 0
        self.last_command: int | None = None
        self.commands_seen: list[int] = []
        self.keepalive_attempts = 0
        self.keepalive_sequences: list[int] = []
        # When True, accept GETDATETIME (count it) but never reply — mid-run
        # health-check death for session-heal tests (ADR-011). Clear to accept again.
        self.silence_keepalive = False
        self.resync_survivals = 0
        self.interleave_message_before_response: bytes | None = None
        self.stale_sequence_before_response = False
        self.wrong_cmd_before_response = False
        self.close_on_next_command = False
        self.plusplusplus_on_next_command = False
        self.command_frame_before_response = False
        self._zones = {z.number: z for z in (zones or ())}
        if zone_count is not None:
            self.zone_count = zone_count
        elif self._zones:
            self.zone_count = max(self._zones)
        else:
            self.zone_count = 0
        self.zone_detail_queries: list[int] = []
        self.zone_state_override: bytes | None = None
        self.area_flags_override: bytes | None = None
        self.area_flags_calls = 0
        self.nak_next_area_flags = 0
        self.last_seteventmessages_body: bytes | None = None
        self.seteventmessages_calls = 0
        self.last_arm_mode: int | None = None
        self.last_arm_body: bytes | None = None
        self.arm_calls: list[int] = []
        self.nak_next_arm = False
        self.nak_next_disarm = False
        self.last_disarm_body: bytes | None = None
        self.disarm_calls = 0
        self._handlers: dict[int, Callable[[Frame], bytes]] = {
            CMD_LOGIN: self._handle_login,
            CMD_GETDATETIME: self._handle_getdatetime,
            CMD_GETPANELIDENTIFICATION: self._handle_get_panel_identification,
            CMD_GETZONEDETAILS: self._handle_get_zone_details,
            CMD_GET_ZONE_STATE: self._handle_get_zone_state,
            CMD_GET_AREA_FLAGS: self._handle_get_area_flags,
            CMD_SETEVENTMESSAGES: self._handle_set_event_messages,
            CMD_SET_AREA_ARM: self._handle_set_area_arm,
            CMD_SET_AREA_DISARM: self._handle_set_area_disarm,
        }

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._on_client, self.host, 0)
        sockets = self._server.sockets
        if not sockets:
            raise RuntimeError("FakePanel failed to bind")
        self.port = sockets[0].getsockname()[1]
        logger.debug("fake_panel_started", extra={"port": self.port})

    async def stop(self) -> None:
        if self._writer is not None and not self._writer.is_closing():
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def inject_before_next_response(self, junk: bytes) -> None:
        self.inject_bytes = junk

    async def inject_zone_message(self, zone_number: int, status: int) -> None:
        """Push an unsolicited ZONE ``'M'`` frame to the connected client."""
        writer = self._writer
        if writer is None or writer.is_closing():
            raise RuntimeError("FakePanel has no connected client")
        body = bytes([MSG_ZONE, zone_number, status])
        writer.write(encode_frame(TYPE_MESSAGE, 0, body))
        await writer.drain()

    async def inject_area_message(self, area_number: int, state: int) -> None:
        """Push an unsolicited AREA ``'M'`` frame to the connected client."""
        writer = self._writer
        if writer is None or writer.is_closing():
            raise RuntimeError("FakePanel has no connected client")
        body = bytes([MSG_AREA, area_number, state])
        writer.write(encode_frame(TYPE_MESSAGE, 0, body))
        await writer.drain()

    async def inject_push_body(self, body: bytes) -> None:
        """Push a raw unsolicited ``'M'`` body (for TRACE ignored-event tests)."""
        writer = self._writer
        if writer is None or writer.is_closing():
            raise RuntimeError("FakePanel has no connected client")
        writer.write(encode_frame(TYPE_MESSAGE, 0, body))
        await writer.drain()

    async def force_disconnect(self) -> None:
        """Close the current TCP client session (mid-session drop for reconnect tests)."""
        writer = self._writer
        if writer is None or writer.is_closing():
            raise RuntimeError("FakePanel has no connected client")
        writer.close()
        await writer.wait_closed()
        if self._writer is writer:
            self._writer = None
        self.authenticated = False

    def connect(self) -> None:
        """Sync stub retained for older e2e smoke shape."""
        self.authenticated = False

    def close(self) -> None:
        """Sync stub retained for older e2e smoke shape."""
        self.authenticated = False

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writer = writer
        buf = bytearray()
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buf.extend(chunk)
                while True:
                    frame, consumed = try_decode_frame(buf)
                    if consumed == 0:
                        break
                    del buf[:consumed]
                    if frame is None:
                        continue
                    await self._handle_frame(frame, writer)
        finally:
            writer.close()
            await writer.wait_closed()
            if self._writer is writer:
                self._writer = None

    async def _handle_frame(self, frame: Frame, writer: asyncio.StreamWriter) -> None:
        if frame.msg_type != TYPE_COMMAND or not frame.body:
            return
        cmd = frame.body[0]
        self.last_command = cmd
        self.commands_seen.append(cmd)
        if cmd == CMD_GETDATETIME:
            self.keepalive_attempts += 1
            self.keepalive_sequences.append(frame.sequence)

        handler = self._handlers.get(cmd)
        if handler is None:
            return
        resp_body = handler(frame)

        if cmd != CMD_LOGIN and self.close_on_next_command:
            self.close_on_next_command = False
            writer.close()
            return

        if cmd != CMD_LOGIN and self.plusplusplus_on_next_command:
            self.plusplusplus_on_next_command = False
            writer.write(b"+++")
            await writer.drain()
            return

        if cmd == CMD_LOGIN and self.drop_login_responses > 0:
            self.drop_login_responses -= 1
            logger.debug("fake_panel_dropped_login_response")
            return

        if cmd != CMD_LOGIN and self.drop_next_command_responses > 0:
            self.drop_next_command_responses -= 1
            logger.debug("fake_panel_dropped_response", extra={"cmd": cmd})
            return

        if cmd == CMD_GETDATETIME and self.silence_keepalive:
            logger.debug("fake_panel_silenced_keepalive")
            return

        if self.inject_bytes:
            junk = self.inject_bytes
            self.inject_bytes = b""
            writer.write(junk)
            await writer.drain()
            self.resync_survivals += 1
            logger.debug("fake_panel_injected_garbage", extra={"bytes": junk.hex()})

        if self.interleave_message_before_response is not None:
            msg_body = self.interleave_message_before_response
            self.interleave_message_before_response = None
            writer.write(encode_frame(TYPE_MESSAGE, 0, msg_body))
            await writer.drain()

        if self.command_frame_before_response:
            self.command_frame_before_response = False
            writer.write(encode_frame(TYPE_COMMAND, frame.sequence, bytes([CMD_GETDATETIME])))
            await writer.drain()

        if self.stale_sequence_before_response:
            self.stale_sequence_before_response = False
            writer.write(encode_frame(TYPE_RESPONSE, (frame.sequence + 1) % 256, resp_body))
            await writer.drain()

        if self.wrong_cmd_before_response:
            self.wrong_cmd_before_response = False
            writer.write(encode_frame(TYPE_RESPONSE, frame.sequence, bytes([0xFF, ACK])))
            await writer.drain()
            return

        response = encode_frame(TYPE_RESPONSE, frame.sequence, resp_body)
        # Sanity: CRC must be valid on the wire we emit.
        assert response[-1] == crc8(response[:-1])
        assert response[0] == HEADER_START
        writer.write(response)
        await writer.drain()

    def _handle_login(self, frame: Frame) -> bytes:
        password = frame.body[1:].decode("ascii", errors="replace")
        if password == self.udl_password:
            self.authenticated = True
            # New session after mid-run health-check death: answer keepalive again.
            self.silence_keepalive = False
            return bytes([CMD_LOGIN, ACK])
        return bytes([CMD_LOGIN, 0x15])

    def _handle_getdatetime(self, frame: Frame) -> bytes:
        # Minimal opaque datetime payload after the command echo byte.
        return bytes([CMD_GETDATETIME, 0x18, 0x08, 0x04, 0x0E, 0x25, 0x00])

    def _handle_get_panel_identification(self, frame: Frame) -> bytes:
        # 32-byte identification string; second whitespace token is zone count.
        text = f"Elite {self.zone_count}     ENG->SW V6.02.02LS1"
        payload = text.encode("ascii")[:32].ljust(32, b" ")
        return bytes([CMD_GETPANELIDENTIFICATION]) + payload

    def _handle_get_zone_details(self, frame: Frame) -> bytes:
        if len(frame.body) < 2:
            return bytes([CMD_GETZONEDETAILS, 0x15])
        zone_number = frame.body[1]
        self.zone_detail_queries.append(zone_number)
        zone = self._zones.get(zone_number)
        if zone is None:
            zone = FakeZone(number=zone_number, zone_type=0, name="")
        # 34-byte payload: type, area bitmap, 32-byte null-padded name.
        name_bytes = zone.name.encode("ascii", errors="replace")[:32].ljust(32, b"\x00")
        payload = bytes([zone.zone_type, 0x01]) + name_bytes
        return bytes([CMD_GETZONEDETAILS]) + payload

    def _handle_get_zone_state(self, frame: Frame) -> bytes:
        if self.zone_state_override is not None:
            override = self.zone_state_override
            self.zone_state_override = None
            return bytes([CMD_GET_ZONE_STATE]) + override
        if len(frame.body) < 3:
            return bytes([CMD_GET_ZONE_STATE, NAK])
        start = frame.body[1]
        count = frame.body[2]
        statuses = bytearray()
        for number in range(start, start + count):
            zone = self._zones.get(number)
            statuses.append(0 if zone is None else zone.status)
        return bytes([CMD_GET_ZONE_STATE]) + bytes(statuses)

    def _handle_get_area_flags(self, frame: Frame) -> bytes:
        self.area_flags_calls += 1
        if self.nak_next_area_flags > 0:
            self.nak_next_area_flags -= 1
            return bytes([CMD_GET_AREA_FLAGS, NAK])
        if self.area_flags_override is not None:
            override = self.area_flags_override
            self.area_flags_override = None
            return bytes([CMD_GET_AREA_FLAGS]) + override
        if len(frame.body) < 3:
            return bytes([CMD_GET_AREA_FLAGS, NAK])
        start = frame.body[1]
        count = frame.body[2]
        areas = AREA_MAP.get(self.zone_count, 8)
        area_size = (areas + 7) // 8
        # Quiet panel: all flag bytes zero (Disarmed for every area).
        payload = bytes(count * area_size)
        # start is ignored for the quiet default; override covers non-zero cases.
        _ = start
        if count > AREA_FLAGS_COUNT and area_size == 1:
            return bytes([CMD_GET_AREA_FLAGS, NAK])
        return bytes([CMD_GET_AREA_FLAGS]) + payload

    def _handle_set_event_messages(self, frame: Frame) -> bytes:
        self.seteventmessages_calls += 1
        self.last_seteventmessages_body = frame.body[1:]
        return bytes([CMD_SETEVENTMESSAGES, ACK])

    def _handle_set_area_arm(self, frame: Frame) -> bytes:
        body = frame.body[1:]
        self.last_arm_body = body
        if body:
            self.last_arm_mode = body[0]
            self.arm_calls.append(body[0])
        if self.nak_next_arm:
            self.nak_next_arm = False
            return bytes([CMD_SET_AREA_ARM, NAK])
        return bytes([CMD_SET_AREA_ARM, ACK])

    def _handle_set_area_disarm(self, frame: Frame) -> bytes:
        self.last_disarm_body = frame.body[1:]
        self.disarm_calls += 1
        if self.nak_next_disarm:
            self.nak_next_disarm = False
            return bytes([CMD_SET_AREA_DISARM, NAK])
        return bytes([CMD_SET_AREA_DISARM, ACK])
