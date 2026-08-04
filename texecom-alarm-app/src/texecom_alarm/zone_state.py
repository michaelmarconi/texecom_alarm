"""Shared zone status bitmap decode and MQTT state publish helpers (ADR-006)."""

from __future__ import annotations

import logging
from typing import Protocol

from texecom_alarm.mqtt.discovery import zone_state_topic
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.protocol.frame import MAX_ZONES_PER_STATE_REQUEST
from texecom_alarm.zones import Zone

logger = logging.getLogger(__name__)

# Low 2 bits of the panel status byte (shared by GetZoneState + ZONE pushes).
_STATUS_SECURE = 0


class MqttPublisher(Protocol):
    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        *,
        retain: bool = False,
        qos: int = 0,
    ) -> None: ...


def mqtt_payload_for_status(status: int) -> str:
    """Map panel status byte → MQTT binary_sensor payload ("0"/"1").

    Secure → off ("0"); Active / Tamper / Short → on ("1"). Higher bits are
    ignored for open/closed meaning so snapshot and live pushes stay aligned.
    """
    return "0" if (status & 0x03) == _STATUS_SECURE else "1"


async def publish_zone_state(
    mqtt: MqttPublisher,
    *,
    zone_number: int,
    status: int,
    topic_prefix: str,
) -> None:
    """Publish retained MQTT state for one zone using the shared encoding."""
    topic = zone_state_topic(topic_prefix, zone_number)
    payload = mqtt_payload_for_status(status)
    await mqtt.publish(topic, payload, retain=True)
    logger.debug(
        "mqtt_zone_state",
        extra={"topic": topic, "zone": zone_number, "status": status, "payload": payload},
    )


async def fetch_zone_states(client: PanelClient, zone_count: int) -> bytes:
    """Read status bytes for zone slots 1..zone_count via GetZoneState batches."""
    if zone_count <= 0:
        return b""
    out = bytearray()
    start = 1
    while start <= zone_count:
        batch = min(MAX_ZONES_PER_STATE_REQUEST, zone_count - start + 1)
        out.extend(await client.get_zone_state(start, batch))
        start += batch
    return bytes(out)


async def publish_zone_state_snapshot(
    client: PanelClient,
    mqtt: MqttPublisher,
    zones: list[Zone],
    *,
    topic_prefix: str,
    zone_count: int,
) -> None:
    """GetZoneState snapshot → retained MQTT for in-use zones only (ADR-006)."""
    logger.debug("zone_state_snapshot_start", extra={"zone_count": zone_count})
    statuses = await fetch_zone_states(client, zone_count)
    in_use = {z.number for z in zones}
    for index, status in enumerate(statuses):
        zone_number = index + 1
        if zone_number not in in_use:
            continue
        await publish_zone_state(
            mqtt,
            zone_number=zone_number,
            status=status,
            topic_prefix=topic_prefix,
        )
    logger.debug(
        "zone_state_snapshot_done",
        extra={"published": len(in_use), "slots": len(statuses)},
    )


async def handle_zone_message(
    mqtt: MqttPublisher,
    body: bytes,
    *,
    topic_prefix: str,
    in_use_zones: set[int],
) -> None:
    """Publish MQTT state for a ZONE push (body[0]==MSG_ZONE) if zone is in use."""
    if len(body) < 3:
        logger.debug("zone_message_short", extra={"body": body.hex()})
        return
    zone_number = body[1]
    status = body[2]
    if zone_number not in in_use_zones:
        logger.debug("zone_message_unused_ignored", extra={"zone": zone_number})
        return
    await publish_zone_state(
        mqtt,
        zone_number=zone_number,
        status=status,
        topic_prefix=topic_prefix,
    )
