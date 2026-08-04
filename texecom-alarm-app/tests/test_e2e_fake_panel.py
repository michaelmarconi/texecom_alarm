"""E2E-shaped tests against a mocked panel — never the live household panel."""

from __future__ import annotations

import asyncio
import json
import socket

import pytest
from amqtt.broker import Broker
from amqtt.client import MQTTClient
from amqtt.mqtt.constants import QOS_1
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm import healthcheck
from texecom_alarm.app import run
from texecom_alarm.config import Settings
from texecom_alarm.mqtt.discovery import AVAILABILITY_OFFLINE, AVAILABILITY_ONLINE
from texecom_alarm.mqtt.publisher import AiomqttPublisher
from texecom_alarm.protocol.client import PanelClient


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _settings(panel: FakePanel, mqtt_port: int) -> Settings:
    return Settings(
        panel_host=panel.host,
        panel_port=panel.port,
        udl_password="1234",
        mqtt_host="127.0.0.1",
        mqtt_port=mqtt_port,
        mqtt_username="",
        mqtt_password="",
        mqtt_topic_prefix="texecom",
        part_arm_away=0,
        part_arm_night=1,
        part_arm_home=2,
    )


def test_fake_panel_session_lifecycle() -> None:
    panel = FakePanel()
    assert not panel.authenticated
    panel.connect()
    assert not panel.authenticated
    assert healthcheck().startswith("texecom-alarm/")
    panel.close()
    assert not panel.authenticated


@pytest.mark.asyncio
async def test_e2e_login_against_fake_panel() -> None:
    panel = FakePanel(udl_password="1234")
    await panel.start()
    try:
        client = PanelClient(
            panel.host,
            panel.port,
            udl_password="1234",
            login_delay=0.0,
            response_timeout=0.5,
        )
        await client.connect()
        await client.login()
        assert client.authenticated
        assert panel.authenticated
        await client.close()
    finally:
        await panel.stop()


def test_e2e_discovery_retained_and_lwt_on_app_stop() -> None:
    """FakePanel + in-process amqtt: retained discovery; LWT offline when app drops."""
    asyncio.run(_e2e_discovery_retained_and_lwt())


async def _e2e_discovery_retained_and_lwt() -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="FRONT DOOR"),
            FakeZone(number=2, zone_type=0, name=""),
            FakeZone(number=3, zone_type=3, name="KITCHEN PIR"),
        ],
        zone_count=3,
    )
    await panel.start()

    mqtt_port = _free_port()
    broker = Broker(
        {
            "listeners": {
                "default": {"type": "tcp", "bind": f"127.0.0.1:{mqtt_port}"},
            },
            "sys_interval": 0,
        }
    )
    await broker.start()

    settings = _settings(panel, mqtt_port)
    stop = asyncio.Event()
    mqtt = AiomqttPublisher(
        "127.0.0.1",
        mqtt_port,
        identifier="texecom-alarm-e2e-app",
        keepalive=5,
    )
    panel_client = PanelClient(
        panel.host,
        panel.port,
        udl_password="1234",
        login_delay=0.0,
        response_timeout=1.0,
    )
    await panel_client.connect()
    await panel_client.login()

    # Observer must be subscribed before the app connects (matches LWT delivery path).
    observer = MQTTClient(client_id="texecom-alarm-e2e-observer")
    await observer.connect(f"mqtt://127.0.0.1:{mqtt_port}/")
    await observer.subscribe(
        [
            ("homeassistant/binary_sensor/+/config", QOS_1),
            ("texecom/status", QOS_1),
        ]
    )

    app_task = asyncio.create_task(run(settings, panel=panel_client, mqtt=mqtt, idle=stop.wait))

    try:
        discovered: dict[str, dict] = {}
        status_payloads: list[str] = []
        deadline = asyncio.get_running_loop().time() + 8.0
        while asyncio.get_running_loop().time() < deadline and not (
            len(discovered) == 2 and AVAILABILITY_ONLINE in status_payloads
        ):
            if app_task.done():
                exc = app_task.exception()
                if exc is not None:
                    raise exc
            try:
                message = await asyncio.wait_for(observer.deliver_message(), timeout=0.4)
            except TimeoutError:
                continue
            packet = message.publish_packet
            topic = packet.variable_header.topic_name
            payload = packet.payload.data.decode("utf-8")
            if topic.startswith("homeassistant/"):
                discovered[topic] = json.loads(payload)
            elif topic == "texecom/status":
                status_payloads.append(payload)

        assert "homeassistant/binary_sensor/texecom_alarm_front_door/config" in discovered
        assert "homeassistant/binary_sensor/texecom_alarm_kitchen_pir/config" in discovered
        assert len(discovered) == 2
        assert AVAILABILITY_ONLINE in status_payloads

        front = discovered["homeassistant/binary_sensor/texecom_alarm_front_door/config"]
        assert front["availability_topic"] == "texecom/status"
        assert front["unique_id"] == "texecom_alarm_front_door"

        # Simulate app-process crash: abort MQTT TCP without DISCONNECT → broker LWT.
        await mqtt.abort()

        lwt_seen = False
        deadline = asyncio.get_running_loop().time() + 8.0
        while asyncio.get_running_loop().time() < deadline and not lwt_seen:
            try:
                message = await asyncio.wait_for(observer.deliver_message(), timeout=0.5)
            except TimeoutError:
                continue
            packet = message.publish_packet
            topic = packet.variable_header.topic_name
            payload = packet.payload.data.decode("utf-8")
            if topic == "texecom/status" and payload == AVAILABILITY_OFFLINE:
                lwt_seen = True

        assert lwt_seen, f"expected LWT offline on texecom/status, got {status_payloads!r}"
    finally:
        # Avoid graceful offline-publish hang after we already aborted the socket.
        mqtt._client = None
        stop.set()
        if not app_task.done():
            app_task.cancel()
            await asyncio.gather(app_task, return_exceptions=True)
        try:
            await observer.disconnect()
        except Exception:  # noqa: S110
            pass
        await broker.shutdown()
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_app_run_with_recording_mqtt() -> None:
    """App wiring: FakePanel enum → discovery on recording stub (no broker)."""
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="FRONT DOOR"),
            FakeZone(number=2, zone_type=0, name=""),
        ],
        zone_count=2,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = _settings(panel, mqtt_port=1883)
        stop = asyncio.Event()
        client = PanelClient(
            panel.host,
            panel.port,
            udl_password="1234",
            login_delay=0.0,
            response_timeout=0.5,
        )
        await client.connect()
        await client.login()

        task = asyncio.create_task(run(settings, panel=client, mqtt=mqtt, idle=stop.wait))
        for _ in range(50):
            if any(m.topic.startswith("homeassistant/") for m in mqtt.messages):
                break
            await asyncio.sleep(0.02)
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)

        topics = [m.topic for m in mqtt.messages]
        assert "homeassistant/binary_sensor/texecom_alarm_front_door/config" in topics
        assert "texecom/status" in topics
        assert mqtt.will_payload == AVAILABILITY_OFFLINE
    finally:
        await panel.stop()
