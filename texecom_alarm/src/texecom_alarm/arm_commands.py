"""Map Home Assistant MQTT alarm command payloads to panel arm/disarm calls."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from texecom_alarm.alarm_flags_guard import (
    coerce_flags_payload_after_disarm,
    flags_snapshot_may_replace_live,
)
from texecom_alarm.area_state import (
    HOUSE_AREA_NUMBER,
    area_size_for_zones,
    decode_area_ha_state,
    publish_alarm_state,
)
from texecom_alarm.config import Settings
from texecom_alarm.panel_trust import (
    REASON_ARM_DISCONNECT,
    REASON_ARM_NAK,
    REASON_ARM_TIMEOUT,
    REASON_DISARM_DISCONNECT,
    REASON_DISARM_NAK,
    REASON_DISARM_TIMEOUT,
    PanelTrust,
)
from texecom_alarm.protocol.client import ForcedDisconnect, PanelClient, ProtocolError
from texecom_alarm.protocol.frame import AREA_FLAGS_COUNT

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


async def _refresh_alarm_from_flags(
    panel: PanelClient,
    settings: Settings,
    *,
    mqtt: MqttPublisher | None,
    topic_prefix: str | None,
    zone_count: int | None,
    trust: PanelTrust | None,
    is_arm: bool,
    ha_mode: str | None = None,
    current_alarm_payload: str | None = None,
) -> str | None:
    """Publish GetAreaFlags after a successful arm/disarm ACK when safe (ADR-009)."""
    if mqtt is None or topic_prefix is None or zone_count is None:
        return None
    try:
        area_size = area_size_for_zones(zone_count)
        if area_size != 1:
            raise ProtocolError(
                f"GetAreaFlags: area_size={area_size} dual-request path not implemented"
            )
        flags = await panel.get_area_flags(0, AREA_FLAGS_COUNT, area_size=area_size)
        decoded = decode_area_ha_state(
            flags,
            area_size=area_size,
            area_number=HOUSE_AREA_NUMBER,
            settings=settings,
        )
        if not is_arm:
            decoded = coerce_flags_payload_after_disarm(decoded)
        if not flags_snapshot_may_replace_live(
            current_alarm_payload,
            decoded,
            after_arm=is_arm,
            after_disarm=not is_arm,
        ):
            logger.debug(
                "alarm_flags_refresh_skipped",
                extra={
                    "current": current_alarm_payload,
                    "decoded": decoded,
                    "after_arm": is_arm,
                    "after_disarm": not is_arm,
                },
            )
            return None
        await publish_alarm_state(mqtt, payload=decoded, topic_prefix=topic_prefix)
        return decoded
    except ProtocolError as exc:
        logger.warning(
            "Panel rejected area-flags refresh after %s: %s",
            "arm" if is_arm else "disarm",
            exc,
        )
        if trust is not None:
            reason = REASON_ARM_NAK if is_arm else REASON_DISARM_NAK
            await trust.record_command_failure(reason, ha_mode=ha_mode)
        return None
    except TimeoutError as exc:
        logger.warning(
            "Area-flags refresh after %s timed out: %s",
            "arm" if is_arm else "disarm",
            exc,
        )
        if trust is not None:
            reason = REASON_ARM_TIMEOUT if is_arm else REASON_DISARM_TIMEOUT
            await trust.record_command_failure(reason, ha_mode=ha_mode)
        return None
    except ForcedDisconnect as exc:
        logger.warning(
            "Panel session ended during area-flags refresh after %s: %s",
            "arm" if is_arm else "disarm",
            exc,
        )
        if trust is not None:
            reason = REASON_ARM_DISCONNECT if is_arm else REASON_DISARM_DISCONNECT
            await trust.record_command_failure(reason, ha_mode=ha_mode)
        return None


async def handle_alarm_command(
    panel: PanelClient,
    settings: Settings,
    payload: str | bytes,
    *,
    mqtt: MqttPublisher | None = None,
    topic_prefix: str | None = None,
    get_current_alarm_state: Callable[[], str | None] | None = None,
    trust: PanelTrust | None = None,
    zone_count: int | None = None,
) -> str | None:
    """Translate ARM_*/DISARM MQTT payloads into shared panel commands (ADR-008).

    On success, may refresh alarm MQTT from GetAreaFlags when that would not
    clobber exit/entry (arming/pending) or publish a stale post-arm disarmed
    read. Disarm refresh covers the Home disarm omitted-AREA case. Returns the
    new HA payload when a snapshot was published, else None.
    """
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    text = text.strip()
    current = get_current_alarm_state() if get_current_alarm_state is not None else None

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
            return None
        except TimeoutError as exc:
            logger.warning(
                "Panel disarm request timed out: %s",
                exc,
            )
            if trust is not None:
                await trust.record_command_failure(REASON_DISARM_TIMEOUT)
            return None
        except ForcedDisconnect as exc:
            logger.warning(
                "Panel session ended during disarm: %s",
                exc,
            )
            if trust is not None:
                await trust.record_command_failure(REASON_DISARM_DISCONNECT)
            return None
        # Re-read live state after ACK — AREA/trust may have moved MQTT during the command.
        if get_current_alarm_state is not None:
            current_after = get_current_alarm_state()
        else:
            current_after = current
        return await _refresh_alarm_from_flags(
            panel,
            settings,
            mqtt=mqtt,
            topic_prefix=topic_prefix,
            zone_count=zone_count,
            trust=trust,
            is_arm=False,
            current_alarm_payload=current_after,
        )

    ha_mode = _PAYLOAD_TO_HA_MODE.get(text)
    if ha_mode is None:
        logger.debug("alarm_command_ignored", extra={"payload": text})
        return None

    mode_byte = settings.mode_byte_for_ha_mode(ha_mode)
    if mode_byte is None:
        logger.debug(
            "alarm_command_unmapped",
            extra={"payload": text, "mode": ha_mode},
        )
        return None

    logger.debug("alarm_command_arm mode=%s byte=%s", ha_mode, mode_byte)
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
        return None
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
        return None
    except ForcedDisconnect as exc:
        logger.warning(
            "Panel session ended during arm request for mode %s: %s",
            ha_mode,
            exc,
        )
        if trust is not None:
            await trust.record_command_failure(REASON_ARM_DISCONNECT, ha_mode=ha_mode)
        live_state = get_current_alarm_state() if get_current_alarm_state is not None else None
        if mqtt is not None and topic_prefix is not None and live_state is not None:
            await publish_alarm_state(
                mqtt,
                payload=live_state,
                topic_prefix=topic_prefix,
            )
        return None
    # Re-read live state after ACK — AREA may have pushed arming during the command.
    current_after = get_current_alarm_state() if get_current_alarm_state is not None else current
    return await _refresh_alarm_from_flags(
        panel,
        settings,
        mqtt=mqtt,
        topic_prefix=topic_prefix,
        zone_count=zone_count,
        trust=trust,
        is_arm=True,
        ha_mode=ha_mode,
        current_alarm_payload=current_after,
    )
