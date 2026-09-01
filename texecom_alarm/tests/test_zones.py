"""Zone enumeration: skip unused slots (zoneType=0), keep in-use zones."""

from __future__ import annotations

import logging

import pytest
from tests.fake_panel import FakePanel, FakeZone

from texecom_alarm.logging_setup import TRACE_LEVEL, configure_logging
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

    zones, zone_count = await enumerate_zones(client)

    assert zone_count == 4
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


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _zone_msgs(records: list[logging.LogRecord]) -> list[str]:
    return [r.getMessage() for r in records if r.name.startswith("texecom_alarm.zones")]


@pytest.mark.asyncio
async def test_enumerate_zones_debug_logging_avoids_logrecord_name_collision(
    panel: FakePanel,
) -> None:
    """DEBUG/TRACE must not pass reserved LogRecord keys via logger extra=."""
    root = logging.getLogger()
    before_level = root.level
    before_handlers = list(root.handlers)
    try:
        configure_logging("DEBUG")
        client = PanelClient(
            panel.host,
            panel.port,
            udl_password="1234",
            login_delay=0.0,
            response_timeout=0.5,
        )
        await client.connect()
        await client.login()
        zones, _ = await enumerate_zones(client)
        assert len(zones) == 2
        await client.close()

        configure_logging("TRACE")
        assert logging.getLogger().isEnabledFor(TRACE_LEVEL)
    finally:
        root.handlers.clear()
        for handler in before_handlers:
            root.addHandler(handler)
        root.setLevel(before_level)


@pytest.mark.asyncio
async def test_enumerate_info_includes_panel_ident_and_counts(panel: FakePanel) -> None:
    """INFO enumerated_zones puts identification + counts in getMessage()."""
    root = logging.getLogger()
    before_level = root.level
    before_handlers = list(root.handlers)
    capture = _Capture()
    try:
        configure_logging("INFO")
        root.addHandler(capture)
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
        await client.close()

        infos = [
            r.getMessage()
            for r in capture.records
            if r.name.startswith("texecom_alarm.zones") and r.levelno == logging.INFO
        ]
        assert infos, f"expected INFO from enumerate_zones, got {_zone_msgs(capture.records)!r}"
        msg = infos[-1]
        assert "enumerated_zones" in msg
        assert "Elite" in msg
        assert "V6.02.02LS1" in msg
        assert "2" in msg  # in-use
        assert "4" in msg  # slots
    finally:
        root.removeHandler(capture)
        root.handlers.clear()
        for handler in before_handlers:
            root.addHandler(handler)
        root.setLevel(before_level)


@pytest.mark.asyncio
async def test_enumerate_debug_zone_in_use_includes_name_and_type(panel: FakePanel) -> None:
    """DEBUG zone_in_use includes panel name and type label in getMessage()."""
    root = logging.getLogger()
    before_level = root.level
    before_handlers = list(root.handlers)
    capture = _Capture()
    try:
        configure_logging("DEBUG")
        root.addHandler(capture)
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
        await client.close()

        msgs = _zone_msgs(capture.records)
        in_use = [m for m in msgs if "zone_in_use" in m]
        assert any("FRONT DOOR" in m and "Entry/Exit 1" in m for m in in_use), msgs
        assert any("KITCHEN PIR" in m and "Interior" in m for m in in_use), msgs
        # Unused skips must not appear at DEBUG.
        assert not any("zone_unused_skipped" in m for m in msgs), msgs
    finally:
        root.removeHandler(capture)
        root.handlers.clear()
        for handler in before_handlers:
            root.addHandler(handler)
        root.setLevel(before_level)


@pytest.mark.asyncio
async def test_enumerate_trace_logs_unused_skips(panel: FakePanel) -> None:
    """TRACE shows zone_unused_skipped with the zone number."""
    root = logging.getLogger()
    before_level = root.level
    before_handlers = list(root.handlers)
    capture = _Capture()
    try:
        configure_logging("TRACE")
        root.addHandler(capture)
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
        await client.close()

        msgs = _zone_msgs(capture.records)
        skips = [m for m in msgs if "zone_unused_skipped" in m]
        assert any("2" in m for m in skips), msgs
        assert any("4" in m for m in skips), msgs
    finally:
        root.removeHandler(capture)
        root.handlers.clear()
        for handler in before_handlers:
            root.addHandler(handler)
        root.setLevel(before_level)
