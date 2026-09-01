"""Unit tests for AiomqttPublisher helpers and app entry wiring."""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm import __version__
from texecom_alarm.app import _listen_zone_messages, _SharedAlarmState, main, run
from texecom_alarm.config import Settings
from texecom_alarm.logging_setup import configure_logging
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
        part_arm_1="night",
        part_arm_2="home",
        part_arm_3="unused",
    )


@pytest.mark.asyncio
async def test_listen_loop_sends_keepalive_on_idle_timeout() -> None:
    """Regression: passive listen must keepalive or the panel drops after ~60s."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
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
                settings=_settings(panel),
                topic_prefix="texecom",
                in_use_zones={1},
                alarm_state=_SharedAlarmState(),
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
async def test_listen_loop_sends_checkins_on_schedule_under_continuous_traffic() -> None:
    """A busy panel must not be able to starve the check-in schedule (ADR-020).

    Continuous unsolicited zone traffic used to reset the old idle-timeout
    clock on every frame, so the check-in never fired while traffic kept
    arriving. Check-ins must now fire on a fixed elapsed-time schedule
    regardless of how much other traffic the panel is sending.
    """
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
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

        stop_traffic = asyncio.Event()

        async def _flood() -> None:
            status = 0
            while not stop_traffic.is_set():
                status ^= 1
                await panel.inject_zone_message(1, status)
                await asyncio.sleep(0.01)

        flood_task = asyncio.create_task(_flood())
        before = panel.keepalive_attempts
        task = asyncio.create_task(
            _listen_zone_messages(
                client,
                mqtt,
                settings=_settings(panel),
                topic_prefix="texecom",
                in_use_zones={1},
                alarm_state=_SharedAlarmState(),
                idle_timeout=0.05,
            )
        )
        try:
            for _ in range(150):
                if panel.keepalive_attempts >= before + 5:
                    break
                await asyncio.sleep(0.02)
        finally:
            stop_traffic.set()
            await asyncio.gather(flood_task, return_exceptions=True)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert (
            len(mqtt.payloads_for("texecom/zone/1/state")) >= 2
        ), "test setup must actually produce continuous inbound traffic"
        assert (
            panel.keepalive_attempts >= before + 5
        ), "continuous inbound traffic must not starve the scheduled check-in"
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_run_owns_panel_with_login_delay() -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR")],
        zone_count=12,
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
        assert any("front_door_zone_1" in m.topic for m in mqtt.messages)
        assert mqtt.payloads_for("texecom/status")[-1] == AVAILABILITY_OFFLINE
        link_cfg = "homeassistant/binary_sensor/texecom_alarm_panel_connection/config"
        assert any(m.topic == link_cfg and m.retain for m in mqtt.messages)
        link_states = [m for m in mqtt.messages if m.topic == "texecom/panel_connection/state"]
        assert link_states and link_states[0].payload == "ON" and link_states[0].retain is True
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_run_publishes_offline_when_discovery_fails_after_online() -> None:
    """Regression: failure after retained online must still clear availability."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR")],
        zone_count=12,
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
    with pytest.raises(RuntimeError, match="not connected|MQTT publisher is not connected"):
        await pub.publish("t", "p")


@pytest.mark.asyncio
async def test_publisher_abort_requires_connection() -> None:
    pub = AiomqttPublisher("127.0.0.1", 1)
    with pytest.raises(RuntimeError, match="not connected|MQTT publisher is not connected"):
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
    with pytest.raises(RuntimeError, match="unable to abort|Unable to abort"):
        await pub.abort()


def test_main_invokes_asyncio_run() -> None:
    settings = Settings(
        panel_host="10.0.0.2",
        panel_port=10001,
        udl_password="1234",
        mqtt_host="mqtt.local",
        mqtt_port=1883,
        mqtt_username="",
        mqtt_password="",
        mqtt_topic_prefix="texecom",
        part_arm_1="unused",
        part_arm_2="unused",
        part_arm_3="unused",
        log_level="DEBUG",
    )
    with (
        patch("texecom_alarm.app.load_settings", return_value=settings) as load_mock,
        patch("texecom_alarm.app.configure_logging") as configure_mock,
        patch("texecom_alarm.app.asyncio.run") as run_mock,
    ):
        main()
        load_mock.assert_called_once_with()
        configure_mock.assert_called_once_with("DEBUG")
        run_mock.assert_called_once()
        coro = run_mock.call_args.args[0]
        assert asyncio.iscoroutine(coro)
        coro.close()


@pytest.fixture
def restore_root_logging() -> None:
    """Keep a real configure_logging call from leaking handlers into later tests."""
    root = logging.getLogger()
    before_level = root.level
    before_handlers = list(root.handlers)
    yield
    root.handlers.clear()
    for handler in before_handlers:
        root.addHandler(handler)
    root.setLevel(before_level)


def test_main_logs_package_version_at_info(restore_root_logging: None) -> None:
    """A Supervisor log dump at the default level names the running release."""
    settings = Settings(
        panel_host="10.0.0.2",
        panel_port=10001,
        udl_password="1234",
        mqtt_host="mqtt.local",
        mqtt_port=1883,
        mqtt_username="",
        mqtt_password="",
        mqtt_topic_prefix="texecom",
        part_arm_1="unused",
        part_arm_2="unused",
        part_arm_3="unused",
        log_level="INFO",
    )
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    capture = _Capture(level=logging.NOTSET)

    def _configure_then_capture(log_level: str) -> None:
        configure_logging(log_level)
        logging.getLogger().addHandler(capture)

    with (
        patch("texecom_alarm.app.load_settings", return_value=settings),
        patch("texecom_alarm.app.configure_logging", side_effect=_configure_then_capture),
        patch("texecom_alarm.app.asyncio.run") as run_mock,
    ):
        main()
        coro = run_mock.call_args.args[0]
        coro.close()

    version_records = [r for r in records if __version__ in r.getMessage()]
    assert version_records, "boot must log the package version after log level is applied"
    assert all(r.levelno == logging.INFO for r in version_records)


@pytest.mark.asyncio
async def test_run_loads_settings_when_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="A")],
        zone_count=12,
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
        await asyncio.wait_for(task, timeout=5.0)
        assert mqtt.messages
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_retained_alarm_command_is_ignored() -> None:
    """Retained ARM_*/DISARM must not execute (restart replay hazard)."""
    from texecom_alarm.app import _listen_alarm_commands
    from texecom_alarm.mqtt.discovery import alarm_command_topic

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.set_area_arm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    settings = Settings(
        panel_host="127.0.0.1",
        panel_port=10001,
        udl_password="1234",
        mqtt_host="127.0.0.1",
        mqtt_port=1883,
        mqtt_username="",
        mqtt_password="",
        mqtt_topic_prefix="texecom",
        part_arm_1="night",
        part_arm_2="home",
        part_arm_3="unused",
    )
    command_topic = alarm_command_topic("texecom")
    alarm_state = _SharedAlarmState(payload="armed_home")
    task = asyncio.create_task(
        _listen_alarm_commands(
            panel,
            mqtt,
            settings=settings,
            command_topic=command_topic,
            alarm_state=alarm_state,
            zone_count=12,
        )
    )
    await mqtt.push_inbound(command_topic, "DISARM", retain=True)
    await asyncio.sleep(0.05)
    panel.set_area_disarm.assert_not_awaited()

    await mqtt.push_inbound(command_topic, "DISARM", retain=False)
    for _ in range(50):
        if panel.set_area_disarm.await_count:
            break
        await asyncio.sleep(0.02)
    panel.set_area_disarm.assert_awaited_once()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_queued_second_disarm_does_not_call_panel() -> None:
    """Two DISARM MQTT payloads in a row: only the first tap reaches the panel."""
    from texecom_alarm.app import _listen_alarm_commands
    from texecom_alarm.mqtt.discovery import alarm_command_topic

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.set_area_arm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    settings = _command_settings()
    command_topic = alarm_command_topic("texecom")
    alarm_state = _SharedAlarmState(payload="armed_away")
    task = asyncio.create_task(
        _listen_alarm_commands(
            panel,
            mqtt,
            settings=settings,
            command_topic=command_topic,
            alarm_state=alarm_state,
            zone_count=12,
        )
    )
    await mqtt.push_inbound(command_topic, "DISARM")
    await mqtt.push_inbound(command_topic, "DISARM")
    for _ in range(50):
        if panel.set_area_disarm.await_count >= 1 and alarm_state.payload == "disarmed":
            break
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.05)
    panel.set_area_disarm.assert_awaited_once()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_run_clears_retained_command_topic_after_subscribe() -> None:
    """After subscribe, publish empty retained payload to clear leftover commands."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR")],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        stop = asyncio.Event()
        task = asyncio.create_task(
            run(_settings(panel), mqtt=mqtt, idle=stop.wait, login_delay=0.0)
        )
        for _ in range(100):
            if "texecom/alarm/command" in mqtt.subscribed:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        clears = [
            m
            for m in mqtt.messages
            if m.topic == "texecom/alarm/command" and m.retain and m.payload in ("", b"")
        ]
        assert clears, "expected empty retained clear on alarm command topic"
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


def _command_settings() -> Settings:
    return Settings(
        panel_host="127.0.0.1",
        panel_port=10001,
        udl_password="1234",
        mqtt_host="127.0.0.1",
        mqtt_port=1883,
        mqtt_username="",
        mqtt_password="",
        mqtt_topic_prefix="texecom",
        part_arm_1="night",
        part_arm_2="home",
        part_arm_3="unused",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "arm_payload"),
    [
        ("away", "ARM_AWAY"),
        ("home", "ARM_HOME"),
        ("night", "ARM_NIGHT"),
    ],
)
async def test_alarm_command_topic_refuses_unready_arm(mode: str, arm_payload: str) -> None:
    """HA alarm command topic: matching ready switch off skips panel arm.

    MQTT sequence is arming then the current alarm payload.
    """
    from texecom_alarm.app import _listen_alarm_commands, _ReadyToArmState
    from texecom_alarm.mqtt.discovery import alarm_command_topic, ready_command_topic

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.set_area_arm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    settings = _command_settings()
    command_topic = alarm_command_topic("texecom")
    ready_topics = {
        ready_command_topic("texecom", item): item for item in ("away", "home", "night")
    }
    ready_state = _ReadyToArmState()
    ready_state.set_mode(mode, False)
    alarm_state = _SharedAlarmState(payload="disarmed")
    task = asyncio.create_task(
        _listen_alarm_commands(
            panel,
            mqtt,
            settings=settings,
            command_topic=command_topic,
            alarm_state=alarm_state,
            zone_count=12,
            ready_state=ready_state,
            ready_command_topics=ready_topics,
        )
    )
    await mqtt.push_inbound(command_topic, arm_payload)
    for _ in range(50):
        if mqtt.payloads_for("texecom/alarm/state")[-2:] == ["arming", "disarmed"]:
            break
        await asyncio.sleep(0.02)
    panel.set_area_arm.assert_not_awaited()
    assert alarm_state.payload == "disarmed"
    assert mqtt.payloads_for("texecom/alarm/state") == ["arming", "disarmed"]
    alarm_msgs = [m for m in mqtt.messages if m.topic == "texecom/alarm/state"]
    assert alarm_msgs[-1].retain is True
    assert alarm_msgs[-2].retain is True
    assert alarm_msgs[-2].payload == "arming"
    events = mqtt.payloads_for("texecom/blocked_arm/event")
    assert events
    body = json.loads(events[-1])
    assert body["event_type"] == mode
    assert "reason" not in body
    event_msgs = [m for m in mqtt.messages if m.topic == "texecom/blocked_arm/event"]
    assert event_msgs[-1].retain is False
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_alarm_command_topic_refuses_unready_arm_while_armed() -> None:
    """HA command path: refuse while armed bounces MQTT arming then that armed state; no disarm."""
    from texecom_alarm.app import _listen_alarm_commands, _ReadyToArmState
    from texecom_alarm.mqtt.discovery import alarm_command_topic, ready_command_topic

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.set_area_arm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    settings = _command_settings()
    command_topic = alarm_command_topic("texecom")
    ready_topics = {
        ready_command_topic("texecom", item): item for item in ("away", "home", "night")
    }
    ready_state = _ReadyToArmState()
    ready_state.set_mode("away", False)
    alarm_state = _SharedAlarmState(payload="armed_home")
    task = asyncio.create_task(
        _listen_alarm_commands(
            panel,
            mqtt,
            settings=settings,
            command_topic=command_topic,
            alarm_state=alarm_state,
            zone_count=12,
            ready_state=ready_state,
            ready_command_topics=ready_topics,
        )
    )
    await mqtt.push_inbound(command_topic, "ARM_AWAY")
    for _ in range(50):
        if mqtt.payloads_for("texecom/alarm/state")[-2:] == ["arming", "armed_home"]:
            break
        await asyncio.sleep(0.02)
    panel.set_area_arm.assert_not_awaited()
    panel.set_area_disarm.assert_not_awaited()
    assert alarm_state.payload == "armed_home"
    assert mqtt.payloads_for("texecom/alarm/state") == ["arming", "armed_home"]
    events = mqtt.payloads_for("texecom/blocked_arm/event")
    assert events
    body = json.loads(events[-1])
    assert body["event_type"] == "away"
    assert "reason" not in body
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_disarm_on_alarm_command_topic_with_all_ready_off() -> None:
    """DISARM on HA's alarm command topic still reaches the panel when every switch is off."""
    from texecom_alarm.app import _listen_alarm_commands, _ReadyToArmState
    from texecom_alarm.mqtt.discovery import alarm_command_topic, ready_command_topic

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.set_area_arm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    settings = _command_settings()
    command_topic = alarm_command_topic("texecom")
    ready_state = _ReadyToArmState()
    for mode in ("away", "home", "night"):
        ready_state.set_mode(mode, False)
    ready_topics = {
        ready_command_topic("texecom", mode): mode for mode in ("away", "home", "night")
    }
    alarm_state = _SharedAlarmState(payload="armed_away")
    task = asyncio.create_task(
        _listen_alarm_commands(
            panel,
            mqtt,
            settings=settings,
            command_topic=command_topic,
            alarm_state=alarm_state,
            zone_count=12,
            ready_state=ready_state,
            ready_command_topics=ready_topics,
        )
    )
    await mqtt.push_inbound(command_topic, "DISARM")
    for _ in range(50):
        if panel.set_area_disarm.await_count:
            break
        await asyncio.sleep(0.02)
    panel.set_area_disarm.assert_awaited_once()
    panel.set_area_arm.assert_not_awaited()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_ready_switch_off_while_armed_does_not_disarm() -> None:
    """Turning a ready switch off while armed must not send disarm."""
    from texecom_alarm.app import _listen_alarm_commands, _ReadyToArmState
    from texecom_alarm.mqtt.discovery import READY_OFF, alarm_command_topic, ready_command_topic

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.set_area_arm = AsyncMock()
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    settings = _command_settings()
    command_topic = alarm_command_topic("texecom")
    away_cmd = ready_command_topic("texecom", "away")
    ready_state = _ReadyToArmState()
    alarm_state = _SharedAlarmState(payload="armed_away")
    task = asyncio.create_task(
        _listen_alarm_commands(
            panel,
            mqtt,
            settings=settings,
            command_topic=command_topic,
            alarm_state=alarm_state,
            zone_count=12,
            ready_state=ready_state,
            ready_command_topics={away_cmd: "away"},
        )
    )
    await mqtt.push_inbound(away_cmd, READY_OFF)
    for _ in range(50):
        if mqtt.payloads_for("texecom/ready/away/state")[-1:] == ["OFF"]:
            break
        await asyncio.sleep(0.02)
    assert mqtt.payloads_for("texecom/ready/away/state")[-1] == "OFF"
    assert ready_state.away is False
    panel.set_area_disarm.assert_not_awaited()
    panel.set_area_arm.assert_not_awaited()
    assert alarm_state.payload == "armed_away"
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
