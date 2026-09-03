"""Panel reconnect after ForcedDisconnect (ADR-004 / ADR-018 / ADR-019)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
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


class MqttPublisher(Protocol):
    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        *,
        retain: bool = False,
        qos: int = 0,
    ) -> None: ...


async def publish_panel_link_state(
    mqtt: MqttPublisher,
    *,
    topic_prefix: str,
    live: bool,
) -> None:
    """Publish retained panel-connection connectivity state (ON=live, OFF=degraded)."""
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
    sleep: Callable[[float], Awaitable[None]] | None = None,
    collision: bool = False,
    current_alarm_payload: str | None = None,
) -> str:
    """Resume after ForcedDisconnect: spaced retries → LOGIN+snapshots → ON.

    A hang-up publishes Connection off immediately. A collision (unreadable
    follow-up after a successful arm/disarm) keeps Connection on if the first
    re-login succeeds; if that first attempt fails, Connection goes off and
    the ordinary keep-trying path runs. Keeps retrying at the one configured
    delay so MQTT LWT does not blank alarm/zone entities — there is no attempt
    cap and no separate interval for a trigger-caused drop. Does not
    re-enumerate zones or re-issue a failed arm/disarm.
    """
    topic_prefix = settings.mqtt_topic_prefix
    delay = settings.reconnect_delay_seconds
    sleeper = sleep if sleep is not None else asyncio.sleep

    if not collision:
        await publish_panel_link_state(mqtt, topic_prefix=topic_prefix, live=False)
        logger.info(
            "Reconnecting to the panel (retrying every %s seconds until it answers).",
            delay,
        )
    else:
        logger.info(
            "Re-logging in after an unreadable follow-up read "
            "(retrying every %s seconds until the panel answers).",
            delay,
        )

    attempt = 0
    while True:
        attempt += 1
        logger.debug("panel_reconnect_attempt", extra={"attempt": attempt, "delay": delay})
        try:
            await panel.close()
        except Exception:
            logger.exception("Could not close the panel connection before a reconnect attempt.")

        await sleeper(delay)

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
                current_alarm_payload=current_alarm_payload,
            )
            await panel.set_event_messages()
            await publish_panel_link_state(mqtt, topic_prefix=topic_prefix, live=True)
            logger.info(
                "Panel reconnect succeeded on attempt %s; alarm state is %s.",
                attempt,
                alarm_payload,
            )
            return alarm_payload
        except Exception:
            if collision and attempt == 1:
                await publish_panel_link_state(mqtt, topic_prefix=topic_prefix, live=False)
                logger.info(
                    "First re-login after an unreadable follow-up read failed — "
                    "Alarm Panel Connection is off; will keep trying every %s seconds.",
                    delay,
                )
            logger.exception(
                "Reconnect attempt %s failed — will keep trying. "
                "If this continues, stop other ComIP clients and check panel power/network.",
                attempt,
            )
            continue
