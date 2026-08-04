"""Asyncio application entry: panel login → enum → discovery → snapshot → listen."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from texecom_alarm.area_state import handle_area_message, publish_area_state_snapshot
from texecom_alarm.config import Settings, load_settings
from texecom_alarm.mqtt.discovery import (
    AVAILABILITY_OFFLINE,
    availability_topic,
    publish_alarm_discovery,
    publish_zone_discovery,
)
from texecom_alarm.mqtt.publisher import AiomqttPublisher
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.protocol.frame import MSG_AREA, MSG_ZONE
from texecom_alarm.zone_state import handle_zone_message, publish_zone_state_snapshot
from texecom_alarm.zones import enumerate_zones

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
        await publish_alarm_discovery(mqtt_client, topic_prefix=cfg.mqtt_topic_prefix)

        await publish_zone_state_snapshot(
            panel_client,
            mqtt_client,
            zones,
            topic_prefix=cfg.mqtt_topic_prefix,
            zone_count=zone_count,
        )
        await publish_area_state_snapshot(
            panel_client,
            mqtt_client,
            settings=cfg,
            topic_prefix=cfg.mqtt_topic_prefix,
            zone_count=zone_count,
        )
        await panel_client.set_event_messages()
        logger.debug("app_event_messages_subscribed")

        in_use = {z.number for z in zones}
        listen_task = asyncio.create_task(
            _listen_panel_messages(
                panel_client,
                mqtt_client,
                settings=cfg,
                topic_prefix=cfg.mqtt_topic_prefix,
                in_use_zones=in_use,
            ),
            name="panel-listen",
        )

        if idle is not None:
            await idle()
        else:
            await _idle_forever()
    finally:
        if listen_task is not None and not listen_task.done():
            listen_task.cancel()
            await asyncio.gather(listen_task, return_exceptions=True)
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


async def _listen_panel_messages(
    panel: PanelClient,
    mqtt: object,
    *,
    settings: Settings,
    topic_prefix: str,
    in_use_zones: set[int],
    idle_timeout: float = _KEEPALIVE_IDLE_TIMEOUT,
) -> None:
    """Steady-state loop: ZONE/AREA pushes update MQTT; keepalive on idle timeout."""
    logger.debug("panel_listen_start")
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
            await handle_zone_message(
                mqtt,  # type: ignore[arg-type]
                body,
                topic_prefix=topic_prefix,
                in_use_zones=in_use_zones,
            )
        elif subtype == MSG_AREA:
            await handle_area_message(
                mqtt,  # type: ignore[arg-type]
                body,
                settings=settings,
                topic_prefix=topic_prefix,
            )
        else:
            logger.debug("panel_message_ignored", extra={"subtype": subtype})


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
