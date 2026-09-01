"""Zone status bitmap decode and MQTT snapshot/push publish helpers."""

from __future__ import annotations

import logging

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.logging_setup import configure_logging
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.zone_state import (
    handle_zone_message,
    mqtt_payload_for_status,
    publish_zone_state,
    publish_zone_state_snapshot,
)
from texecom_alarm.zones import Zone, enumerate_zones

CMD_GET_ZONE_STATE = 2


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (0x00, "0"),  # Secure
        (0x01, "1"),  # Active
        (0x02, "1"),  # Tamper
        (0x03, "1"),  # Short
        (0x11, "1"),  # Active + alarmed bit
        (0x10, "0"),  # Secure + alarmed bit (low 2 bits still Secure)
    ],
)
def test_mqtt_payload_for_status_uses_low_two_bits(status: int, expected: str) -> None:
    assert mqtt_payload_for_status(status) == expected


@pytest.mark.asyncio
async def test_publish_zone_state_writes_retained_payload() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await publish_zone_state(mqtt, zone_number=3, status=0x01, topic_prefix="texecom")
    assert mqtt.payloads_for("texecom/zone/3/state") == ["1"]
    assert mqtt.messages[-1].retain is True


@pytest.mark.asyncio
async def test_snapshot_publishes_in_use_zones_only_matching_status_bytes() -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00),
            FakeZone(number=2, zone_type=0, name="", status=0x01),
            FakeZone(number=3, zone_type=3, name="KITCHEN PIR", status=0x01),
        ],
        zone_count=3,
    )
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
        zones, zone_count = await enumerate_zones(client)
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()

        await publish_zone_state_snapshot(
            client,
            mqtt,
            zones,
            topic_prefix="texecom",
            zone_count=zone_count,
        )

        assert mqtt.payloads_for("texecom/zone/1/state") == ["0"]
        assert mqtt.payloads_for("texecom/zone/3/state") == ["1"]
        assert mqtt.payloads_for("texecom/zone/2/state") == []
        assert CMD_GET_ZONE_STATE in panel.commands_seen
        forbidden = {4, 5, 6, 8, 9}
        assert forbidden.isdisjoint(panel.commands_seen)
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_snapshot_sends_only_get_zone_state_for_zone_status() -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=1,
    )
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
        zones = [Zone(number=1, zone_type=1, name="DOOR")]
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()

        before = list(panel.commands_seen)
        await publish_zone_state_snapshot(
            client,
            mqtt,
            zones,
            topic_prefix="texecom",
            zone_count=1,
        )
        snapshot_cmds = panel.commands_seen[len(before) :]

        assert snapshot_cmds == [CMD_GET_ZONE_STATE]
        assert 1 not in snapshot_cmds  # LOGIN
        assert 22 not in snapshot_cmds  # GETPANELIDENTIFICATION
        assert 3 not in snapshot_cmds  # GETZONEDETAILS
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_handle_zone_message_ignores_short_and_unused() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await handle_zone_message(mqtt, b"\x01\x01", topic_prefix="texecom", in_use_zones={1})
    await handle_zone_message(mqtt, b"\x01\x02\x01", topic_prefix="texecom", in_use_zones={1})
    assert mqtt.payloads_for("texecom/zone/1/state") == []
    assert mqtt.payloads_for("texecom/zone/2/state") == []


@pytest.mark.asyncio
async def test_fetch_zone_states_empty_count() -> None:
    from texecom_alarm.zone_state import fetch_zone_states

    class _Stub:
        async def get_zone_state(self, start: int, count: int) -> bytes:
            raise AssertionError("should not be called")

    assert await fetch_zone_states(_Stub(), 0) == b""  # type: ignore[arg-type]


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _zone_state_msgs(records: list[logging.LogRecord]) -> list[str]:
    return [r.getMessage() for r in records if r.name.startswith("texecom_alarm.zone_state")]


@pytest.mark.asyncio
async def test_handle_zone_message_debug_includes_name_and_status() -> None:
    """DEBUG mqtt_zone_state includes zone name, status label, hex, MQTT open/1."""
    root = logging.getLogger()
    before_level = root.level
    before_handlers = list(root.handlers)
    capture = _Capture()
    try:
        configure_logging("DEBUG")
        root.addHandler(capture)
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        zones = {1: Zone(number=1, zone_type=1, name="DOOR")}
        await handle_zone_message(
            mqtt,
            bytes([0x01, 1, 0x01]),
            topic_prefix="texecom",
            in_use_zones={1},
            zones=zones,
        )
        msgs = _zone_state_msgs(capture.records)
        assert any("mqtt_zone_state" in m for m in msgs), msgs
        joined = " ".join(msgs)
        assert "DOOR" in joined
        assert "Active" in joined
        assert "0x01" in joined
        assert "open" in joined or "1" in joined
        assert mqtt.payloads_for("texecom/zone/1/state") == ["1"]
    finally:
        root.removeHandler(capture)
        root.handlers.clear()
        for handler in before_handlers:
            root.addHandler(handler)
        root.setLevel(before_level)


@pytest.mark.asyncio
async def test_handle_zone_message_debug_without_zones_lookup_still_logs() -> None:
    """Without a zones mapping, still logs number + status label (no crash)."""
    root = logging.getLogger()
    before_level = root.level
    before_handlers = list(root.handlers)
    capture = _Capture()
    try:
        configure_logging("DEBUG")
        root.addHandler(capture)
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        await handle_zone_message(
            mqtt,
            bytes([0x01, 3, 0x02]),
            topic_prefix="texecom",
            in_use_zones={3},
        )
        msgs = _zone_state_msgs(capture.records)
        joined = " ".join(msgs)
        assert "mqtt_zone_state" in joined
        assert "3" in joined
        assert "Tamper" in joined
    finally:
        root.removeHandler(capture)
        root.handlers.clear()
        for handler in before_handlers:
            root.addHandler(handler)
        root.setLevel(before_level)


@pytest.mark.asyncio
async def test_snapshot_debug_summary_not_per_zone_flood() -> None:
    """Snapshot logs one zone_state_snapshot_done summary; no per-zone mqtt_zone_state."""
    root = logging.getLogger()
    before_level = root.level
    before_handlers = list(root.handlers)
    capture = _Capture()
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00),
            FakeZone(number=2, zone_type=0, name="", status=0x01),
            FakeZone(number=3, zone_type=3, name="KITCHEN PIR", status=0x01),
        ],
        zone_count=3,
    )
    await panel.start()
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
        zones = [
            Zone(number=1, zone_type=1, name="FRONT DOOR"),
            Zone(number=3, zone_type=3, name="KITCHEN PIR"),
        ]
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        capture.records.clear()

        await publish_zone_state_snapshot(
            client,
            mqtt,
            zones,
            topic_prefix="texecom",
            zone_count=3,
        )

        msgs = _zone_state_msgs(capture.records)
        assert not any(m.startswith("mqtt_zone_state") for m in msgs), msgs
        done = [m for m in msgs if "zone_state_snapshot_done" in m]
        assert done, msgs
        assert any("KITCHEN PIR" in m and "Active" in m for m in done), done
        assert mqtt.payloads_for("texecom/zone/3/state") == ["1"]
        await client.close()
    finally:
        root.removeHandler(capture)
        root.handlers.clear()
        for handler in before_handlers:
            root.addHandler(handler)
        root.setLevel(before_level)
        await panel.stop()
