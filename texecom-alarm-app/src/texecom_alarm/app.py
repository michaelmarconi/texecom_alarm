"""Asyncio application entry: panel login → enum → discovery → snapshot → listen."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from texecom_alarm.area_state import handle_area_message, publish_area_state_snapshot
from texecom_alarm.arm_commands import handle_alarm_command
from texecom_alarm.config import Settings, load_settings
from texecom_alarm.mqtt.discovery import (
    AVAILABILITY_OFFLINE,
    alarm_command_topic,
    availability_topic,
    publish_alarm_discovery,
    publish_connectivity_discovery,
    publish_zone_discovery,
)
from texecom_alarm.mqtt.publisher import AiomqttPublisher
from texecom_alarm.protocol.client import ForcedDisconnect, PanelClient
from texecom_alarm.protocol.frame import MSG_AREA, MSG_LOG, MSG_ZONE
from texecom_alarm.reconnect import publish_panel_link_state, reconnect_after_disconnect
from texecom_alarm.trigger_snapshot import TriggerActivityBuffer, maybe_publish_trigger_snapshot
from texecom_alarm.zone_state import handle_zone_message, publish_zone_state_snapshot
from texecom_alarm.zones import Zone, enumerate_zones

logger = logging.getLogger(__name__)

# Panel drops passive listen-only sessions after ~60s; ~15s GETDATETIME keeps alive
# (docs/protocol-reference.md). Used as recv_message idle timeout → keepalive.
_KEEPALIVE_IDLE_TIMEOUT = 15.0


async def run(
    settings: Settings | None = None,
    *,
    panel: PanelClient | None = None,
    mqtt: object | None = None,
    idle: Callable[[], Awaitable[None]] | None = None,
    login_delay: float | None = None,
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
            await panel_client.connect()
            await panel_client.login()

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

        command_topic = alarm_command_topic(cfg.mqtt_topic_prefix)
        await mqtt_client.subscribe(command_topic)  # type: ignore[attr-defined]
        logger.debug("mqtt_alarm_command_subscribed", extra={"topic": command_topic})

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
                initial_alarm_payload=initial_alarm_payload,
            ),
            name="panel-listen",
        )
        command_task = asyncio.create_task(
            _listen_alarm_commands(
                panel_client,
                mqtt_client,
                settings=cfg,
                command_topic=command_topic,
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
                logger.exception("mqtt_offline_publish_failed")
        try:
            await mqtt_client.disconnect()
        except Exception:
            logger.exception("mqtt_disconnect_failed")
        if owns_panel:
            try:
                await panel_client.close()
            except Exception:
                logger.exception("panel_close_failed")
        logger.debug("app_stop")


async def _listen_alarm_commands(
    panel: PanelClient,
    mqtt: object,
    *,
    settings: Settings,
    command_topic: str,
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
            await handle_alarm_command(panel, settings, payload)
        except Exception:
            logger.exception("alarm_command_failed", extra={"topic": topic})


async def _listen_with_reconnect(
    panel: PanelClient,
    mqtt: object,
    *,
    settings: Settings,
    zones: list[Zone],
    zone_count: int,
    topic_prefix: str,
    in_use_zones: set[int],
    idle_timeout: float = _KEEPALIVE_IDLE_TIMEOUT,
    initial_alarm_payload: str | None = None,
) -> None:
    """Listen for panel pushes; on ForcedDisconnect, asymmetric reconnect then resume."""
    last_alarm_payload = initial_alarm_payload
    # Survive outages: one rolling buffer across reconnect cycles (ADR-004).
    activity = TriggerActivityBuffer()
    while True:
        try:
            last_alarm_payload = await _listen_panel_messages(
                panel,
                mqtt,
                settings=settings,
                topic_prefix=topic_prefix,
                in_use_zones=in_use_zones,
                idle_timeout=idle_timeout,
                initial_alarm_payload=last_alarm_payload,
                activity=activity,
            )
        except Exception:
            # Non-recoverable listen failure: mark panel-link degraded, never
            # alarm/zone availability (ADR-004). Cancellation is BaseException.
            logger.exception("panel_listen_failed")
            await publish_panel_link_state(
                mqtt,  # type: ignore[arg-type]
                topic_prefix=topic_prefix,
                live=False,
            )
            raise
        logger.info(
            "panel_forced_disconnect",
            extra={"last_alarm_payload": last_alarm_payload},
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
    idle_timeout: float = _KEEPALIVE_IDLE_TIMEOUT,
    initial_alarm_payload: str | None = None,
    activity: TriggerActivityBuffer | None = None,
) -> str | None:
    """Steady-state loop until ForcedDisconnect; returns last HOUSE alarm payload.

    Keepalive on idle timeout. Cancellation still propagates.
    """
    logger.debug("panel_listen_start")
    buffer = activity if activity is not None else TriggerActivityBuffer()
    # Seed from area-flags snapshot so cold-start already-in-alarm does not invent.
    last_alarm_payload: str | None = initial_alarm_payload
    try:
        while True:
            try:
                frame = await panel.recv_message(timeout=idle_timeout)
            except TimeoutError:
                await panel.keepalive()
                continue
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
                else:
                    logger.debug("log_message_short", extra={"body": body.hex()})
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
                        previous_payload=last_alarm_payload,
                        new_payload=new_payload,
                        topic_prefix=topic_prefix,
                        buffer=buffer,
                    )
                    last_alarm_payload = new_payload
            else:
                logger.debug("panel_message_ignored", extra={"subtype": subtype})
    except ForcedDisconnect:
        return last_alarm_payload


# Backward-compatible alias for tests that still import the old name.
_listen_zone_messages = _listen_panel_messages


async def _idle_forever() -> None:
    """Block until cancelled — keeps the s6-supervised process alive."""
    stop = asyncio.Event()
    await stop.wait()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
