"""Shared area-flags decode and MQTT alarm-state publish helpers (ADR-007)."""

from __future__ import annotations

import logging
from typing import Protocol

from texecom_alarm.config import Settings
from texecom_alarm.mqtt.discovery import alarm_state_topic
from texecom_alarm.protocol.client import PanelClient, ProtocolError
from texecom_alarm.protocol.frame import AREA_FLAGS_COUNT, AREA_MAP, MSG_AREA

# Re-export for tests / callers that import flag-count from this module.
__all__ = [
    "AREA_FLAGS_COUNT",
    "HOUSE_AREA_NUMBER",
    "area_size_for_zones",
    "decode_area_ha_state",
    "flag_bit",
    "handle_area_message",
    "mqtt_payload_for_area_state",
    "publish_alarm_state",
    "publish_area_state_snapshot",
]

logger = logging.getLogger(__name__)

# Flag indices used by the SPIKE-007 area-flags decode.
FLAG_ALARM = 0
FLAG_ARMED = 21
FLAG_FULL_ARMED = 22
FLAG_PART_ARMED = 23
FLAG_FORCE_ARMED = 26
FLAG_PART_ARM_1 = 50
FLAG_PART_ARM_2 = 51
FLAG_PART_ARM_3 = 52

# HOUSE on this Elite 88 — only in-use area gets an MQTT entity.
HOUSE_AREA_NUMBER = 1

# Live AREA state byte → HA alarm_control_panel payload (non–Part-Arm states).
_LIVE_AREA_STATE_MAP: dict[int, str] = {
    0: "disarmed",
    1: "arming",
    2: "pending",
    3: "armed_away",
    4: "arming",
    5: "triggered",
}

# Settled Part-Arm AREA bytes → panel Part-Arm slot (protocol-reference: 6→1, 7→2).
_LIVE_PART_ARM_STATE_TO_SLOT: dict[int, int] = {
    6: 1,
    7: 2,
}


class MqttPublisher(Protocol):
    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        *,
        retain: bool = False,
        qos: int = 0,
    ) -> None: ...


def area_size_for_zones(zone_count: int) -> int:
    """Derive area bitmap width in bytes from panel zone count (SPIKE-007 areaMap)."""
    areas = AREA_MAP.get(zone_count)
    if areas is None:
        raise ProtocolError(f"no AREA_MAP entry for zone_count={zone_count}")
    return (areas + 7) // 8


def flag_bit(flags: bytes, flag_index: int, *, area_size: int, area_number: int) -> bool:
    """Return whether ``area_number`` (1-based) is set in flag slot ``flag_index``."""
    offset = flag_index * area_size
    chunk = flags[offset : offset + area_size]
    if len(chunk) < area_size:
        return False
    value = int.from_bytes(chunk, "little")
    return bool(value & (1 << (area_number - 1)))


def mqtt_payload_for_area_state(state: int, settings: Settings) -> str | None:
    """Map live AREA state byte → MQTT alarm_control_panel payload.

    Part-Arm settled states (6/7) use the same install-time slot → HA mapping
    as the area-flags snapshot (ADR-005). Unknown bytes return None so callers
    leave the last MQTT payload unchanged (do not guess disarmed).
    """
    slot = _LIVE_PART_ARM_STATE_TO_SLOT.get(state)
    if slot is not None:
        return _ha_state_for_part_arm_slot(slot, settings)
    return _LIVE_AREA_STATE_MAP.get(state)


def _ha_state_for_part_arm_slot(slot: int, settings: Settings) -> str:
    """Invert install-time Part-Arm mapping (ADR-005) to an HA armed_* payload."""
    ha_mode = settings.ha_mode_for_part_arm_slot(slot)
    if ha_mode is None:
        return "armed_away"
    return f"armed_{ha_mode}"


def decode_area_ha_state(
    flags: bytes,
    *,
    area_size: int,
    area_number: int,
    settings: Settings,
) -> str:
    """Decode GetAreaFlags bytes for one area into an HA alarm payload (ADR-007).

    Priority: Alarm → triggered; Armed/FullArmed/ForceArmed/PartArmed → armed_*;
    PartArmed + PartArm slot → Night/Home via inverted Settings; else disarmed.
    Away is never a Part-Arm label (ADR-008); unmapped Part-Arm slots fall back
    to armed_away as a conservative full-arm label.
    """
    alarm = flag_bit(flags, FLAG_ALARM, area_size=area_size, area_number=area_number)
    armed = flag_bit(flags, FLAG_ARMED, area_size=area_size, area_number=area_number)
    full_armed = flag_bit(flags, FLAG_FULL_ARMED, area_size=area_size, area_number=area_number)
    part_armed = flag_bit(flags, FLAG_PART_ARMED, area_size=area_size, area_number=area_number)
    force_armed = flag_bit(flags, FLAG_FORCE_ARMED, area_size=area_size, area_number=area_number)
    part1 = flag_bit(flags, FLAG_PART_ARM_1, area_size=area_size, area_number=area_number)
    part2 = flag_bit(flags, FLAG_PART_ARM_2, area_size=area_size, area_number=area_number)
    part3 = flag_bit(flags, FLAG_PART_ARM_3, area_size=area_size, area_number=area_number)
    part_arm = 1 if part1 else 2 if part2 else 3 if part3 else None

    if alarm:
        return "triggered"
    if not (armed or full_armed or part_armed or force_armed):
        return "disarmed"
    if part_arm is not None:
        return _ha_state_for_part_arm_slot(part_arm, settings)
    return "armed_away"


async def publish_alarm_state(
    mqtt: MqttPublisher,
    *,
    payload: str,
    topic_prefix: str,
) -> None:
    """Publish retained MQTT alarm state for the single HOUSE alarm entity."""
    topic = alarm_state_topic(topic_prefix)
    await mqtt.publish(topic, payload, retain=True)
    logger.debug("mqtt_alarm_state", extra={"topic": topic, "payload": payload})


async def publish_area_state_snapshot(
    client: PanelClient,
    mqtt: MqttPublisher,
    *,
    settings: Settings,
    topic_prefix: str,
    zone_count: int,
) -> str:
    """GetAreaFlags snapshot → retained MQTT for area 1 only (ADR-007).

    Returns the HA payload that was published.
    """
    area_size = area_size_for_zones(zone_count)
    if area_size != 1:
        # Dual-request area_size==8 path is an ADR-007 open follow-on.
        raise ProtocolError(
            f"GetAreaFlags: area_size={area_size} dual-request path not implemented"
        )
    logger.debug(
        "area_state_snapshot_start",
        extra={"zone_count": zone_count, "area_size": area_size, "count": AREA_FLAGS_COUNT},
    )
    flags = await client.get_area_flags(0, AREA_FLAGS_COUNT, area_size=area_size)
    payload = decode_area_ha_state(
        flags,
        area_size=area_size,
        area_number=HOUSE_AREA_NUMBER,
        settings=settings,
    )
    await publish_alarm_state(mqtt, payload=payload, topic_prefix=topic_prefix)
    logger.debug("area_state_snapshot_done", extra={"payload": payload})
    return payload


async def handle_area_message(
    mqtt: MqttPublisher,
    body: bytes,
    *,
    settings: Settings,
    topic_prefix: str,
) -> str | None:
    """Publish MQTT alarm state for an AREA push (body[0]==MSG_AREA) for area 1.

    Returns the published HA payload string, or None if the message was ignored.
    """
    if len(body) < 3:
        logger.debug("area_message_short", extra={"body": body.hex()})
        return None
    if body[0] != MSG_AREA:
        return None
    area_number = body[1]
    state = body[2]
    if area_number != HOUSE_AREA_NUMBER:
        logger.debug("area_message_unused_ignored", extra={"area": area_number})
        return None
    payload = mqtt_payload_for_area_state(state, settings)
    if payload is None:
        logger.warning(
            "Ignoring unknown live AREA state byte %s for area %s — "
            "leaving last Home Assistant alarm state unchanged.",
            state,
            area_number,
        )
        return None
    await publish_alarm_state(mqtt, payload=payload, topic_prefix=topic_prefix)
    return payload
