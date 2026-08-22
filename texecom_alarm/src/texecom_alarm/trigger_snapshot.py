"""Rolling trigger activity buffer and last-trigger MQTT attributes (ADR-004)."""

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from texecom_alarm.mqtt.discovery import alarm_attributes_topic
from texecom_alarm.zones import Zone

# Re-export so callers/tests can import the topic helper alongside the buffer.
__all__ = [
    "TriggerActivityBuffer",
    "alarm_attributes_topic",
    "maybe_publish_trigger_snapshot",
]

logger = logging.getLogger(__name__)

# Low 2 bits: Secure == 0 (same encoding as zone_state / ADR-006).
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


@dataclass(frozen=True, slots=True)
class _ZoneActivity:
    zone_number: int
    status: int
    when: datetime


@dataclass(frozen=True, slots=True)
class _LogActivity:
    event_type: int
    group: int
    when: datetime


@dataclass
class TriggerActivityBuffer:
    """Short rolling memory of recent ZONE/LOG activity for trigger snapshots."""

    maxlen: int = 32
    _events: deque[object] = field(init=False)

    def __post_init__(self) -> None:
        self._events = deque(maxlen=self.maxlen)

    def record_zone(
        self,
        zone_number: int,
        status: int,
        *,
        when: datetime | None = None,
    ) -> None:
        stamp = when if when is not None else datetime.now(UTC)
        self._events.append(_ZoneActivity(zone_number, status, stamp))

    def record_log(
        self,
        event_type: int,
        group: int,
        *,
        when: datetime | None = None,
    ) -> None:
        stamp = when if when is not None else datetime.now(UTC)
        self._events.append(_LogActivity(event_type, group, stamp))

    def initiating_zone(self) -> int | None:
        """Most recent buffered ZONE whose low 2 bits ≠ Secure, else None."""
        for event in reversed(self._events):
            if isinstance(event, _ZoneActivity) and (event.status & 0x03) != _STATUS_SECURE:
                return event.zone_number
        return None


async def maybe_publish_trigger_snapshot(
    mqtt: MqttPublisher,
    *,
    previous_payload: str | None,
    new_payload: str | None,
    topic_prefix: str,
    buffer: TriggerActivityBuffer,
    clock: Callable[[], datetime] | None = None,
    zones: Mapping[int, Zone] | None = None,
) -> None:
    """On edge into HA ``triggered`` only, publish retained last-trigger attributes.

    Cold-start already-in-alarm (previous already ``triggered``) does not invent a
    snapshot. Disarm must not clear attributes — callers simply omit any clear publish;
    the next enter-triggered edge overwrites.
    """
    if new_payload != "triggered" or previous_payload == "triggered":
        return
    now = (clock or (lambda: datetime.now(UTC)))()
    zone_number = buffer.initiating_zone()
    body = {
        "last_trigger_zone": zone_number,
        "last_trigger_time": now.astimezone(UTC).isoformat(),
    }
    topic = alarm_attributes_topic(topic_prefix)
    await mqtt.publish(topic, json.dumps(body, separators=(",", ":")), retain=True)
    name_part = ""
    if zone_number is not None and zones is not None:
        zone = zones.get(zone_number)
        if zone is not None and zone.name:
            name_part = f" name={zone.name!r}"
    logger.debug(
        "mqtt_trigger_snapshot zone=%s%s topic=%s",
        zone_number,
        name_part,
        topic,
    )
