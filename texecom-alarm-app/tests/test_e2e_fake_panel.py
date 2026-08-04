"""E2E-shaped tests against a mocked panel — never the live household panel."""

from __future__ import annotations

import pytest
from tests.fake_panel import FakePanel

from texecom_alarm import healthcheck
from texecom_alarm.protocol.client import PanelClient


def test_fake_panel_session_lifecycle() -> None:
    panel = FakePanel()
    assert not panel.authenticated
    panel.connect()
    assert not panel.authenticated
    assert healthcheck().startswith("texecom-alarm/")
    panel.close()
    assert not panel.authenticated


@pytest.mark.asyncio
async def test_e2e_login_against_fake_panel() -> None:
    panel = FakePanel(udl_password="1234")
    await panel.start()
    try:
        client = PanelClient(
            panel.host,
            panel.port,
            udl_password="1234",
            login_delay=0.0,
            response_timeout=0.5,
        )
        await client.connect()
        await client.login()
        assert client.authenticated
        assert panel.authenticated
        await client.close()
    finally:
        await panel.stop()
