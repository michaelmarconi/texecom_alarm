"""Asyncio application entry: panel login → zone enum → MQTT discovery → idle."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from texecom_alarm.config import Settings, load_settings
from texecom_alarm.mqtt.discovery import (
    AVAILABILITY_OFFLINE,
    availability_topic,
    publish_zone_discovery,
)
from texecom_alarm.mqtt.publisher import AiomqttPublisher
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.zones import enumerate_zones

logger = logging.getLogger(__name__)


async def run(
    settings: Settings | None = None,
    *,
    panel: PanelClient | None = None,
    mqtt: object | None = None,
    idle: Callable[[], Awaitable[None]] | None = None,
    login_delay: float | None = None,
) -> None:
    """Connect to panel and MQTT, enumerate zones, publish discovery, then idle for s6."""
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
    try:
        logger.debug("app_start")
        if owns_panel:
            await panel_client.connect()
            await panel_client.login()

        zones = await enumerate_zones(panel_client)
        logger.info("enumerated_zones", extra={"count": len(zones)})

        avail = availability_topic(cfg.mqtt_topic_prefix)
        await mqtt_client.connect(
            will_topic=avail,
            will_payload=AVAILABILITY_OFFLINE,
            will_retain=True,
        )
        mqtt_connected = True
        await publish_zone_discovery(mqtt_client, zones, topic_prefix=cfg.mqtt_topic_prefix)

        if idle is not None:
            await idle()
        else:
            await _idle_forever()
    finally:
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
