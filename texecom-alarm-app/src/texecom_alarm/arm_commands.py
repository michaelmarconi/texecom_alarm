"""Map Home Assistant MQTT alarm command payloads to panel arm/disarm calls."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from texecom_alarm.area_state import publish_alarm_state
from texecom_alarm.config import Settings
from texecom_alarm.panel_trust import (
    REASON_ARM_NAK,
    REASON_ARM_TIMEOUT,
    REASON_DISARM_NAK,
    REASON_DISARM_TIMEOUT,
    PanelTrust,
)
from texecom_alarm.protocol.client import PanelClient, ProtocolError

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


class MqttPublisher(Protocol):
    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        *,
        retain: bool = False,
        qos: int = 0,
    ) -> None: ...


async def handle_alarm_command(
    panel: PanelClient,
    settings: Settings,
    payload: str | bytes,
    *,
    mqtt: MqttPublisher | None = None,
    topic_prefix: str | None = None,
    get_current_alarm_state: Callable[[], str | None] | None = None,
    trust: PanelTrust | None = None,
) -> None:
    """Translate ARM_*/DISARM MQTT payloads into shared panel commands (ADR-008).

    Does not publish optimistic armed_* on success — MQTT state comes from
    AREA/snapshot updates. On panel NAK for arm, republishes the live last-known
    alarm state (via get_current_alarm_state at NAK time) so HA does not leave a
    stuck mode selection and mid-flight retained updates are not overwritten.
    Arm/disarm reject or timeout also records a panel-link trust failure (ADR-010).
    Unknown payloads and HA modes not available from the Part-Arm mapping are
    ignored (logged, no panel send). Away always uses full-arm mode byte 0.
    """
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    text = text.strip()

    if text == PAYLOAD_DISARM:
        logger.debug("alarm_command_disarm")
        try:
            await panel.set_area_disarm()
        except ProtocolError as exc:
            logger.warning(
                "Panel rejected disarm request: %s",
                exc,
            )
            if trust is not None:
                await trust.record_command_failure(REASON_DISARM_NAK)
        except TimeoutError as exc:
            logger.warning(
                "Panel disarm request timed out: %s",
                exc,
            )
            if trust is not None:
                await trust.record_command_failure(REASON_DISARM_TIMEOUT)
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
    try:
        await panel.set_area_arm(mode_byte)
    except ProtocolError as exc:
        logger.warning(
            "Panel rejected arm request for mode %s: %s "
            "Home Assistant will be refreshed with the current alarm state.",
            ha_mode,
            exc,
        )
        if trust is not None:
            await trust.record_command_failure(REASON_ARM_NAK, ha_mode=ha_mode)
        live_state = get_current_alarm_state() if get_current_alarm_state is not None else None
        if mqtt is not None and topic_prefix is not None and live_state is not None:
            await publish_alarm_state(
                mqtt,
                payload=live_state,
                topic_prefix=topic_prefix,
            )
        return
    except TimeoutError as exc:
        logger.warning(
            "Panel arm request for mode %s timed out: %s",
            ha_mode,
            exc,
        )
        if trust is not None:
            await trust.record_command_failure(REASON_ARM_TIMEOUT, ha_mode=ha_mode)
        live_state = get_current_alarm_state() if get_current_alarm_state is not None else None
        if mqtt is not None and topic_prefix is not None and live_state is not None:
            await publish_alarm_state(
                mqtt,
                payload=live_state,
                topic_prefix=topic_prefix,
            )
        return
