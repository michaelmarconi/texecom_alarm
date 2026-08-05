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

_PAYLOAD_TO_HA_MODE = {
    PAYLOAD_ARM_AWAY: "away",
    PAYLOAD_ARM_NIGHT: "night",
    PAYLOAD_ARM_HOME: "home",
}


async def handle_alarm_command(
    panel: PanelClient,
    settings: Settings,
    payload: str | bytes,
) -> None:
    """Translate ARM_*/DISARM MQTT payloads into shared panel commands (ADR-005).

    Does not publish alarm state — MQTT state comes from AREA/snapshot updates.
    Unknown payloads and HA modes not available from the Part-Arm mapping are
    ignored (logged, no panel send).
    """
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    text = text.strip()

    if text == PAYLOAD_DISARM:
        logger.debug("alarm_command_disarm")
        await panel.set_area_disarm()
        return

    ha_mode = _PAYLOAD_TO_HA_MODE.get(text)
    if ha_mode is None:
        logger.debug("alarm_command_ignored", extra={"payload": text})
        return

    mode_byte = settings.mode_byte_for_ha_mode(ha_mode)
    if mode_byte is None:
        logger.debug(
            "alarm_command_unmapped",
            extra={"payload": text, "mode": ha_mode},
        )
        return

    logger.debug("alarm_command_arm", extra={"mode": ha_mode, "byte": mode_byte})
    await panel.set_area_arm(mode_byte)
