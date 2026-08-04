"""Unit tests for AiomqttPublisher helpers and app entry wiring."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.app import _listen_zone_messages, main, run
from texecom_alarm.config import Settings
from texecom_alarm.mqtt.discovery import AVAILABILITY_OFFLINE, AVAILABILITY_ONLINE
from texecom_alarm.mqtt.publisher import AiomqttPublisher
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.protocol.frame import CMD_GETDATETIME


def _settings(panel: FakePanel) -> Settings:
    return Settings(
        panel_host=panel.host,
        panel_port=panel.port,
        udl_password="1234",
        mqtt_host="127.0.0.1",
        mqtt_port=1883,
        mqtt_username="",
        mqtt_password="",
        mqtt_topic_prefix="texecom",
        part_arm_away=0,
        part_arm_night=1,
        part_arm_home=2,
    )


@pytest.mark.asyncio
async def test_listen_loop_sends_keepalive_on_idle_timeout() -> None:
    """Regression: passive listen must keepalive or the panel drops after ~60s."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=1,
    )
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
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        before = panel.keepalive_attempts
        task = asyncio.create_task(
            _listen_zone_messages(
                client,
                mqtt,
                topic_prefix="texecom",
                in_use_zones={1},
                idle_timeout=0.05,
            )
        )
        for _ in range(50):
            if panel.keepalive_attempts > before:
                break
            await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert panel.keepalive_attempts > before
        assert panel.last_command == CMD_GETDATETIME
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_run_owns_panel_with_login_delay() -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR")],
        zone_count=1,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        stop = asyncio.Event()
        task = asyncio.create_task(
            run(_settings(panel), mqtt=mqtt, idle=stop.wait, login_delay=0.0)
        )
        for _ in range(50):
            if any(m.topic.startswith("homeassistant/") for m in mqtt.messages):
                break
            await asyncio.sleep(0.02)
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
        assert mqtt.will_payload == AVAILABILITY_OFFLINE
        assert any("front_door_1" in m.topic for m in mqtt.messages)
        assert mqtt.payloads_for("texecom/status")[-1] == AVAILABILITY_OFFLINE
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_run_publishes_offline_when_discovery_fails_after_online() -> None:
    """Regression: failure after retained online must still clear availability."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR")],
        zone_count=1,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()

        async def fail_after_online(
            mqtt_client: RecordingMqttPublisher,
            zones: object,
            *,
            topic_prefix: str,
        ) -> None:
            await mqtt_client.publish(
                f"{topic_prefix}/status",
                AVAILABILITY_ONLINE,
                retain=True,
            )
            raise RuntimeError("discovery boom")

        with (
            patch("texecom_alarm.app.publish_zone_discovery", side_effect=fail_after_online),
            pytest.raises(RuntimeError, match="discovery boom"),
        ):
            await run(_settings(panel), mqtt=mqtt, idle=asyncio.Event().wait, login_delay=0.0)

        status = mqtt.payloads_for("texecom/status")
        assert AVAILABILITY_ONLINE in status
        assert status[-1] == AVAILABILITY_OFFLINE
        assert mqtt.connected is False
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_publisher_publish_requires_connection() -> None:
    pub = AiomqttPublisher("127.0.0.1", 1)
    with pytest.raises(RuntimeError, match="not connected"):
        await pub.publish("t", "p")


@pytest.mark.asyncio
async def test_publisher_abort_requires_connection() -> None:
    pub = AiomqttPublisher("127.0.0.1", 1)
    with pytest.raises(RuntimeError, match="not connected"):
        await pub.abort()


@pytest.mark.asyncio
async def test_publisher_connect_with_credentials_and_will() -> None:
    pub = AiomqttPublisher(
        "127.0.0.1",
        1883,
        username="u",
        password="p",
        identifier="id-1",
        keepalive=10,
    )
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.publish = AsyncMock()

    with patch("texecom_alarm.mqtt.publisher.aiomqtt.Client", return_value=fake_client) as ctor:
        await pub.connect(will_topic="texecom/status", will_payload="offline", will_retain=True)
        kwargs = ctor.call_args.kwargs
        assert kwargs["username"] == "u"
        assert kwargs["password"] == "p"
        assert kwargs["identifier"] == "id-1"
        assert kwargs["keepalive"] == 10
        assert kwargs["will"] is not None
        await pub.publish("t", "hello", retain=True)
        fake_client.publish.assert_awaited()
        await pub.disconnect()
        fake_client.__aexit__.assert_awaited()


@pytest.mark.asyncio
async def test_publisher_abort_closes_sock() -> None:
    pub = AiomqttPublisher("127.0.0.1", 1)
    sock = MagicMock()
    paho = MagicMock()
    paho._sock = sock
    client = MagicMock()
    client._client = paho
    pub._client = client
    await pub.abort()
    sock.close.assert_called_once()


@pytest.mark.asyncio
async def test_publisher_abort_falls_back_to_sock_close() -> None:
    pub = AiomqttPublisher("127.0.0.1", 1)
    paho = MagicMock()
    paho._sock = None
    paho.socket = MagicMock(return_value=None)
    paho._sock_close = MagicMock()
    client = MagicMock()
    client._client = paho
    pub._client = client
    await pub.abort()
    paho._sock_close.assert_called_once()


@pytest.mark.asyncio
async def test_publisher_abort_raises_when_no_sock() -> None:
    pub = AiomqttPublisher("127.0.0.1", 1)
    paho = MagicMock()
    paho._sock = None
    paho.socket = MagicMock(return_value=None)
    paho._sock_close = None
    client = MagicMock()
    client._client = paho
    pub._client = client
    with pytest.raises(RuntimeError, match="unable to abort"):
        await pub.abort()


def test_main_invokes_asyncio_run() -> None:
    with patch("texecom_alarm.app.asyncio.run") as run_mock:
        main()
        run_mock.assert_called_once()


@pytest.mark.asyncio
async def test_run_loads_settings_when_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="A")],
        zone_count=1,
    )
    await panel.start()
    try:
        monkeypatch.setenv("TEXECOM_PANEL_HOST", panel.host)
        monkeypatch.setenv("TEXECOM_PANEL_PORT", str(panel.port))
        monkeypatch.setenv("TEXECOM_UDL_PASSWORD", "1234")
        monkeypatch.setenv("TEXECOM_MQTT_HOST", "127.0.0.1")
        mqtt = RecordingMqttPublisher()
        client = PanelClient(
            panel.host, panel.port, udl_password="1234", login_delay=0.0, response_timeout=0.5
        )
        await client.connect()
        await client.login()
        stop = asyncio.Event()
        task = asyncio.create_task(run(panel=client, mqtt=mqtt, idle=stop.wait))
        for _ in range(50):
            if mqtt.messages:
                break
            await asyncio.sleep(0.02)
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
        assert mqtt.messages
    finally:
        await panel.stop()
