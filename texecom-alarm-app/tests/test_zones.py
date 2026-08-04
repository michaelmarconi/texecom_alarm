"""Zone enumeration: skip unused slots (zoneType=0), keep in-use zones."""

from __future__ import annotations

import pytest
from tests.fake_panel import FakePanel, FakeZone

from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.zones import Zone, enumerate_zones


@pytest.fixture
async def panel() -> FakePanel:
    fp = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="FRONT DOOR"),
            FakeZone(number=2, zone_type=0, name=""),
            FakeZone(number=3, zone_type=3, name="KITCHEN PIR"),
            FakeZone(number=4, zone_type=0, name=""),
        ],
        zone_count=4,
    )
    await fp.start()
    yield fp
    await fp.stop()


@pytest.mark.asyncio
async def test_enumerate_zones_skips_unused_slots(panel: FakePanel) -> None:
    client = PanelClient(
        panel.host,
        panel.port,
        udl_password="1234",
        login_delay=0.0,
        response_timeout=0.5,
    )
    await client.connect()
    await client.login()

    zones = await enumerate_zones(client)

    assert zones == [
        Zone(number=1, zone_type=1, name="FRONT DOOR"),
        Zone(number=3, zone_type=3, name="KITCHEN PIR"),
    ]
    assert all(z.zone_type != 0 for z in zones)
    await client.close()


@pytest.mark.asyncio
async def test_enumerate_zones_queries_panel_reported_count(panel: FakePanel) -> None:
    client = PanelClient(
        panel.host,
        panel.port,
        udl_password="1234",
        login_delay=0.0,
        response_timeout=0.5,
    )
    await client.connect()
    await client.login()
    await enumerate_zones(client)

    assert panel.zone_detail_queries == [1, 2, 3, 4]
    await client.close()
