"""Unit tests for HA MQTT discovery payloads via recording stub (no broker)."""

from __future__ import annotations

import json

import pytest
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.mqtt.discovery import (
    AVAILABILITY_OFFLINE,
    AVAILABILITY_ONLINE,
    availability_topic,
    publish_zone_discovery,
    zone_discovery_topic,
    zone_object_id,
)
from texecom_alarm.zones import Zone


def test_zone_object_id_matches_provisional_texecom_alarm_naming() -> None:
    zone = Zone(number=1, zone_type=1, name="FRONT DOOR")
    assert zone_object_id(zone) == "texecom_alarm_front_door_1"


def test_zone_object_id_unique_when_names_collide() -> None:
    a = Zone(number=1, zone_type=1, name="PIR")
    b = Zone(number=5, zone_type=1, name="PIR")
    assert zone_object_id(a) == "texecom_alarm_pir_1"
    assert zone_object_id(b) == "texecom_alarm_pir_5"
    assert zone_object_id(a) != zone_object_id(b)


def test_zone_discovery_topic() -> None:
    assert (
        zone_discovery_topic("texecom_alarm_front_door_1")
        == "homeassistant/binary_sensor/texecom_alarm_front_door_1/config"
    )


@pytest.mark.asyncio
async def test_publish_zone_discovery_skips_nothing_for_in_use_only() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect(
        will_topic=availability_topic("texecom"),
        will_payload=AVAILABILITY_OFFLINE,
        will_retain=True,
    )

    zones = [
        Zone(number=1, zone_type=1, name="FRONT DOOR"),
        Zone(number=3, zone_type=3, name="KITCHEN PIR"),
    ]
    await publish_zone_discovery(mqtt, zones, topic_prefix="texecom")

    topics = [m.topic for m in mqtt.messages]
    assert availability_topic("texecom") in topics
    assert "homeassistant/binary_sensor/texecom_alarm_front_door_1/config" in topics
    assert "homeassistant/binary_sensor/texecom_alarm_kitchen_pir_3/config" in topics
    # No discovery for an unused slot that was never passed in.
    assert not any("unused" in t for t in topics)
    assert len([t for t in topics if t.startswith("homeassistant/")]) == 2

    front = next(
        m
        for m in mqtt.messages
        if m.topic == "homeassistant/binary_sensor/texecom_alarm_front_door_1/config"
    )
    assert front.retain is True
    payload = json.loads(
        front.payload if isinstance(front.payload, str) else front.payload.decode()
    )
    assert payload["name"] == "FRONT DOOR"
    assert payload["unique_id"] == "texecom_alarm_front_door_1"
    assert payload["object_id"] == "texecom_alarm_front_door_1"
    assert payload["state_topic"] == "texecom/zone/1/state"
    assert payload["availability_topic"] == "texecom/status"
    assert payload["payload_available"] == AVAILABILITY_ONLINE
    assert payload["payload_not_available"] == AVAILABILITY_OFFLINE

    assert mqtt.will_topic == "texecom/status"
    assert mqtt.will_payload == AVAILABILITY_OFFLINE
    assert mqtt.will_retain is True

    status = mqtt.payloads_for("texecom/status")
    assert status[-1] == AVAILABILITY_ONLINE
