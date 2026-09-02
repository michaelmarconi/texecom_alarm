"""Map Home Assistant MQTT alarm command payloads to panel arm/disarm calls."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Protocol

from texecom_alarm.alarm_flags_guard import (
    coerce_flags_payload_after_disarm,
    flags_round_trip_needed_after_command,
    flags_snapshot_may_replace_live,
)
from texecom_alarm.area_state import (
    HOUSE_AREA_NUMBER,
    area_size_for_zones,
    decode_area_ha_state,
    mqtt_payload_for_area_state,
    publish_alarm_state,
)
from texecom_alarm.config import Settings
from texecom_alarm.mqtt.discovery import publish_blocked_arm_event
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
from texecom_alarm.protocol.frame import AREA_FLAGS_COUNT, MSG_AREA

logger = logging.getLogger(__name__)

# Pause so Home Assistant can apply Arming before the snap-back payload.
_REFUSE_ARMING_HOLD_S = 0.35

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


def _alarm_payload_from_queued_area(panel: object, settings: Settings) -> str | None:
    """Read live AREA already queued during the ACK wait, then put frames back.

    Garage return sends AREA disarmed as interleaved ``M`` frames while disarm
    is in flight. Those sit on the command queue until the listen loop runs,
    so MQTT still looks armed when we decide whether to ask for flags.
    """
    if not isinstance(panel, PanelClient):
        return None
    frames = panel.take_queued_messages()
    latest: str | None = None
    for frame in frames:
        body = frame.body
        if body and body[0] == MSG_AREA and len(body) >= 3 and body[1] == HOUSE_AREA_NUMBER:
            decoded = mqtt_payload_for_area_state(body[2], settings)
            if decoded is not None:
                latest = decoded
    for frame in frames:
        panel.enqueue_unsolicited(frame)
    return latest


def _payload_after_ack(
    panel: object,
    settings: Settings,
    get_current_alarm_state: Callable[[], str | None] | None,
    fallback: str | None,
) -> str | None:
    current = get_current_alarm_state() if get_current_alarm_state is not None else fallback
    queued = _alarm_payload_from_queued_area(panel, settings)
    return queued if queued is not None else current


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
    """Ask the panel for area flags after a successful disarm ACK only when
    live AREA/LOG has not already published unset.

    After a successful arm ACK this is a no-op: live AREA carries exit/armed,
    and a flags read during that burst collides. An unreadable reply after the
    tap already ACK'd is re-raised so the session can log in again; it is not
    recorded as a failed arm or disarm. A NAK or timeout on this housekeeping
    read is the panel being busy, not a lost connection — Connection stays as
    it was.
    """
    if mqtt is None or topic_prefix is None or zone_count is None:
        return None
    if not flags_round_trip_needed_after_command(
        current_alarm_payload,
        after_arm=is_arm,
        after_disarm=not is_arm,
    ):
        logger.debug(
            "alarm_flags_round_trip_skipped",
            extra={
                "current": current_alarm_payload,
                "after_arm": is_arm,
                "after_disarm": not is_arm,
            },
        )
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
            "Area-flags refresh after %s was rejected: %s "
            "The command already succeeded; this is not a failed tap.",
            "arm" if is_arm else "disarm",
            exc,
        )
        return None
    except TimeoutError as exc:
        logger.warning(
            "Area-flags refresh after %s timed out: %s "
            "The command already succeeded; the panel was busy, not gone.",
            "arm" if is_arm else "disarm",
            exc,
        )
        return None
    except ForcedDisconnect as exc:
        logger.warning(
            "Panel session became unreadable during area-flags refresh after %s: %s "
            "The command already succeeded; this is a collision to resync, not a failed tap.",
            "arm" if is_arm else "disarm",
            exc,
        )
        if trust is not None:
            trust.note_session_collision()
        raise


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
    ready_state: object | None = None,
) -> str | None:
    """Translate ARM_*/DISARM MQTT payloads into shared panel commands (ADR-008).

    DISARM when the house is already unset is a no-op: a queued duplicate must
    not send a second SETAREADISARM into the post-ACK event burst.

    On success, ask the panel for area flags only after disarm when live
    AREA/LOG has not already published unset. Arm never does that follow-up
    read: live AREA carries exit/armed, and asking during the post-ACK burst
    collides. Returns the HA payload to keep shared state in sync when flags
    were skipped because live AREA already said disarmed.
    """
    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    text = text.strip()
    current = get_current_alarm_state() if get_current_alarm_state is not None else None

    if text == PAYLOAD_DISARM:
        if current == "disarmed":
            logger.debug("alarm_command_disarm_ignored already=disarmed")
            return None
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
                # Chatty waits are retried as a new request inside the client.
                # Reaching here means the wait was silent or those retries were
                # used up — we cannot talk, so Connection goes off now.
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
        # Re-read live state after ACK — AREA may already be queued from the wait.
        current_after = _payload_after_ack(panel, settings, get_current_alarm_state, current)
        refreshed = await _refresh_alarm_from_flags(
            panel,
            settings,
            mqtt=mqtt,
            topic_prefix=topic_prefix,
            zone_count=zone_count,
            trust=trust,
            is_arm=False,
            current_alarm_payload=current_after,
        )
        if refreshed is not None:
            return refreshed
        # Flags skipped because live AREA already answered; keep shared state in
        # sync so a queued second DISARM does not TX into the post-ACK burst.
        return current_after if current_after == "disarmed" else None

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

    if ready_state is not None and not getattr(ready_state, ha_mode, True):
        logger.info("alarm_command_blocked mode=%s", ha_mode)
        if mqtt is not None and topic_prefix is not None:
            await publish_blocked_arm_event(
                mqtt,
                topic_prefix=topic_prefix,
                mode=ha_mode,
            )
            live_state = get_current_alarm_state() if get_current_alarm_state is not None else None
            if live_state is not None:
                # MQTT-only bounce: Home Assistant ignores a second copy of the
                # same payload, so flash Arming first, then the panel's current state.
                # Do not update live alarm state to arming — flags/trust polls must
                # still see the real current payload.
                if live_state != "arming":
                    await publish_alarm_state(
                        mqtt,
                        payload="arming",
                        topic_prefix=topic_prefix,
                    )
                    await asyncio.sleep(_REFUSE_ARMING_HOLD_S)
                await publish_alarm_state(
                    mqtt,
                    payload=live_state,
                    topic_prefix=topic_prefix,
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
            # Chatty waits are retried as a new request inside the client.
            # Reaching here means the wait was silent or those retries were
            # used up — we cannot talk, so Connection goes off now.
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
    current_after = _payload_after_ack(panel, settings, get_current_alarm_state, current)
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
