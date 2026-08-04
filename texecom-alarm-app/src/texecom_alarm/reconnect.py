"""Asymmetric panel reconnect after ForcedDisconnect (ADR-002 / ADR-004)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from texecom_alarm.area_state import publish_area_state_snapshot
from texecom_alarm.config import Settings
from texecom_alarm.mqtt.discovery import (
    PANEL_LINK_OFF,
    PANEL_LINK_ON,
    connectivity_state_topic,
)
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.zone_state import publish_zone_state_snapshot
from texecom_alarm.zones import Zone

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReconnectProfile:
    """Tunable reconnect budget for one disconnect class (ADR-002)."""

    name: str
    attempts: int
    interval_seconds: float


class MqttPublisher(Protocol):
    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        *,
        retain: bool = False,
        qos: int = 0,
    ) -> None: ...


def select_reconnect_profile(
    settings: Settings,
    *,
    last_alarm_payload: str | None,
) -> ReconnectProfile:
    """Choose normal vs trigger budget from last HOUSE alarm MQTT payload."""
    if last_alarm_payload == "triggered":
        return ReconnectProfile(
            name="trigger",
            attempts=settings.reconnect_trigger_attempts,
            interval_seconds=settings.reconnect_trigger_interval_seconds,
        )
    return ReconnectProfile(
        name="normal",
        attempts=settings.reconnect_normal_attempts,
        interval_seconds=settings.reconnect_normal_interval_seconds,
    )


async def publish_panel_link_state(
    mqtt: MqttPublisher,
    *,
    topic_prefix: str,
    live: bool,
) -> None:
    """Publish retained panel-link connectivity state (ON=live, OFF=degraded)."""
    topic = connectivity_state_topic(topic_prefix)
    payload = PANEL_LINK_ON if live else PANEL_LINK_OFF
    await mqtt.publish(topic, payload, retain=True)
    logger.debug("mqtt_panel_link_state", extra={"topic": topic, "payload": payload})


async def reconnect_after_disconnect(
    panel: PanelClient,
    mqtt: MqttPublisher,
    *,
    settings: Settings,
    zones: list[Zone],
    zone_count: int,
    last_alarm_payload: str | None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> str:
    """Resume after ForcedDisconnect: OFF → budgeted retries → LOGIN+snapshots → ON.

    Never exits the process after exhausting the named attempt budget — keeps
    retrying at the selected interval so MQTT LWT does not blank alarm/zone
    entities (ADR-004). Does not re-enumerate zones.
    """
    topic_prefix = settings.mqtt_topic_prefix
    profile = select_reconnect_profile(settings, last_alarm_payload=last_alarm_payload)
    sleeper = sleep if sleep is not None else asyncio.sleep

    await publish_panel_link_state(mqtt, topic_prefix=topic_prefix, live=False)
    logger.info(
        "panel_reconnect_start",
        extra={
            "profile": profile.name,
            "attempts": profile.attempts,
            "interval_seconds": profile.interval_seconds,
            "last_alarm_payload": last_alarm_payload,
        },
    )

    attempt = 0
    while True:
        attempt += 1
        logger.debug(
            "panel_reconnect_attempt",
            extra={"profile": profile.name, "attempt": attempt, "budget": profile.attempts},
        )
        try:
            await panel.close()
        except Exception:
            logger.exception("panel_reconnect_close_failed")

        await sleeper(profile.interval_seconds)

        try:
            await panel.connect()
            await panel.login()
            await publish_zone_state_snapshot(
                panel,
                mqtt,
                zones,
                topic_prefix=topic_prefix,
                zone_count=zone_count,
            )
            alarm_payload = await publish_area_state_snapshot(
                panel,
                mqtt,
                settings=settings,
                topic_prefix=topic_prefix,
                zone_count=zone_count,
            )
            await panel.set_event_messages()
            await publish_panel_link_state(mqtt, topic_prefix=topic_prefix, live=True)
            logger.info(
                "panel_reconnect_ok",
                extra={"profile": profile.name, "attempt": attempt, "alarm": alarm_payload},
            )
            return alarm_payload
        except Exception:
            logger.exception(
                "panel_reconnect_attempt_failed",
                extra={"profile": profile.name, "attempt": attempt},
            )
            # Named budget is informational; keep retrying indefinitely (ADR-004).
            continue
