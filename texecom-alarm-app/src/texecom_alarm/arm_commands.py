"""Map Home Assistant MQTT alarm command payloads to panel arm/disarm calls."""

from __future__ import annotations

import logging

from texecom_alarm.config import Settings
from texecom_alarm.protocol.client import PanelClient

logger = logging.getLogger(__name__)

PAYLOAD_ARM_AWAY = "ARM_AWAY"
PAYLOAD_ARM_NIGHT = "ARM_NIGHT"
PAYLOAD_ARM_HOME = "ARM_HOME"
PAYLOAD_DISARM = "DISARM"


async def handle_alarm_command(
    panel: PanelClient,
    settings: Settings,
    payload: str | bytes,
) -> None:
    """Translate ARM_*/DISARM MQTT payloads into shared panel commands (ADR-005).

    Does not publish alarm state — MQTT state comes from AREA/snapshot updates.
    Unknown payloads are ignored (logged, no panel send).
    """
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    text = text.strip()

    if text == PAYLOAD_ARM_AWAY:
        logger.debug("alarm_command_arm", extra={"mode": "away", "byte": settings.part_arm_away})
        await panel.set_area_arm(settings.part_arm_away)
    elif text == PAYLOAD_ARM_NIGHT:
        logger.debug("alarm_command_arm", extra={"mode": "night", "byte": settings.part_arm_night})
        await panel.set_area_arm(settings.part_arm_night)
    elif text == PAYLOAD_ARM_HOME:
        logger.debug("alarm_command_arm", extra={"mode": "home", "byte": settings.part_arm_home})
        await panel.set_area_arm(settings.part_arm_home)
    elif text == PAYLOAD_DISARM:
        logger.debug("alarm_command_disarm")
        await panel.set_area_disarm()
    else:
        logger.debug("alarm_command_ignored", extra={"payload": text})
