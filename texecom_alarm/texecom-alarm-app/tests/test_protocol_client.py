"""Async client tests against FakePanel — login, resync, keepalive retry."""

from __future__ import annotations

import asyncio

import pytest
from tests.fake_panel import FakePanel, FakeZone

from texecom_alarm.protocol.client import ForcedDisconnect, PanelClient, ProtocolError
from texecom_alarm.protocol.frame import (
    CMD_GET_AREA_FLAGS,
    CMD_GETDATETIME,
    CMD_SET_AREA_ARM,
    CMD_SET_AREA_DISARM,
    CMD_SETEVENTMESSAGES,
    MSG_AREA,
    MSG_ZONE,
)


@pytest.fixture
async def panel() -> FakePanel:
    fp = FakePanel(udl_password="1234")
    await fp.start()
    yield fp
    await fp.stop()


async def _logged_in_client(panel: FakePanel, **kwargs: float | int) -> PanelClient:
    opts = {
        "login_delay": 0.0,
        "response_timeout": 0.5,
        **kwargs,
    }
    client = PanelClient(panel.host, panel.port, udl_password="1234", **opts)  # type: ignore[arg-type]
    await client.connect()
    await client.login()
    return client


@pytest.mark.asyncio
async def test_login_yields_authenticated_session(panel: FakePanel) -> None:
    client = await _logged_in_client(panel)
    assert client.authenticated is True
    await client.close()


@pytest.mark.asyncio
async def test_login_respects_post_connect_delay(panel: FakePanel) -> None:
    client = PanelClient(
        panel.host,
        panel.port,
        udl_password="1234",
        login_delay=0.05,
        response_timeout=0.5,
    )
    await client.connect()
    await client.login()
    assert client.authenticated is True
    await client.close()


@pytest.mark.asyncio
async def test_login_nak_raises(panel: FakePanel) -> None:
    client = PanelClient(
        panel.host,
        panel.port,
        udl_password="wrong",
        login_delay=0.0,
        response_timeout=0.5,
    )
    await client.connect()
    with pytest.raises(ProtocolError, match="LOGIN|UDL|password"):
        await client.login()
    await client.close()


@pytest.mark.asyncio
async def test_send_command_requires_connection() -> None:
    client = PanelClient("127.0.0.1", 1, udl_password="1234")
    with pytest.raises(ProtocolError, match="Not connected|not connected"):
        await client.send_command(CMD_GETDATETIME)


@pytest.mark.asyncio
async def test_resync_skips_injected_garbage_without_closing(panel: FakePanel) -> None:
    client = await _logged_in_client(panel)
    panel.inject_before_next_response(b"ATH0\rATZ\r")
    payload = await client.keepalive()
    assert payload is not None
    assert client.authenticated is True
    assert panel.resync_survivals == 1
    await client.close()


@pytest.mark.asyncio
async def test_keepalive_retries_once_with_same_sequence(panel: FakePanel) -> None:
    client = await _logged_in_client(panel, response_timeout=0.15)
    panel.drop_next_command_responses = 1
    await client.keepalive()

    assert panel.last_command == CMD_GETDATETIME
    assert panel.keepalive_attempts == 2
    assert panel.keepalive_sequences[0] == panel.keepalive_sequences[1]
    assert client.authenticated is True
    await client.close()


@pytest.mark.asyncio
async def test_keepalive_timeout_exhausted(panel: FakePanel) -> None:
    client = await _logged_in_client(panel, response_timeout=0.1, keepalive_retries=1)
    panel.drop_next_command_responses = 5
    with pytest.raises(TimeoutError):
        await client.keepalive()
    await client.close()


@pytest.mark.asyncio
async def test_interleaved_message_then_response(panel: FakePanel) -> None:
    client = await _logged_in_client(panel)
    panel.interleave_message_before_response = b"\x01\x02\x01"
    payload = await client.keepalive()
    assert payload[0] == 0x18
    queued = await client.recv_message(timeout=0.2)
    assert queued.body == b"\x01\x02\x01"
    await client.close()


@pytest.mark.asyncio
async def test_get_zone_state_rejects_invalid_count(panel: FakePanel) -> None:
    client = await _logged_in_client(panel)
    with pytest.raises(ProtocolError, match="count"):
        await client.get_zone_state(1, 0)
    with pytest.raises(ProtocolError, match="count"):
        await client.get_zone_state(1, 169)
    with pytest.raises(ProtocolError, match="start"):
        await client.get_zone_state(0, 1)
    await client.close()


@pytest.mark.asyncio
async def test_get_zone_state_accepts_status_byte_equal_to_nak() -> None:
    """count=1 status 0x15 is a valid bitmap, not a GetZoneState NAK."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="A", status=0x15)],
        zone_count=1,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        statuses = await client.get_zone_state(1, 1)
        assert statuses == bytes([0x15])
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_get_zone_state_nak_when_length_mismatches() -> None:
    """True NAK is a single 0x15 when the panel rejects the request (len != count)."""
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="A", status=0x00),
            FakeZone(number=2, zone_type=1, name="B", status=0x00),
        ],
        zone_count=2,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        panel.zone_state_override = bytes([0x15])  # NAK-shaped, wrong length for count=2
        with pytest.raises(ProtocolError, match="GetZoneState NAK|rejected reading zone"):
            await client.get_zone_state(1, 2)
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_get_zone_state_returns_status_bytes() -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="A", status=0x00),
            FakeZone(number=2, zone_type=1, name="B", status=0x01),
            FakeZone(number=3, zone_type=0, name="", status=0x02),
        ],
        zone_count=3,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        statuses = await client.get_zone_state(1, 3)
        assert statuses == bytes([0x00, 0x01, 0x02])
        assert panel.last_command == 2  # CMD_GET_ZONE_STATE
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_get_zone_state_length_mismatch_raises() -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="A", status=0x00)],
        zone_count=1,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        panel.zone_state_override = b"\x00\x00"  # wrong length for count=1
        with pytest.raises(ProtocolError, match="GetZoneState|zone-state"):
            await client.get_zone_state(1, 1)
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_set_event_messages_sends_expected_bitmask() -> None:
    panel = FakePanel(udl_password="1234")
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        await client.set_event_messages()
        assert panel.last_command == CMD_SETEVENTMESSAGES
        assert panel.last_seteventmessages_body == bytes([0x3F, 0x00])
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_recv_message_receives_injected_zone_push() -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=1,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        await panel.inject_zone_message(zone_number=1, status=0x01)
        msg = await client.recv_message(timeout=1.0)
        assert msg.body[0] == MSG_ZONE
        assert msg.body[1] == 1
        assert msg.body[2] == 0x01
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_get_area_flags_returns_count_times_area_size_bytes() -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR")],
        zone_count=12,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        flags = await client.get_area_flags(0, 72)
        assert len(flags) == 72
        assert panel.last_command == CMD_GET_AREA_FLAGS
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_get_area_flags_rejects_bad_count(panel: FakePanel) -> None:
    client = await _logged_in_client(panel)
    with pytest.raises(ProtocolError, match="count"):
        await client.get_area_flags(0, 0)
    await client.close()


@pytest.mark.asyncio
async def test_recv_message_receives_injected_area_push() -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR")],
        zone_count=12,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        await panel.inject_area_message(area_number=1, state=3)
        msg = await client.recv_message(timeout=1.0)
        assert msg.body[0] == MSG_AREA
        assert msg.body[1] == 1
        assert msg.body[2] == 3
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_set_event_messages_ack_is_success() -> None:
    panel = FakePanel(udl_password="1234")
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        # Handler returns ACK; method should not raise.
        await client.set_event_messages()
        assert panel.seteventmessages_calls == 1
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_stale_sequence_then_matching_response(panel: FakePanel) -> None:
    client = await _logged_in_client(panel)
    panel.stale_sequence_before_response = True
    payload = await client.keepalive()
    assert payload is not None
    await client.close()


@pytest.mark.asyncio
async def test_unexpected_command_frame_then_response(panel: FakePanel) -> None:
    client = await _logged_in_client(panel)
    panel.command_frame_before_response = True
    payload = await client.keepalive()
    assert payload is not None
    await client.close()


@pytest.mark.asyncio
async def test_wrong_response_cmd_raises(panel: FakePanel) -> None:
    client = await _logged_in_client(panel)
    panel.wrong_cmd_before_response = True
    with pytest.raises(ProtocolError, match="response cmd|did not match"):
        await client.keepalive()
    await client.close()


@pytest.mark.asyncio
async def test_close_waits_for_in_flight_io_lock(panel: FakePanel) -> None:
    """Reconnect teardown must not null streams under an in-flight send_command."""
    client = await _logged_in_client(panel)
    await client._io_lock.acquire()
    close_done = asyncio.Event()

    async def do_close() -> None:
        await client.close()
        close_done.set()

    task = asyncio.create_task(do_close())
    await asyncio.sleep(0.05)
    assert not close_done.is_set()
    assert client._writer is not None
    client._io_lock.release()
    await asyncio.wait_for(task, timeout=1.0)
    assert close_done.is_set()
    assert client._writer is None


@pytest.mark.asyncio
async def test_forced_disconnect_plusplusplus(panel: FakePanel) -> None:
    client = await _logged_in_client(panel)
    panel.plusplusplus_on_next_command = True
    with pytest.raises(ForcedDisconnect, match=r"\+\+\+"):
        await client.keepalive()
    await client.close()


@pytest.mark.asyncio
async def test_forced_disconnect_peer_close(panel: FakePanel) -> None:
    client = await _logged_in_client(panel)
    panel.close_on_next_command = True
    with pytest.raises(ForcedDisconnect, match="closed by peer|closed the network"):
        await client.keepalive()
    await client.close()


@pytest.mark.asyncio
async def test_connection_reset_maps_to_forced_disconnect(panel: FakePanel) -> None:
    """TCP RST / OSError on read must become ForcedDisconnect (keep-trying reconnect)."""
    client = await _logged_in_client(panel)
    assert client._reader is not None

    async def _rst(_n: int = 4096) -> bytes:
        raise ConnectionResetError("Connection reset by peer")

    client._reader.read = _rst  # type: ignore[method-assign]
    with pytest.raises(ForcedDisconnect, match="reset|network|session"):
        await client.recv_message(timeout=0.5)
    await client.close()


@pytest.mark.asyncio
async def test_send_command_after_session_teardown_is_forced_disconnect(
    panel: FakePanel,
) -> None:
    """Mid-session close (had a transport) → ForcedDisconnect, not a generic ProtocolError."""
    client = await _logged_in_client(panel)
    await client.close()
    with pytest.raises(ForcedDisconnect, match="Not connected|session|network"):
        await client.send_command(CMD_GETDATETIME)


@pytest.mark.asyncio
async def test_set_area_arm_sends_cmd_6_with_mode_and_area() -> None:
    panel = FakePanel(udl_password="1234")
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        await client.set_area_arm(0)
        assert panel.last_command == CMD_SET_AREA_ARM
        assert panel.last_arm_body == bytes([0x00, 0x01])
        assert panel.last_arm_mode == 0
        await client.set_area_arm(2)
        assert panel.last_arm_body == bytes([0x02, 0x01])
        assert panel.last_arm_mode == 2
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_set_area_disarm_sends_cmd_8_with_01() -> None:
    panel = FakePanel(udl_password="1234")
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        await client.set_area_disarm()
        assert panel.last_command == CMD_SET_AREA_DISARM
        assert panel.last_disarm_body == bytes([0x01])
        assert panel.disarm_calls == 1
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_send_command_requires_authenticated_except_login(panel: FakePanel) -> None:
    """Connected but not logged in must refuse non-LOGIN commands."""
    client = PanelClient(
        panel.host,
        panel.port,
        udl_password="1234",
        login_delay=0.0,
        response_timeout=0.5,
    )
    await client.connect()
    assert client.authenticated is False
    with pytest.raises(ProtocolError, match="not authenticated|login"):
        await client.keepalive()
    await client.login()
    assert client.authenticated is True
    await client.keepalive()
    await client.close()


@pytest.mark.asyncio
async def test_plusplusplus_message_does_not_claim_trigger_is_common(panel: FakePanel) -> None:
    """ADR-014: ForcedDisconnect copy must not present trigger drops as the normal path."""
    client = await _logged_in_client(panel)
    panel.plusplusplus_on_next_command = True
    with pytest.raises(ForcedDisconnect) as excinfo:
        await client.keepalive()
    msg = str(excinfo.value).lower()
    assert "often happens around arm/disarm or a real alarm trigger" not in msg
    assert "reconnect" in msg
    await client.close()
