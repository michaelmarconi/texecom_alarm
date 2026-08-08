"""HA MQTT discovery payload builders for zone binary_sensors and alarm panel."""

from __future__ import annotations

import json
import logging
from typing import Protocol

from texecom_alarm.config import Settings
from texecom_alarm.zones import Zone, zone_display_name, zone_slug

logger = logging.getLogger(__name__)

AVAILABILITY_ONLINE = "online"
AVAILABILITY_OFFLINE = "offline"

ALARM_OBJECT_ID = "texecom_alarm_arm_status"
CONNECTIVITY_OBJECT_ID = "texecom_alarm_panel_link"
PANEL_LINK_ON = "ON"
PANEL_LINK_OFF = "OFF"

# Shared across zone, alarm, and panel-link discovery so HA groups one device.
MQTT_DEVICE: dict[str, object] = {
    "identifiers": ["texecom_alarm"],
    "name": "Texecom Alarm",
    "manufacturer": "Texecom",
    "model": "Premier Elite",
}

# HA card order when the MQTT platform respects supported_features list order.
_ARM_FEATURE_ORDER = ("arm_home", "arm_night", "arm_away")


class MqttPublisher(Protocol):
    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        *,
        retain: bool = False,
        qos: int = 0,
    ) -> None: ...


def availability_topic(topic_prefix: str) -> str:
    return f"{topic_prefix}/status"


def zone_object_id(zone: Zone) -> str:
    """object_id / unique_id: texecom_alarm_{slug}_{zone_number} (unique per zone)."""
    return f"texecom_alarm_{zone_slug(zone.name, zone_number=zone.number)}"


def zone_state_topic(topic_prefix: str, zone_number: int) -> str:
    return f"{topic_prefix}/zone/{zone_number}/state"


def zone_discovery_topic(object_id: str) -> str:
    return f"homeassistant/binary_sensor/{object_id}/config"


def alarm_state_topic(topic_prefix: str) -> str:
    return f"{topic_prefix}/alarm/state"


def alarm_command_topic(topic_prefix: str) -> str:
    return f"{topic_prefix}/alarm/command"


def alarm_attributes_topic(topic_prefix: str) -> str:
    return f"{topic_prefix}/alarm/attributes"


def alarm_discovery_topic(object_id: str = ALARM_OBJECT_ID) -> str:
    return f"homeassistant/alarm_control_panel/{object_id}/config"


def connectivity_state_topic(topic_prefix: str) -> str:
    return f"{topic_prefix}/panel_link/state"


def connectivity_discovery_topic(object_id: str = CONNECTIVITY_OBJECT_ID) -> str:
    return f"homeassistant/binary_sensor/{object_id}/config"


def zone_discovery_payload(zone: Zone, *, topic_prefix: str) -> dict[str, object]:
    object_id = zone_object_id(zone)
    return {
        "name": zone_display_name(zone.name, zone_number=zone.number),
        "unique_id": object_id,
        "object_id": object_id,
        # Modern HA ignores topic/object_id for entity_id; name would win otherwise.
        "default_entity_id": f"binary_sensor.{object_id}",
        "device": MQTT_DEVICE,
        "state_topic": zone_state_topic(topic_prefix, zone.number),
        "availability_topic": availability_topic(topic_prefix),
        "payload_available": AVAILABILITY_ONLINE,
        "payload_not_available": AVAILABILITY_OFFLINE,
        "payload_on": "1",
        "payload_off": "0",
    }


def alarm_discovery_payload(
    *,
    topic_prefix: str,
    settings: Settings | None = None,
) -> dict[str, object]:
    if settings is None:
        supported = list(_ARM_FEATURE_ORDER)
    else:
        supported = settings.supported_arm_features()
    return {
        "name": "Texecom Alarm",
        "unique_id": ALARM_OBJECT_ID,
        "object_id": ALARM_OBJECT_ID,
        "default_entity_id": f"alarm_control_panel.{ALARM_OBJECT_ID}",
        "device": MQTT_DEVICE,
        "state_topic": alarm_state_topic(topic_prefix),
        "command_topic": alarm_command_topic(topic_prefix),
        "json_attributes_topic": alarm_attributes_topic(topic_prefix),
        "availability_topic": availability_topic(topic_prefix),
        "payload_available": AVAILABILITY_ONLINE,
        "payload_not_available": AVAILABILITY_OFFLINE,
        "code_arm_required": False,
        "code_disarm_required": False,
        "supported_features": supported,
    }


def connectivity_discovery_payload(*, topic_prefix: str) -> dict[str, object]:
    return {
        "name": "Alarm Panel Connected",
        "unique_id": CONNECTIVITY_OBJECT_ID,
        "object_id": CONNECTIVITY_OBJECT_ID,
        "default_entity_id": f"binary_sensor.{CONNECTIVITY_OBJECT_ID}",
        "device": MQTT_DEVICE,
        "state_topic": connectivity_state_topic(topic_prefix),
        "availability_topic": availability_topic(topic_prefix),
        "payload_available": AVAILABILITY_ONLINE,
        "payload_not_available": AVAILABILITY_OFFLINE,
        "device_class": "connectivity",
        "payload_on": PANEL_LINK_ON,
        "payload_off": PANEL_LINK_OFF,
    }


async def publish_zone_discovery(
    mqtt: MqttPublisher,
    zones: list[Zone],
    *,
    topic_prefix: str,
) -> None:
    """Publish retained discovery configs and mark the app online (ADR-004 LWT peer)."""
    avail = availability_topic(topic_prefix)
    await mqtt.publish(avail, AVAILABILITY_ONLINE, retain=True)
    logger.debug("mqtt_availability_online", extra={"topic": avail})

    for zone in zones:
        object_id = zone_object_id(zone)
        topic = zone_discovery_topic(object_id)
        payload = zone_discovery_payload(zone, topic_prefix=topic_prefix)
        body = json.dumps(payload, separators=(",", ":"))
        await mqtt.publish(topic, body, retain=True)
        logger.debug(
            "mqtt_discovery_published",
            extra={"topic": topic, "zone": zone.number, "object_id": object_id},
        )


async def publish_alarm_discovery(
    mqtt: MqttPublisher,
    *,
    topic_prefix: str,
    settings: Settings | None = None,
) -> None:
    """Publish retained alarm_control_panel discovery (ADR-003)."""
    topic = alarm_discovery_topic()
    payload = alarm_discovery_payload(topic_prefix=topic_prefix, settings=settings)
    body = json.dumps(payload, separators=(",", ":"))
    await mqtt.publish(topic, body, retain=True)
    logger.debug(
        "mqtt_alarm_discovery_published",
        extra={"topic": topic, "object_id": ALARM_OBJECT_ID},
    )


async def publish_connectivity_discovery(
    mqtt: MqttPublisher,
    *,
    topic_prefix: str,
) -> None:
    """Publish retained panel-link connectivity binary_sensor discovery (ADR-004)."""
    topic = connectivity_discovery_topic()
    payload = connectivity_discovery_payload(topic_prefix=topic_prefix)
    body = json.dumps(payload, separators=(",", ":"))
    await mqtt.publish(topic, body, retain=True)
    logger.debug(
        "mqtt_connectivity_discovery_published",
        extra={"topic": topic, "object_id": CONNECTIVITY_OBJECT_ID},
    )
