"""Unit tests for HA MQTT discovery payloads via recording stub (no broker)."""

from __future__ import annotations

import json

import pytest
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.config import Settings
from texecom_alarm.mqtt.discovery import (
    ALARM_OBJECT_ID,
    AVAILABILITY_OFFLINE,
    AVAILABILITY_ONLINE,
    CONNECTIVITY_OBJECT_ID,
    alarm_attributes_topic,
    alarm_discovery_payload,
    alarm_discovery_topic,
    availability_topic,
    connectivity_discovery_payload,
    connectivity_discovery_topic,
    connectivity_state_topic,
    publish_alarm_discovery,
    publish_connectivity_discovery,
    publish_zone_discovery,
    zone_discovery_payload,
    zone_discovery_topic,
    zone_object_id,
)
from texecom_alarm.zones import Zone

EXPECTED_DEVICE = {
    "identifiers": ["texecom_alarm"],
    "name": "Texecom Alarm",
    "manufacturer": "Texecom",
    "model": "Premier Elite",
}


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "panel_host": "192.0.2.1",
        "panel_port": 10001,
        "udl_password": "1234",
        "mqtt_host": "127.0.0.1",
        "mqtt_port": 1883,
        "mqtt_username": "",
        "mqtt_password": "",
        "mqtt_topic_prefix": "texecom",
        "part_arm_1": "night",
        "part_arm_2": "home",
        "part_arm_3": "unused",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_alarm_object_id_is_texecom_alarm_arm_status() -> None:
    assert ALARM_OBJECT_ID == "texecom_alarm_arm_status"


def test_alarm_discovery_topic() -> None:
    assert (
        alarm_discovery_topic(ALARM_OBJECT_ID)
        == "homeassistant/alarm_control_panel/texecom_alarm_arm_status/config"
    )


def test_alarm_attributes_topic() -> None:
    assert alarm_attributes_topic("texecom") == "texecom/alarm/attributes"


def test_alarm_discovery_payload_shape() -> None:
    payload = alarm_discovery_payload(topic_prefix="texecom")
    assert payload["unique_id"] == "texecom_alarm_arm_status"
    assert payload["object_id"] == "texecom_alarm_arm_status"
    assert payload["default_entity_id"] == "alarm_control_panel.texecom_alarm_arm_status"
    assert payload["name"] == "Texecom Alarm"
    assert payload["device"] == EXPECTED_DEVICE
    assert payload["state_topic"] == "texecom/alarm/state"
    assert payload["command_topic"] == "texecom/alarm/command"
    assert payload["json_attributes_topic"] == "texecom/alarm/attributes"
    assert payload["availability_topic"] == "texecom/status"
    assert payload["payload_available"] == AVAILABILITY_ONLINE
    assert payload["payload_not_available"] == AVAILABILITY_OFFLINE
    assert payload["code_arm_required"] is False
    assert payload["code_disarm_required"] is False
    assert payload["supported_features"] == ["arm_home", "arm_night", "arm_away"]


def test_alarm_supported_features_order_home_night_away() -> None:
    """AC-3: feature list order is Home → Night → Away regardless of Part-Arm slots."""
    settings = _settings(part_arm_1="night", part_arm_2="home", part_arm_3="unused")
    payload = alarm_discovery_payload(topic_prefix="texecom", settings=settings)
    assert payload["supported_features"] == ["arm_home", "arm_night", "arm_away"]

    remapped = _settings(part_arm_1="home", part_arm_2="away", part_arm_3="night")
    remapped_payload = alarm_discovery_payload(topic_prefix="texecom", settings=remapped)
    assert remapped_payload["supported_features"] == ["arm_home", "arm_night", "arm_away"]


def test_connectivity_object_id_is_panel_link() -> None:
    assert CONNECTIVITY_OBJECT_ID == "texecom_alarm_panel_link"


def test_connectivity_discovery_topic() -> None:
    assert (
        connectivity_discovery_topic()
        == "homeassistant/binary_sensor/texecom_alarm_panel_link/config"
    )


def test_connectivity_state_topic() -> None:
    assert connectivity_state_topic("texecom") == "texecom/panel_link/state"


def test_connectivity_discovery_payload_shape() -> None:
    payload = connectivity_discovery_payload(topic_prefix="texecom")
    assert payload["unique_id"] == CONNECTIVITY_OBJECT_ID
    assert payload["object_id"] == CONNECTIVITY_OBJECT_ID
    assert payload["default_entity_id"] == "binary_sensor.texecom_alarm_panel_link"
    assert payload["device"] == EXPECTED_DEVICE
    assert payload["state_topic"] == "texecom/panel_link/state"
    assert payload["device_class"] == "connectivity"
    assert payload["payload_on"] == "ON"
    assert payload["payload_off"] == "OFF"
    assert payload["availability_topic"] == "texecom/status"
    assert payload["payload_available"] == AVAILABILITY_ONLINE
    assert payload["payload_not_available"] == AVAILABILITY_OFFLINE


def test_zone_alarm_and_connectivity_share_one_device_block() -> None:
    """AC-2: all discovery payloads share one MQTT device block."""
    zone = Zone(number=1, zone_type=1, name="FRONT DOOR")
    zone_payload = zone_discovery_payload(zone, topic_prefix="texecom")
    alarm_payload = alarm_discovery_payload(topic_prefix="texecom")
    link_payload = connectivity_discovery_payload(topic_prefix="texecom")
    assert zone_payload["device"] == EXPECTED_DEVICE
    assert alarm_payload["device"] == EXPECTED_DEVICE
    assert link_payload["device"] == EXPECTED_DEVICE
    assert zone_payload["device"] is alarm_payload["device"] is link_payload["device"]


def test_zone_and_alarm_discovery_use_app_lwt_only() -> None:
    """AC-3: zone/alarm availability is app LWT — not panel-link state."""
    zone = Zone(number=1, zone_type=1, name="FRONT DOOR")
    zone_payload = zone_discovery_payload(zone, topic_prefix="texecom")
    alarm_payload = alarm_discovery_payload(topic_prefix="texecom")
    assert zone_payload["availability_topic"] == "texecom/status"
    assert alarm_payload["availability_topic"] == "texecom/status"
    assert zone_payload["availability_topic"] != connectivity_state_topic("texecom")
    assert alarm_payload["availability_topic"] != connectivity_state_topic("texecom")


@pytest.mark.asyncio
async def test_publish_connectivity_discovery_retained() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect(
        will_topic=availability_topic("texecom"),
        will_payload=AVAILABILITY_OFFLINE,
        will_retain=True,
    )
    await publish_connectivity_discovery(mqtt, topic_prefix="texecom")
    topic = "homeassistant/binary_sensor/texecom_alarm_panel_link/config"
    msgs = [m for m in mqtt.messages if m.topic == topic]
    assert len(msgs) == 1
    assert msgs[0].retain is True
    payload = json.loads(
        msgs[0].payload if isinstance(msgs[0].payload, str) else msgs[0].payload.decode()
    )
    assert payload["unique_id"] == CONNECTIVITY_OBJECT_ID
    assert payload["device_class"] == "connectivity"
    assert payload["availability_topic"] == "texecom/status"


@pytest.mark.asyncio
async def test_publish_alarm_discovery_retained() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect(
        will_topic=availability_topic("texecom"),
        will_payload=AVAILABILITY_OFFLINE,
        will_retain=True,
    )
    await publish_alarm_discovery(mqtt, topic_prefix="texecom")
    topic = "homeassistant/alarm_control_panel/texecom_alarm_arm_status/config"
    msgs = [m for m in mqtt.messages if m.topic == topic]
    assert len(msgs) == 1
    assert msgs[0].retain is True
    payload = json.loads(
        msgs[0].payload if isinstance(msgs[0].payload, str) else msgs[0].payload.decode()
    )
    assert payload["unique_id"] == ALARM_OBJECT_ID
    assert payload["availability_topic"] == "texecom/status"


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
    assert payload["name"] == "Front Door"
    assert payload["unique_id"] == "texecom_alarm_front_door_1"
    assert payload["object_id"] == "texecom_alarm_front_door_1"
    assert payload["default_entity_id"] == "binary_sensor.texecom_alarm_front_door_1"
    assert payload["device"] == EXPECTED_DEVICE
    assert payload["state_topic"] == "texecom/zone/1/state"
    assert payload["availability_topic"] == "texecom/status"
    assert payload["payload_available"] == AVAILABILITY_ONLINE
    assert payload["payload_not_available"] == AVAILABILITY_OFFLINE

    assert mqtt.will_topic == "texecom/status"
    assert mqtt.will_payload == AVAILABILITY_OFFLINE
    assert mqtt.will_retain is True

    status = mqtt.payloads_for("texecom/status")
    assert status[-1] == AVAILABILITY_ONLINE


def test_zone_discovery_name_is_title_case() -> None:
    """AC-2: zone friendly names are Title Case derived from panel names."""
    zone = Zone(number=1, zone_type=1, name="FRONT DOOR")
    payload = zone_discovery_payload(zone, topic_prefix="texecom")
    assert payload["name"] == "Front Door"
    assert payload["object_id"] == "texecom_alarm_front_door_1"
    assert payload["unique_id"] == "texecom_alarm_front_door_1"
    assert payload["default_entity_id"] == "binary_sensor.texecom_alarm_front_door_1"

    empty = Zone(number=9, zone_type=1, name="")
    assert zone_discovery_payload(empty, topic_prefix="texecom")["name"] == "Zone 9"
