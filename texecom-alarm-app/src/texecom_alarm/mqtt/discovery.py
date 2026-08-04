"""HA MQTT discovery payload builders for zone binary_sensors."""

from __future__ import annotations

import json
import logging
from typing import Protocol

from texecom_alarm.zones import Zone, zone_slug

logger = logging.getLogger(__name__)

AVAILABILITY_ONLINE = "online"
AVAILABILITY_OFFLINE = "offline"


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
