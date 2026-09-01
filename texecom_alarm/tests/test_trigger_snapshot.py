"""Unit tests for last-trigger activity buffer and MQTT attributes (ADR-004)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import pytest
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.logging_setup import configure_logging
from texecom_alarm.trigger_snapshot import (
    TriggerActivityBuffer,
    alarm_attributes_topic,
    maybe_publish_trigger_snapshot,
)
from texecom_alarm.zones import Zone


def test_alarm_attributes_topic() -> None:
    assert alarm_attributes_topic("texecom") == "texecom/alarm/attributes"


def test_initiating_zone_most_recent_active() -> None:
    buf = TriggerActivityBuffer()
    buf.record_zone(1, 0x00)  # Secure
    buf.record_zone(3, 0x01)  # Active
    buf.record_zone(5, 0x00)  # Secure after
    assert buf.initiating_zone() == 3


def test_initiating_zone_prefers_later_active_over_earlier() -> None:
    buf = TriggerActivityBuffer()
    buf.record_zone(2, 0x01)
    buf.record_zone(7, 0x02)  # Tamper also non-Secure
    assert buf.initiating_zone() == 7


def test_initiating_zone_none_when_buffer_empty_or_only_secure() -> None:
    buf = TriggerActivityBuffer()
    assert buf.initiating_zone() is None
    buf.record_zone(1, 0x00)
    assert buf.initiating_zone() is None


def test_record_log_does_not_affect_initiating_zone() -> None:
    buf = TriggerActivityBuffer()
    buf.record_log(event_type=1, group=2)
    assert buf.initiating_zone() is None
    buf.record_zone(4, 0x01)
    buf.record_log(event_type=9, group=1)
    assert buf.initiating_zone() == 4


@pytest.mark.asyncio
async def test_maybe_publish_on_edge_into_triggered() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    buf = TriggerActivityBuffer()
    buf.record_zone(12, 0x01)
    fixed = datetime(2026, 8, 4, 17, 0, 0, tzinfo=UTC)

    await maybe_publish_trigger_snapshot(
        mqtt,
        previous_payload="armed_away",
        new_payload="triggered",
        topic_prefix="texecom",
        buffer=buf,
        clock=lambda: fixed,
    )

    msgs = [m for m in mqtt.messages if m.topic == "texecom/alarm/attributes"]
    assert len(msgs) == 1
    assert msgs[0].retain is True
    payload = json.loads(msgs[0].payload)
    assert payload["last_trigger_zone"] == 12
    assert payload["last_trigger_time"] == "2026-08-04T17:00:00+00:00"


@pytest.mark.asyncio
async def test_maybe_publish_null_zone_when_buffer_empty() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    buf = TriggerActivityBuffer()
    fixed = datetime(2026, 8, 4, 18, 0, 0, tzinfo=UTC)

    await maybe_publish_trigger_snapshot(
        mqtt,
        previous_payload="disarmed",
        new_payload="triggered",
        topic_prefix="texecom",
        buffer=buf,
        clock=lambda: fixed,
    )

    payload = json.loads(mqtt.payloads_for("texecom/alarm/attributes")[-1])
    assert payload["last_trigger_zone"] is None
    assert payload["last_trigger_time"] == "2026-08-04T18:00:00+00:00"


@pytest.mark.asyncio
async def test_no_publish_when_already_triggered() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    buf = TriggerActivityBuffer()
    buf.record_zone(1, 0x01)

    await maybe_publish_trigger_snapshot(
        mqtt,
        previous_payload="triggered",
        new_payload="triggered",
        topic_prefix="texecom",
        buffer=buf,
    )
    assert mqtt.payloads_for("texecom/alarm/attributes") == []


@pytest.mark.asyncio
async def test_no_publish_when_not_entering_triggered() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    buf = TriggerActivityBuffer()
    buf.record_zone(1, 0x01)

    await maybe_publish_trigger_snapshot(
        mqtt,
        previous_payload="armed_away",
        new_payload="disarmed",
        topic_prefix="texecom",
        buffer=buf,
    )
    assert mqtt.payloads_for("texecom/alarm/attributes") == []


@pytest.mark.asyncio
async def test_attributes_retained_across_later_disarm_state_publish() -> None:
    """Disarm updates alarm state topic but must not clear retained attributes."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    buf = TriggerActivityBuffer()
    buf.record_zone(3, 0x01)
    fixed = datetime(2026, 8, 4, 19, 0, 0, tzinfo=UTC)

    await maybe_publish_trigger_snapshot(
        mqtt,
        previous_payload="armed_away",
        new_payload="triggered",
        topic_prefix="texecom",
        buffer=buf,
        clock=lambda: fixed,
    )
    attrs_before = mqtt.payloads_for("texecom/alarm/attributes")
    assert len(attrs_before) == 1

    # Simulate disarm state publish only (area_state path) — no attributes clear.
    await mqtt.publish("texecom/alarm/state", "disarmed", retain=True)

    assert mqtt.payloads_for("texecom/alarm/attributes") == attrs_before
    payload = json.loads(attrs_before[0])
    assert payload["last_trigger_zone"] == 3


@pytest.mark.asyncio
async def test_trigger_snapshot_debug_includes_zone_name() -> None:
    root = logging.getLogger()
    before_level = root.level
    before_handlers = list(root.handlers)

    class _Capture(logging.Handler):
        def __init__(self) -> None:
            super().__init__(level=logging.NOTSET)
            self.records: list[logging.LogRecord] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.records.append(record)

    capture = _Capture()
    try:
        configure_logging("DEBUG")
        root.addHandler(capture)
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        buf = TriggerActivityBuffer()
        buf.record_zone(1, 0x01)
        fixed = datetime(2026, 8, 4, 17, 0, 0, tzinfo=UTC)
        await maybe_publish_trigger_snapshot(
            mqtt,
            previous_payload="armed_away",
            new_payload="triggered",
            topic_prefix="texecom",
            buffer=buf,
            clock=lambda: fixed,
            zones={1: Zone(number=1, zone_type=1, name="FRONT DOOR")},
        )
        msgs = [
            r.getMessage()
            for r in capture.records
            if r.name.startswith("texecom_alarm.trigger_snapshot")
        ]
        assert any("mqtt_trigger_snapshot" in m for m in msgs), msgs
        assert any("FRONT DOOR" in m and "1" in m for m in msgs), msgs
    finally:
        root.removeHandler(capture)
        root.handlers.clear()
        for handler in before_handlers:
            root.addHandler(handler)
        root.setLevel(before_level)
