"""HA MQTT discovery payload builders for zone binary_sensors and alarm panel."""

from __future__ import annotations

import json
import logging
from typing import Protocol

from texecom_alarm.zones import Zone, zone_slug

logger = logging.getLogger(__name__)

AVAILABILITY_ONLINE = "online"
AVAILABILITY_OFFLINE = "offline"

ALARM_OBJECT_ID = "texecom_alarm_arm_status"


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
    """Provisional object_id: texecom_alarm_{slug}_{zone_number} (unique per zone)."""
    return f"texecom_alarm_{zone_slug(zone.name, zone_number=zone.number)}"


def zone_state_topic(topic_prefix: str, zone_number: int) -> str:
    return f"{topic_prefix}/zone/{zone_number}/state"


def zone_discovery_topic(object_id: str) -> str:
    return f"homeassistant/binary_sensor/{object_id}/config"


def alarm_state_topic(topic_prefix: str) -> str:
    return f"{topic_prefix}/alarm/state"


def alarm_command_topic(topic_prefix: str) -> str:
    return f"{topic_prefix}/alarm/command"


def alarm_discovery_topic(object_id: str = ALARM_OBJECT_ID) -> str:
    return f"homeassistant/alarm_control_panel/{object_id}/config"


def zone_discovery_payload(zone: Zone, *, topic_prefix: str) -> dict[str, object]:
    object_id = zone_object_id(zone)
    return {
        "name": zone.name or f"Zone {zone.number}",
        "unique_id": object_id,
        "object_id": object_id,
        "state_topic": zone_state_topic(topic_prefix, zone.number),
        "availability_topic": availability_topic(topic_prefix),
        "payload_available": AVAILABILITY_ONLINE,
        "payload_not_available": AVAILABILITY_OFFLINE,
        "payload_on": "1",
        "payload_off": "0",
    }


def alarm_discovery_payload(*, topic_prefix: str) -> dict[str, object]:
    return {
        "name": "Arm Status",
        "unique_id": ALARM_OBJECT_ID,
        "object_id": ALARM_OBJECT_ID,
        "state_topic": alarm_state_topic(topic_prefix),
        "command_topic": alarm_command_topic(topic_prefix),
        "availability_topic": availability_topic(topic_prefix),
        "payload_available": AVAILABILITY_ONLINE,
        "payload_not_available": AVAILABILITY_OFFLINE,
        "code_arm_required": False,
        "code_disarm_required": False,
        "supported_features": ["arm_home", "arm_away", "arm_night"],
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
) -> None:
    """Publish retained alarm_control_panel discovery (ADR-003)."""
    topic = alarm_discovery_topic()
    payload = alarm_discovery_payload(topic_prefix=topic_prefix)
    body = json.dumps(payload, separators=(",", ":"))
    await mqtt.publish(topic, body, retain=True)
    logger.debug(
        "mqtt_alarm_discovery_published",
        extra={"topic": topic, "object_id": ALARM_OBJECT_ID},
    )
