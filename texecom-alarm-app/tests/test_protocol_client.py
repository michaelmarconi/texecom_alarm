"""Async client tests against FakePanel — login, resync, keepalive retry."""

from __future__ import annotations

import pytest
from tests.fake_panel import FakePanel

from texecom_alarm.protocol.client import ForcedDisconnect, PanelClient, ProtocolError
from texecom_alarm.protocol.frame import CMD_GETDATETIME


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
    with pytest.raises(ProtocolError, match="LOGIN failed"):
        await client.login()
    await client.close()


@pytest.mark.asyncio
async def test_send_command_requires_connection() -> None:
    client = PanelClient("127.0.0.1", 1, udl_password="1234")
    with pytest.raises(ProtocolError, match="not connected"):
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
    await client.close()


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
    with pytest.raises(ProtocolError, match="response cmd"):
        await client.keepalive()
    await client.close()


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
    with pytest.raises(ForcedDisconnect, match="closed by peer"):
        await client.keepalive()
    await client.close()
