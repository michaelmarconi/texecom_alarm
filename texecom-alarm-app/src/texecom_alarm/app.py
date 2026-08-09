"""Asyncio application entry: panel login → enum → discovery → snapshot → listen."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from texecom_alarm.area_state import handle_area_message, publish_area_state_snapshot
from texecom_alarm.arm_commands import handle_alarm_command
from texecom_alarm.config import Settings, load_settings
from texecom_alarm.logging_setup import TRACE_LEVEL, configure_logging
from texecom_alarm.mqtt.discovery import (
    AVAILABILITY_OFFLINE,
    alarm_command_topic,
    availability_topic,
    publish_alarm_discovery,
    publish_connectivity_discovery,
    publish_zone_discovery,
)
from texecom_alarm.mqtt.publisher import AiomqttPublisher
from texecom_alarm.panel_trust import (
    RECOVER_WINDOW_SECONDS,
    TRUST_POLL_INTERVAL_SECONDS,
    PanelTrust,
)
from texecom_alarm.protocol.client import ForcedDisconnect, PanelClient, ProtocolError
from texecom_alarm.protocol.frame import (
    MSG_AREA,
    MSG_DEBUG,
    MSG_LOG,
    MSG_OUTPUT,
    MSG_USER,
    MSG_ZONE,
)
from texecom_alarm.reconnect import publish_panel_link_state, reconnect_after_disconnect
from texecom_alarm.trigger_snapshot import TriggerActivityBuffer, maybe_publish_trigger_snapshot
from texecom_alarm.zone_state import handle_zone_message, publish_zone_state_snapshot
from texecom_alarm.zones import Zone, enumerate_zones

logger = logging.getLogger(__name__)

# Panel drops passive listen-only sessions after ~60s; ~15s GETDATETIME keeps alive
# (docs/protocol-reference.md). Used as recv_message idle timeout → keepalive.
_KEEPALIVE_IDLE_TIMEOUT = 15.0

_MSG_SUBTYPE_LABELS: dict[int, str] = {
    MSG_DEBUG: "DEBUG",
    MSG_ZONE: "ZONE",
    MSG_AREA: "AREA",
    MSG_OUTPUT: "OUTPUT",
    MSG_USER: "USER",
    MSG_LOG: "LOG",
}


def _msg_subtype_label(subtype: int) -> str:
    return _MSG_SUBTYPE_LABELS.get(subtype, f"unknown({subtype})")


@dataclass
class _SharedAlarmState:
    """Last known HA alarm payload shared by listen + MQTT command tasks."""

    payload: str | None = None


async def run(
    settings: Settings | None = None,
    *,
    panel: PanelClient | None = None,
    mqtt: object | None = None,
    idle: Callable[[], Awaitable[None]] | None = None,
    login_delay: float | None = None,
    startup_retry_interval: float | None = None,
    startup_sleep: Callable[[float], Awaitable[None]] | None = None,
    trust_poll_interval: float | None = None,
    trust_recover_window: float | None = None,
) -> None:
    """Connect, enumerate, discover, snapshot zone+alarm state, subscribe, listen."""
    cfg = settings if settings is not None else load_settings()
    owns_panel = panel is None

    panel_kwargs: dict = {}
    if login_delay is not None:
        panel_kwargs["login_delay"] = login_delay
    panel_client = panel or PanelClient(
        cfg.panel_host, cfg.panel_port, cfg.udl_password, **panel_kwargs
    )
    mqtt_client = mqtt or AiomqttPublisher(
        cfg.mqtt_host,
        cfg.mqtt_port,
        username=cfg.mqtt_username,
        password=cfg.mqtt_password,
    )

    # True once MQTT is connected: failure paths must publish offline before a
    # clean DISCONNECT (otherwise retained "online" sticks and LWT never fires).
    # Hard crash / abort() still relies on LWT (no clean DISCONNECT).
    mqtt_connected = False
    listen_task: asyncio.Task[None] | None = None
    command_task: asyncio.Task[None] | None = None
    try:
        logger.debug("app_start")
        if owns_panel:
            await _connect_and_login_with_retry(
                panel_client,
                host=cfg.panel_host,
                port=cfg.panel_port,
                interval=(
                    startup_retry_interval
                    if startup_retry_interval is not None
                    else cfg.reconnect_normal_interval_seconds
                ),
                sleep=startup_sleep,
            )

        zones, zone_count = await enumerate_zones(panel_client)
        logger.info("enumerated_zones", extra={"count": len(zones), "zone_count": zone_count})

        avail = availability_topic(cfg.mqtt_topic_prefix)
        await mqtt_client.connect(
            will_topic=avail,
            will_payload=AVAILABILITY_OFFLINE,
            will_retain=True,
        )
        mqtt_connected = True
        await publish_zone_discovery(mqtt_client, zones, topic_prefix=cfg.mqtt_topic_prefix)
        await publish_alarm_discovery(mqtt_client, topic_prefix=cfg.mqtt_topic_prefix, settings=cfg)
        await publish_connectivity_discovery(mqtt_client, topic_prefix=cfg.mqtt_topic_prefix)

        await publish_zone_state_snapshot(
            panel_client,
            mqtt_client,
            zones,
            topic_prefix=cfg.mqtt_topic_prefix,
            zone_count=zone_count,
        )
        initial_alarm_payload = await publish_area_state_snapshot(
            panel_client,
            mqtt_client,
            settings=cfg,
            topic_prefix=cfg.mqtt_topic_prefix,
            zone_count=zone_count,
        )
        await panel_client.set_event_messages()
        await publish_panel_link_state(
            mqtt_client,  # type: ignore[arg-type]
            topic_prefix=cfg.mqtt_topic_prefix,
            live=True,
        )
        logger.debug("app_event_messages_subscribed")

        trust = PanelTrust(
            mqtt_client,  # type: ignore[arg-type]
            topic_prefix=cfg.mqtt_topic_prefix,
            zone_count=zone_count,
            poll_interval=(
                trust_poll_interval
                if trust_poll_interval is not None
                else TRUST_POLL_INTERVAL_SECONDS
            ),
            recover_window=(
                trust_recover_window if trust_recover_window is not None else RECOVER_WINDOW_SECONDS
            ),
        )
        # Startup area-flags snapshot already corroborated house state.
        await trust.reset_after_reconnect()

        command_topic = alarm_command_topic(cfg.mqtt_topic_prefix)
        await mqtt_client.subscribe(command_topic)  # type: ignore[attr-defined]
        logger.debug("mqtt_alarm_command_subscribed", extra={"topic": command_topic})

        alarm_state = _SharedAlarmState(payload=initial_alarm_payload)
        in_use = {z.number for z in zones}
        listen_task = asyncio.create_task(
            _listen_with_reconnect(
                panel_client,
                mqtt_client,
                settings=cfg,
                zones=zones,
                zone_count=zone_count,
                topic_prefix=cfg.mqtt_topic_prefix,
                in_use_zones=in_use,
                alarm_state=alarm_state,
                trust=trust,
            ),
            name="panel-listen",
        )
        command_task = asyncio.create_task(
            _listen_alarm_commands(
                panel_client,
                mqtt_client,
                settings=cfg,
                command_topic=command_topic,
                alarm_state=alarm_state,
                trust=trust,
            ),
            name="mqtt-alarm-commands",
        )

        if idle is not None:
            await idle()
        else:
            await _idle_forever()
    finally:
        for task in (command_task, listen_task):
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        if mqtt_connected:
            try:
                await mqtt_client.publish(
                    availability_topic(cfg.mqtt_topic_prefix),
                    AVAILABILITY_OFFLINE,
                    retain=True,
                )
            except Exception:
                logger.exception(
                    "Could not publish MQTT offline before shutdown — "
                    "Home Assistant may briefly show a stale online status."
                )
        try:
            await mqtt_client.disconnect()
        except Exception:
            logger.exception("Could not disconnect from the MQTT broker cleanly during shutdown.")
        if owns_panel:
            try:
                await panel_client.close()
            except Exception:
                logger.exception(
                    "Could not close the panel network connection cleanly during shutdown."
                )
        logger.debug("app_stop")


async def _connect_and_login_with_retry(
    panel: PanelClient,
    *,
    host: str,
    port: int,
    interval: float,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> None:
    """Keep retrying first connect/login until the panel accepts (continuous-operation)."""
    sleeper = sleep if sleep is not None else asyncio.sleep
    attempt = 0
    while True:
        attempt += 1
        try:
            await panel.connect()
            await panel.login()
            if attempt > 1:
                logger.info(
                    "Connected to the panel at %s:%s after %s attempt(s).",
                    host,
                    port,
                    attempt,
                )
            return
        except (TimeoutError, OSError, ProtocolError, ForcedDisconnect) as exc:
            logger.error(
                "Could not log in to the panel at %s:%s (attempt %s): %s "
                "Keeping the add-on running and retrying in %g seconds. "
                "If this persists, stop any other app using the panel (Texecom Connect / "
                "another add-on) — only one ComIP client is allowed.",
                host,
                port,
                attempt,
                exc,
                interval,
            )
            try:
                await panel.close()
            except Exception:
                logger.exception("Could not close the failed panel connection before retrying.")
            await sleeper(interval)


async def _listen_alarm_commands(
    panel: PanelClient,
    mqtt: object,
    *,
    settings: Settings,
    command_topic: str,
    alarm_state: _SharedAlarmState,
    trust: PanelTrust | None = None,
) -> None:
    """Subscribe loop: MQTT ARM_*/DISARM → shared panel arm/disarm (ADR-005)."""
    inbound = mqtt.inbound_messages  # type: ignore[attr-defined]
    logger.debug("mqtt_alarm_command_listen_start", extra={"topic": command_topic})
    async for message in inbound:
        topic = str(getattr(message, "topic", ""))
        if topic != command_topic:
            continue
        payload = getattr(message, "payload", b"")
        try:
            await handle_alarm_command(
                panel,
                settings,
                payload,
                mqtt=mqtt,  # type: ignore[arg-type]
                topic_prefix=settings.mqtt_topic_prefix,
                get_current_alarm_state=lambda: alarm_state.payload,
                trust=trust,
            )
        except Exception:
            logger.exception(
                "Unexpected failure while handling an MQTT alarm command on topic %s.",
                topic,
            )


async def _listen_with_reconnect(
    panel: PanelClient,
    mqtt: object,
    *,
    settings: Settings,
    zones: list[Zone],
    zone_count: int,
    topic_prefix: str,
    in_use_zones: set[int],
    alarm_state: _SharedAlarmState,
    idle_timeout: float = _KEEPALIVE_IDLE_TIMEOUT,
    trust: PanelTrust | None = None,
) -> None:
    """Listen for panel pushes; on ForcedDisconnect, asymmetric reconnect then resume."""
    # Survive outages: one rolling buffer across reconnect cycles (ADR-004).
    activity = TriggerActivityBuffer()
    while True:
        try:
            await _listen_panel_messages(
                panel,
                mqtt,
                settings=settings,
                topic_prefix=topic_prefix,
                in_use_zones=in_use_zones,
                idle_timeout=idle_timeout,
                alarm_state=alarm_state,
                activity=activity,
                trust=trust,
            )
        except Exception:
            # Non-recoverable listen failure: mark panel-link degraded, never
            # alarm/zone availability (ADR-004). Cancellation is BaseException.
            logger.exception(
                "Panel listen loop failed unexpectedly — marking Alarm Panel Connected "
                "as disconnected and stopping this listen cycle."
            )
            await publish_panel_link_state(
                mqtt,  # type: ignore[arg-type]
                topic_prefix=topic_prefix,
                live=False,
            )
            raise
        last_alarm_payload = alarm_state.payload
        logger.info(
            "Panel ended the monitoring session (forced disconnect); "
            "last alarm state was %s. Reconnecting…",
            last_alarm_payload,
        )
        previous_payload = last_alarm_payload
        last_alarm_payload = await reconnect_after_disconnect(
            panel,
            mqtt,  # type: ignore[arg-type]
            settings=settings,
            zones=zones,
            zone_count=zone_count,
            last_alarm_payload=last_alarm_payload,
        )
        alarm_state.payload = last_alarm_payload
        if trust is not None:
            await trust.reset_after_reconnect()
        # Snapshot may edge into triggered during the outage; use preserved buffer.
        await maybe_publish_trigger_snapshot(
            mqtt,  # type: ignore[arg-type]
            previous_payload=previous_payload,
            new_payload=last_alarm_payload,
            topic_prefix=topic_prefix,
            buffer=activity,
        )


async def _listen_panel_messages(
    panel: PanelClient,
    mqtt: object,
    *,
    settings: Settings,
    topic_prefix: str,
    in_use_zones: set[int],
    alarm_state: _SharedAlarmState,
    idle_timeout: float = _KEEPALIVE_IDLE_TIMEOUT,
    activity: TriggerActivityBuffer | None = None,
    trust: PanelTrust | None = None,
) -> None:
    """Steady-state loop until ForcedDisconnect.

    Keepalive on idle timeout; periodic house/arm trust poll alongside (ADR-010).
    Cancellation still propagates.
    Updates ``alarm_state`` when HOUSE AREA pushes change the MQTT payload.
    """
    logger.debug("panel_listen_start")
    buffer = activity if activity is not None else TriggerActivityBuffer()
    try:
        while True:
            wait = idle_timeout
            if trust is not None and trust.poll_due():
                wait = min(wait, 0.05)
            elif trust is not None:
                wait = min(wait, max(0.05, trust.seconds_until_poll()))
            try:
                frame = await panel.recv_message(timeout=wait)
            except TimeoutError:
                # Idle or trust-poll slice elapsed: keep session alive and
                # corroborate house/arm state when due (ADR-010).
                try:
                    await panel.keepalive()
                    if trust is not None:
                        trust.note_keepalive_ok()
                except Exception:
                    if trust is not None:
                        trust.note_keepalive_failed()
                    raise
                if trust is not None:
                    await trust.maybe_poll(panel)
                continue
            if trust is not None:
                await trust.maybe_poll(panel)
            body = frame.body
            if not body:
                logger.debug("panel_message_empty")
                continue
            subtype = body[0]
            if subtype == MSG_ZONE:
                if len(body) >= 3:
                    buffer.record_zone(body[1], body[2])
                await handle_zone_message(
                    mqtt,  # type: ignore[arg-type]
                    body,
                    topic_prefix=topic_prefix,
                    in_use_zones=in_use_zones,
                )
            elif subtype == MSG_LOG:
                # Record type/group when present; LOG never publishes MQTT state.
                if len(body) >= 3:
                    buffer.record_log(body[1], body[2])
                    logger.log(
                        TRACE_LEVEL,
                        "panel_event LOG type=%s group=%s (kept for trigger snapshot; "
                        "not used for alarm MQTT state) body=%s",
                        body[1],
                        body[2],
                        body.hex(),
                    )
                else:
                    logger.log(
                        TRACE_LEVEL,
                        "panel_event LOG short/unusual body=%s",
                        body.hex(),
                    )
            elif subtype == MSG_AREA:
                new_payload = await handle_area_message(
                    mqtt,  # type: ignore[arg-type]
                    body,
                    settings=settings,
                    topic_prefix=topic_prefix,
                )
                if new_payload is not None:
                    await maybe_publish_trigger_snapshot(
                        mqtt,  # type: ignore[arg-type]
                        previous_payload=alarm_state.payload,
                        new_payload=new_payload,
                        topic_prefix=topic_prefix,
                        buffer=buffer,
                    )
                    alarm_state.payload = new_payload
            else:
                # OUTPUT / USER / DEBUG / unknown — not decoded for MQTT yet.
                logger.log(
                    TRACE_LEVEL,
                    "panel_event %s ignored for MQTT (not decoded as zone/area state) body=%s",
                    _msg_subtype_label(subtype),
                    body.hex(),
                )
    except ForcedDisconnect:
        return


# Backward-compatible alias for tests that still import the old name.
_listen_zone_messages = _listen_panel_messages


async def _idle_forever() -> None:
    """Block until cancelled — keeps the s6-supervised process alive."""
    stop = asyncio.Event()
    await stop.wait()


def main() -> None:
    try:
        cfg = load_settings()
    except Exception as exc:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("texecom_alarm").error(
            "Cannot start: add-on configuration is invalid — %s. "
            "Open the Texecom Alarm Configuration tab in Supervisor, fix the highlighted "
            "options, and start the add-on again.",
            exc,
        )
        raise SystemExit(1) from exc
    configure_logging(cfg.log_level)
    try:
        asyncio.run(run(cfg))
    except Exception as exc:
        logger.exception(
            "Texecom Alarm stopped because of an unexpected error: %s. "
            "If this keeps happening after a restart, copy the traceback "
            "above when asking for help.",
            exc,
        )
        raise


if __name__ == "__main__":
    main()
