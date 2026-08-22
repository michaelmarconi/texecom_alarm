"""Shared zone status bitmap decode and MQTT state publish helpers (ADR-006)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Protocol

from texecom_alarm.log_labels import zone_status_label
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


def _mqtt_open_closed(payload: str) -> str:
    return "open" if payload == "1" else "closed"


async def publish_zone_state(
    mqtt: MqttPublisher,
    *,
    zone_number: int,
    status: int,
    topic_prefix: str,
    zones: Mapping[int, Zone] | None = None,
    log_change: bool = True,
) -> None:
    """Publish retained MQTT state for one zone using the shared encoding."""
    topic = zone_state_topic(topic_prefix, zone_number)
    payload = mqtt_payload_for_status(status)
    await mqtt.publish(topic, payload, retain=True)
    if not log_change:
        return
    zone = zones.get(zone_number) if zones is not None else None
    name_part = f" name={zone.name!r}" if zone is not None and zone.name else ""
    logger.debug(
        "mqtt_zone_state zone=%s%s %s (status=0x%02x) → MQTT %s (%s)",
        zone_number,
        name_part,
        zone_status_label(status),
        status & 0xFF,
        _mqtt_open_closed(payload),
        payload,
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
    logger.debug("zone_state_snapshot_start zone_count=%s", zone_count)
    statuses = await fetch_zone_states(client, zone_count)
    by_number = {z.number: z for z in zones}
    in_use = set(by_number)
    open_parts: list[str] = []
    published = 0
    for index, status in enumerate(statuses):
        zone_number = index + 1
        if zone_number not in in_use:
            continue
        published += 1
        if (status & 0x03) != _STATUS_SECURE:
            zone = by_number[zone_number]
            label = zone.name if zone.name else f"zone {zone_number}"
            open_parts.append(f"{label} {zone_status_label(status)} (0x{status & 0xFF:02x})")
        await publish_zone_state(
            mqtt,
            zone_number=zone_number,
            status=status,
            topic_prefix=topic_prefix,
            zones=by_number,
            log_change=False,
        )
    if open_parts:
        open_summary = ", ".join(open_parts)
    else:
        open_summary = "all Secure"
    logger.debug(
        "zone_state_snapshot_done published=%s slots=%s open=%s",
        published,
        len(statuses),
        open_summary,
    )


async def handle_zone_message(
    mqtt: MqttPublisher,
    body: bytes,
    *,
    topic_prefix: str,
    in_use_zones: set[int],
    zones: Mapping[int, Zone] | None = None,
) -> None:
    """Publish MQTT state for a ZONE push (body[0]==MSG_ZONE) if zone is in use."""
    if len(body) < 3:
        logger.debug("zone_message_short body=%s", body.hex())
        return
    zone_number = body[1]
    status = body[2]
    if zone_number not in in_use_zones:
        logger.debug("zone_message_unused_ignored zone=%s", zone_number)
        return
    await publish_zone_state(
        mqtt,
        zone_number=zone_number,
        status=status,
        topic_prefix=topic_prefix,
        zones=zones,
    )
