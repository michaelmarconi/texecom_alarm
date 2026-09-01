"""E2E-shaped tests against a mocked panel — never the live household panel."""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import aiomqtt
import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm import healthcheck
from texecom_alarm.app import run
from texecom_alarm.config import Settings
from texecom_alarm.mqtt.discovery import AVAILABILITY_OFFLINE, AVAILABILITY_ONLINE
from texecom_alarm.mqtt.publisher import AiomqttPublisher
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.protocol.frame import (
    CMD_GET_AREA_FLAGS,
    CMD_GET_ZONE_STATE,
    CMD_LOGIN,
    CMD_SET_AREA_ARM,
    CMD_SETEVENTMESSAGES,
)

_MOSQUITTO_IMAGE = "eclipse-mosquitto:2"


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
        part_arm_1="night",
        part_arm_2="home",
        part_arm_3="unused",
    )


class _MosquittoBroker:
    """Ephemeral Mosquitto via Docker — closer to HA's broker than a pure-Python double."""

    def __init__(self) -> None:
        if shutil.which("docker") is None:
            pytest.skip("docker required for Mosquitto E2E broker")
        self.port = _free_port()
        self._tmpdir = Path(tempfile.mkdtemp(prefix="texecom-mosquitto-"))
        conf = self._tmpdir / "mosquitto.conf"
        conf.write_text("listener 1883\nallow_anonymous true\n", encoding="utf-8")
        self._container_id: str | None = None

    def start(self) -> None:
        result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "-p",
                f"127.0.0.1:{self.port}:1883",
                "-v",
                f"{self._tmpdir / 'mosquitto.conf'}:/mosquitto/config/mosquitto.conf:ro",
                _MOSQUITTO_IMAGE,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self._container_id = result.stdout.strip()

    def stop(self) -> None:
        if self._container_id:
            subprocess.run(
                ["docker", "stop", self._container_id],
                check=False,
                capture_output=True,
                text=True,
            )
            self._container_id = None
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def wait_ready(self, timeout: float = 10.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    pass
            except OSError:
                await asyncio.sleep(0.05)
                continue
            # TCP can accept before the broker completes MQTT handshake (Docker
            # port publish race). Probe with a short CONNECT/CONNACK exchange.
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", self.port),
                    timeout=0.5,
                )
                try:
                    # MQTT 3.1.1 CONNECT: empty client id, clean session.
                    writer.write(b"\x10\x0c\x00\x04MQTT\x04\x02\x00\x3c\x00\x00")
                    await writer.drain()
                    connack = await asyncio.wait_for(reader.readexactly(4), timeout=0.5)
                    if connack[:2] == b"\x20\x02":
                        return
                finally:
                    writer.close()
                    await writer.wait_closed()
            except (OSError, TimeoutError, asyncio.IncompleteReadError):
                await asyncio.sleep(0.05)
        raise TimeoutError(f"Mosquitto not accepting connections on {self.port}")


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


@pytest.mark.asyncio
async def test_e2e_discovery_retained_and_lwt_on_app_stop() -> None:
    """FakePanel + Mosquitto: retained discovery; LWT offline when app drops."""
    await _e2e_discovery_retained_and_lwt()


async def _e2e_discovery_retained_and_lwt() -> None:
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="FRONT DOOR"),
            FakeZone(number=2, zone_type=0, name=""),
            FakeZone(number=3, zone_type=3, name="KITCHEN PIR"),
        ],
        zone_count=12,
    )
    await panel.start()

    broker = _MosquittoBroker()
    broker.start()
    try:
        await broker.wait_ready()

        settings = _settings(panel, broker.port)
        stop = asyncio.Event()
        mqtt = AiomqttPublisher(
            "127.0.0.1",
            broker.port,
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

        discovered: dict[str, dict] = {}
        status_payloads: list[str] = []

        async with aiomqtt.Client(
            hostname="127.0.0.1",
            port=broker.port,
            identifier="texecom-alarm-e2e-observer",
            timeout=20.0,
        ) as observer:
            await observer.subscribe("homeassistant/binary_sensor/+/config")
            await observer.subscribe("homeassistant/alarm_control_panel/+/config")
            await observer.subscribe("texecom/status")
            await observer.subscribe("texecom/panel_connection/state")

            app_task = asyncio.create_task(
                run(settings, panel=panel_client, mqtt=mqtt, idle=stop.wait)
            )
            try:
                deadline = asyncio.get_running_loop().time() + 15.0
                alarm_cfg = "homeassistant/alarm_control_panel/texecom_alarm_arm_status/config"
                link_cfg = "homeassistant/binary_sensor/texecom_alarm_panel_connection/config"
                link_states: list[str] = []
                while asyncio.get_running_loop().time() < deadline and not (
                    len(discovered) >= 4
                    and alarm_cfg in discovered
                    and link_cfg in discovered
                    and AVAILABILITY_ONLINE in status_payloads
                    and "ON" in link_states
                ):
                    if app_task.done():
                        exc = app_task.exception()
                        if exc is not None:
                            raise exc
                    try:
                        message = await asyncio.wait_for(observer.messages.__anext__(), timeout=0.4)
                    except TimeoutError:
                        continue
                    topic = str(message.topic)
                    payload = message.payload.decode("utf-8")
                    if topic.startswith("homeassistant/"):
                        discovered[topic] = json.loads(payload)
                    elif topic == "texecom/status":
                        status_payloads.append(payload)
                    elif topic == "texecom/panel_connection/state":
                        link_states.append(payload)

                assert (
                    "homeassistant/binary_sensor/texecom_alarm_front_door_zone_1/config"
                    in discovered
                )
                assert (
                    "homeassistant/binary_sensor/texecom_alarm_kitchen_pir_zone_3/config"
                    in discovered
                )
                assert alarm_cfg in discovered
                assert link_cfg in discovered
                assert AVAILABILITY_ONLINE in status_payloads
                assert link_states and link_states[-1] == "ON"

                front = discovered[
                    "homeassistant/binary_sensor/texecom_alarm_front_door_zone_1/config"
                ]
                assert front["availability_topic"] == "texecom/status"
                assert front["unique_id"] == "texecom_alarm_zone_1"
                assert front["default_entity_id"] == (
                    "binary_sensor.texecom_alarm_front_door_zone_1"
                )
                assert front["name"] == "Front Door"
                assert "_zone_" not in str(front["name"])
                assert front["device"]["identifiers"] == ["texecom_alarm"]

                link = discovered[link_cfg]
                assert link["availability_topic"] == "texecom/status"
                assert link["name"] == "Alarm Panel Connection"
                assert link["unique_id"] == "texecom_alarm_panel_connection"
                assert link["device_class"] == "connectivity"
                assert link["state_topic"] == "texecom/panel_connection/state"
                assert link["device"]["identifiers"] == ["texecom_alarm"]
                assert link["device"] == front["device"]

                # Late subscriber must still receive retained discovery + panel-link state.
                async with aiomqtt.Client(
                    hostname="127.0.0.1",
                    port=broker.port,
                    identifier="texecom-alarm-e2e-late",
                    timeout=20.0,
                ) as late:
                    await late.subscribe(link_cfg)
                    await late.subscribe("texecom/panel_connection/state")
                    got_cfg: dict | None = None
                    got_state: str | None = None
                    late_deadline = asyncio.get_running_loop().time() + 5.0
                    while asyncio.get_running_loop().time() < late_deadline and (
                        got_cfg is None or got_state is None
                    ):
                        try:
                            message = await asyncio.wait_for(late.messages.__anext__(), timeout=0.4)
                        except TimeoutError:
                            continue
                        topic = str(message.topic)
                        payload = message.payload.decode("utf-8")
                        if topic == link_cfg:
                            got_cfg = json.loads(payload)
                        elif topic == "texecom/panel_connection/state":
                            got_state = payload
                    assert (
                        got_cfg is not None
                    ), "panel_connection discovery was not retained on broker"
                    assert got_cfg["device_class"] == "connectivity"
                    assert got_state == "ON", "panel_connection state was not retained ON on broker"

                # Simulate app-process crash: abort MQTT TCP without DISCONNECT → LWT.
                await mqtt.abort()

                lwt_seen = False
                deadline = asyncio.get_running_loop().time() + 15.0
                while asyncio.get_running_loop().time() < deadline and not lwt_seen:
                    try:
                        message = await asyncio.wait_for(observer.messages.__anext__(), timeout=0.5)
                    except TimeoutError:
                        continue
                    topic = str(message.topic)
                    payload = message.payload.decode("utf-8")
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
    finally:
        broker.stop()
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
        zone_count=12,
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
        assert "homeassistant/binary_sensor/texecom_alarm_front_door_zone_1/config" in topics
        assert "homeassistant/alarm_control_panel/texecom_alarm_arm_status/config" in topics
        link_cfg = "homeassistant/binary_sensor/texecom_alarm_panel_connection/config"
        assert link_cfg in topics
        assert "texecom/panel_connection/state" in topics
        assert mqtt.payloads_for("texecom/panel_connection/state")[0] == "ON"
        # TASK-10 AC-1/AC-2/AC-3: discovery + panel-link state must be retained.
        link_disc = next(m for m in mqtt.messages if m.topic == link_cfg)
        assert link_disc.retain is True
        link_state = next(m for m in mqtt.messages if m.topic == "texecom/panel_connection/state")
        assert link_state.retain is True
        assert link_state.payload == "ON"
        assert "texecom/status" in topics
        assert mqtt.will_payload == AVAILABILITY_OFFLINE
        assert mqtt.payloads_for("texecom/status")[-1] == AVAILABILITY_OFFLINE
        # ADR-004: zone/alarm availability stays on app LWT, not panel-link.
        zone_disc = next(
            m
            for m in mqtt.messages
            if m.topic == "homeassistant/binary_sensor/texecom_alarm_front_door_zone_1/config"
        )
        zone_payload = json.loads(
            zone_disc.payload if isinstance(zone_disc.payload, str) else zone_disc.payload.decode()
        )
        assert zone_payload["availability_topic"] == "texecom/status"
        assert zone_payload["availability_topic"] != "texecom/panel_connection/state"
        assert zone_payload["unique_id"] == "texecom_alarm_zone_1"
        assert zone_payload["default_entity_id"] == (
            "binary_sensor.texecom_alarm_front_door_zone_1"
        )
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_zone_state_snapshot_and_live_push() -> None:
    """Zone snapshot MQTT state, live ZONE push, no arm/omit cmds."""
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00),
            FakeZone(number=2, zone_type=0, name="", status=0x01),
            FakeZone(number=3, zone_type=3, name="KITCHEN PIR", status=0x01),
        ],
        zone_count=12,
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
        for _ in range(100):
            if mqtt.payloads_for("texecom/zone/1/state") and mqtt.payloads_for(
                "texecom/zone/3/state"
            ):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        assert mqtt.payloads_for("texecom/zone/1/state")[-1] == "0"
        assert mqtt.payloads_for("texecom/zone/3/state")[-1] == "1"
        assert mqtt.payloads_for("texecom/zone/2/state") == []
        forbidden = {4, 5, 6, 8, 9}
        assert forbidden.isdisjoint(panel.commands_seen)

        await panel.inject_zone_message(zone_number=1, status=0x01)
        for _ in range(100):
            payloads = mqtt.payloads_for("texecom/zone/1/state")
            if payloads and payloads[-1] == "1":
                break
            await asyncio.sleep(0.02)

        assert mqtt.payloads_for("texecom/zone/1/state")[-1] == "1"

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_alarm_snapshot_live_area_and_discovery() -> None:
    """TASK-6 AC-1/AC-2/AC-3: area-flags snapshot, AREA push, alarm discovery."""
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00),
            FakeZone(number=2, zone_type=0, name=""),
        ],
        zone_count=12,
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
        for _ in range(150):
            if mqtt.payloads_for("texecom/alarm/state") and any(
                m.topic.startswith("homeassistant/alarm_control_panel/") for m in mqtt.messages
            ):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        # AC-1: quiet panel → retained disarmed; GetAreaFlags used; no arm/omit.
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"
        assert 11 in panel.commands_seen  # CMD_GET_AREA_FLAGS
        forbidden = {4, 5, 6, 8, 9}
        assert forbidden.isdisjoint(panel.commands_seen)

        # AC-3: discovery payload shape + shared availability (not panel-link).
        disc_topic = "homeassistant/alarm_control_panel/texecom_alarm_arm_status/config"
        disc_msgs = [m for m in mqtt.messages if m.topic == disc_topic]
        assert disc_msgs
        assert disc_msgs[0].retain is True
        payload = json.loads(
            disc_msgs[0].payload
            if isinstance(disc_msgs[0].payload, str)
            else disc_msgs[0].payload.decode()
        )
        assert payload["unique_id"] == "texecom_alarm_arm_status"
        assert payload["object_id"] == "texecom_alarm_arm_status"
        assert payload["default_entity_id"] == "alarm_control_panel.texecom_alarm_arm_status"
        assert payload["name"] == "Texecom Alarm"
        assert payload["device"]["identifiers"] == ["texecom_alarm"]
        assert payload["availability_topic"] == "texecom/status"
        assert payload["json_attributes_topic"] == "texecom/alarm/attributes"
        assert payload["supported_features"] == ["arm_home", "arm_night", "arm_away"]
        assert payload["command_topic"] == "texecom/alarm/command"

        # AC-2: injected AREA push updates state (0/3/5 at minimum).
        await panel.inject_area_message(area_number=1, state=3)
        for _ in range(100):
            if mqtt.payloads_for("texecom/alarm/state")[-1] == "armed_away":
                break
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "armed_away"

        await panel.inject_area_message(area_number=1, state=5)
        for _ in range(100):
            if mqtt.payloads_for("texecom/alarm/state")[-1] == "triggered":
                break
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "triggered"

        await panel.inject_area_message(area_number=1, state=0)
        for _ in range(100):
            if mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed":
                break
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_trigger_snapshot_attributes_retained_across_disarm() -> None:
    """TASK-8 AC-1/AC-3: ZONE Active then AREA in-alarm → retained attributes; disarm keeps them."""
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00),
            FakeZone(number=2, zone_type=0, name=""),
        ],
        zone_count=12,
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
        for _ in range(150):
            if mqtt.payloads_for("texecom/alarm/state"):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        await panel.inject_zone_message(zone_number=1, status=0x01)
        for _ in range(100):
            if mqtt.payloads_for("texecom/zone/1/state")[-1:] == ["1"]:
                break
            await asyncio.sleep(0.02)

        await panel.inject_area_message(area_number=1, state=5)
        for _ in range(100):
            if mqtt.payloads_for("texecom/alarm/attributes"):
                break
            await asyncio.sleep(0.02)

        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "triggered"
        attr_msgs = [m for m in mqtt.messages if m.topic == "texecom/alarm/attributes"]
        assert attr_msgs
        assert attr_msgs[-1].retain is True
        attrs = json.loads(
            attr_msgs[-1].payload
            if isinstance(attr_msgs[-1].payload, str)
            else attr_msgs[-1].payload.decode()
        )
        assert attrs["last_trigger_zone"] == 1
        assert isinstance(attrs["last_trigger_time"], str)
        assert "T" in attrs["last_trigger_time"]
        attrs_payload = mqtt.payloads_for("texecom/alarm/attributes")[-1]

        await panel.inject_area_message(area_number=1, state=0)
        for _ in range(100):
            if mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed":
                break
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"
        assert mqtt.payloads_for("texecom/alarm/attributes")[-1] == attrs_payload

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_mqtt_arm_disarm_commands() -> None:
    """TASK-7 AC-1/AC-2/AC-3: MQTT ARM_*/DISARM → FakePanel cmd 6/8 bodies."""
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00),
            FakeZone(number=2, zone_type=0, name=""),
        ],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = Settings(
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
        for _ in range(150):
            if "texecom/alarm/command" in mqtt.subscribed:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert "texecom/alarm/command" in mqtt.subscribed

        async def _wait_arm(mode: int) -> None:
            for _ in range(100):
                if panel.last_arm_mode == mode and panel.last_arm_body == bytes([mode, 0x01]):
                    return
                if task.done():
                    exc = task.exception()
                    if exc is not None:
                        raise exc
                await asyncio.sleep(0.02)
            raise AssertionError(f"expected arm mode {mode}, got {panel.last_arm_mode!r}")

        await mqtt.push_inbound("texecom/alarm/command", "ARM_AWAY")
        await _wait_arm(0)

        await mqtt.push_inbound("texecom/alarm/command", "ARM_NIGHT")
        await _wait_arm(1)

        await mqtt.push_inbound("texecom/alarm/command", "ARM_HOME")
        await _wait_arm(2)
        # Arm while MQTT is still disarmed still asks for flags. Wait for that
        # in-flight read so the unknown-command no-op check is stable.
        for _ in range(100):
            if panel.commands_seen and panel.commands_seen[-1] == CMD_GET_AREA_FLAGS:
                break
            await asyncio.sleep(0.02)

        before_cmds = list(panel.commands_seen)
        await mqtt.push_inbound("texecom/alarm/command", "NOT_A_COMMAND")
        await asyncio.sleep(0.1)
        assert panel.commands_seen == before_cmds

        disarm_before = panel.disarm_calls
        await mqtt.push_inbound("texecom/alarm/command", "DISARM")
        for _ in range(100):
            if panel.disarm_calls > disarm_before:
                break
            await asyncio.sleep(0.02)
        assert panel.disarm_calls == disarm_before + 1
        assert panel.last_disarm_body == bytes([0x01])

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_arm_omits_flags_when_live_area_already_published() -> None:
    """After ACK, FakePanel must not see GetAreaFlags when AREA already published armed."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00)],
        zone_count=12,
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
        for _ in range(150):
            if "texecom/alarm/command" in mqtt.subscribed and mqtt.payloads_for(
                "texecom/alarm/state"
            ):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert "texecom/alarm/command" in mqtt.subscribed

        await panel.inject_area_message(area_number=1, state=3)
        for _ in range(100):
            if mqtt.payloads_for("texecom/alarm/state")[-1] == "armed_away":
                break
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "armed_away"

        flags_before = panel.area_flags_calls
        await mqtt.push_inbound("texecom/alarm/command", "ARM_AWAY")
        for _ in range(100):
            if panel.last_arm_mode == 0:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert panel.last_arm_mode == 0
        await asyncio.sleep(0.15)
        assert panel.area_flags_calls == flags_before

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_post_ack_unparseable_flags_is_collision_not_failed_tap() -> None:
    """ACK then unreadable GetAreaFlags: not a failed arm; Connection stays on
    if the first re-login succeeds; zone and alarm state are re-read.
    """
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = Settings(
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
            reconnect_delay_seconds=0.01,
        )
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

        task = asyncio.create_task(
            run(
                settings,
                panel=client,
                mqtt=mqtt,
                idle=stop.wait,
                idle_timeout=0.2,
                trust_poll_interval=60.0,
            )
        )
        for _ in range(150):
            if (
                mqtt.payloads_for("texecom/panel_connection/state")[-1:] == ["ON"]
                and "texecom/alarm/command" in mqtt.subscribed
            ):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
        before_status = list(mqtt.payloads_for("texecom/status"))
        zone_before = mqtt.payloads_for("texecom/zone/1/state")[-1]
        alarm_before = mqtt.payloads_for("texecom/alarm/state")[-1]
        cmds_before = list(panel.commands_seen)
        login_before = panel.commands_seen.count(CMD_LOGIN)
        setevent_before = panel.seteventmessages_calls

        panel.garbage_next_area_flags = True
        await mqtt.push_inbound("texecom/alarm/command", "ARM_AWAY")
        for _ in range(300):
            resumed = (
                panel.commands_seen.count(CMD_LOGIN) > login_before
                and panel.seteventmessages_calls > setevent_before
                and CMD_GET_ZONE_STATE in panel.commands_seen[len(cmds_before) :]
                and CMD_GET_AREA_FLAGS in panel.commands_seen[len(cmds_before) :]
            )
            if resumed:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        assert task.done() is False
        link = mqtt.payloads_for("texecom/panel_connection/state")
        assert "OFF" not in link
        assert link[-1] == "ON"
        assert panel.arm_calls == [0]
        assert panel.commands_seen.count(CMD_SET_AREA_ARM) == 1
        new_cmds = panel.commands_seen[len(cmds_before) :]
        assert CMD_LOGIN in new_cmds
        assert CMD_GET_ZONE_STATE in new_cmds
        assert CMD_GET_AREA_FLAGS in new_cmds
        assert CMD_SETEVENTMESSAGES in new_cmds
        assert mqtt.payloads_for("texecom/status") == before_status or (
            mqtt.payloads_for("texecom/status")[-1] == AVAILABILITY_ONLINE
        )
        assert "offline" not in mqtt.payloads_for("texecom/status")[len(before_status) :]
        assert mqtt.payloads_for("texecom/zone/1/state")[-1] == zone_before
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == alarm_before

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_arm_nak_still_turns_connection_off_immediately() -> None:
    """A refused arm still turns Connection off at once and is not re-issued."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = Settings(
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
            reconnect_delay_seconds=0.01,
        )
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

        task = asyncio.create_task(
            run(
                settings,
                panel=client,
                mqtt=mqtt,
                idle=stop.wait,
                idle_timeout=0.2,
                trust_poll_interval=60.0,
            )
        )
        for _ in range(150):
            if (
                mqtt.payloads_for("texecom/panel_connection/state")[-1:] == ["ON"]
                and "texecom/alarm/command" in mqtt.subscribed
            ):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
        before_status = list(mqtt.payloads_for("texecom/status"))

        panel.nak_next_arm = True
        await mqtt.push_inbound("texecom/alarm/command", "ARM_AWAY")
        for _ in range(100):
            if mqtt.payloads_for("texecom/panel_connection/state")[-1:] == ["OFF"]:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
        assert panel.arm_calls == [0]
        assert panel.commands_seen.count(CMD_SET_AREA_ARM) == 1
        assert mqtt.payloads_for("texecom/status") == before_status or (
            mqtt.payloads_for("texecom/status")[-1] == AVAILABILITY_ONLINE
        )
        await asyncio.sleep(0.15)
        assert panel.arm_calls == [0]
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_home_disarm_without_area_still_reads_flags() -> None:
    """Home disarm that omits AREA still runs GetAreaFlags and publishes disarmed."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00)],
        zone_count=12,
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
        for _ in range(150):
            if "texecom/alarm/command" in mqtt.subscribed and mqtt.payloads_for(
                "texecom/alarm/state"
            ):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert "texecom/alarm/command" in mqtt.subscribed

        await panel.inject_area_message(area_number=1, state=7)
        for _ in range(100):
            if mqtt.payloads_for("texecom/alarm/state")[-1] == "armed_home":
                break
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "armed_home"

        flags_before = panel.area_flags_calls
        await mqtt.push_inbound("texecom/alarm/command", "DISARM")
        for _ in range(100):
            if (
                panel.disarm_calls >= 1
                and panel.area_flags_calls > flags_before
                and mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"
            ):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert panel.disarm_calls >= 1
        assert panel.area_flags_calls > flags_before
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_mqtt_arm_uses_remapped_part_arm_slots() -> None:
    """AC-3: changing Part-Arm slot → HA mode changes the mode byte without code change."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = Settings(
            panel_host=panel.host,
            panel_port=panel.port,
            udl_password="1234",
            mqtt_host="127.0.0.1",
            mqtt_port=1883,
            mqtt_username="",
            mqtt_password="",
            mqtt_topic_prefix="texecom",
            part_arm_1="home",
            part_arm_2="unused",
            part_arm_3="night",
        )
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
        for _ in range(150):
            if "texecom/alarm/command" in mqtt.subscribed:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        await mqtt.push_inbound("texecom/alarm/command", "ARM_HOME")
        for _ in range(100):
            if panel.last_arm_body == bytes([0x01, 0x01]):
                break
            await asyncio.sleep(0.02)
        assert panel.last_arm_body == bytes([0x01, 0x01])

        await mqtt.push_inbound("texecom/alarm/command", "ARM_AWAY")
        for _ in range(100):
            if panel.last_arm_body == bytes([0x00, 0x01]):
                break
            await asyncio.sleep(0.02)
        assert panel.last_arm_body == bytes([0x00, 0x01])

        await mqtt.push_inbound("texecom/alarm/command", "ARM_NIGHT")
        for _ in range(100):
            if panel.last_arm_body == bytes([0x03, 0x01]):
                break
            await asyncio.sleep(0.02)
        assert panel.last_arm_body == bytes([0x03, 0x01])

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_arm_nak_republishes_disarmed_state() -> None:
    """AC-1: FakePanel NAK of ARM_HOME republishes retained disarmed (no stuck selection)."""
    panel = FakePanel(
        udl_password="1234",
        zones=[
            FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00),
            FakeZone(number=2, zone_type=0, name=""),
        ],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = Settings(
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
        for _ in range(150):
            states = mqtt.payloads_for("texecom/alarm/state")
            if states and "texecom/alarm/command" in mqtt.subscribed:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"
        before = len(mqtt.payloads_for("texecom/alarm/state"))

        panel.nak_next_arm = True
        await mqtt.push_inbound("texecom/alarm/command", "ARM_HOME")
        for _ in range(100):
            if panel.last_arm_mode == 2 and len(mqtt.payloads_for("texecom/alarm/state")) > before:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        assert panel.last_arm_mode == 2
        assert panel.last_arm_body == bytes([0x02, 0x01])
        states = mqtt.payloads_for("texecom/alarm/state")
        assert len(states) > before
        assert states[-1] == "disarmed"

        # AC-2: subsequent successful ARM_HOME still uses Home mode byte 2.
        await mqtt.push_inbound("texecom/alarm/command", "ARM_HOME")
        for _ in range(100):
            if len(panel.arm_calls) >= 2 and panel.arm_calls[-1] == 2:
                break
            await asyncio.sleep(0.02)
        assert panel.arm_calls[-1] == 2
        assert panel.last_arm_body == bytes([0x02, 0x01])

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_quiet_house_panel_link_stays_on() -> None:
    """ADR-016 / AC2: no zone pushes alone must not degrade Alarm Panel Connection."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = Settings(
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

        task = asyncio.create_task(
            run(
                settings,
                panel=client,
                mqtt=mqtt,
                idle=stop.wait,
                idle_timeout=0.05,
                trust_poll_interval=0.08,
                trust_recover_window=0.05,
            )
        )
        for _ in range(150):
            if mqtt.payloads_for("texecom/panel_connection/state"):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"

        # Check-ins fire on their own fixed schedule (idle_timeout above,
        # ADR-020), independent of the reconciliation poll interval below.
        for _ in range(50):
            if panel.area_flags_calls >= 2 and panel.keepalive_attempts >= 1:
                break
            await asyncio.sleep(0.02)

        assert panel.area_flags_calls >= 2
        assert panel.keepalive_attempts >= 1
        assert "OFF" not in mqtt.payloads_for("texecom/panel_connection/state")
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_arm_nak_degrades_panel_link_keepalive_still_ok() -> None:
    """ADR-016 / AC1: FakePanel arm NAK → panel_connection OFF; app availability stays online."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = Settings(
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

        task = asyncio.create_task(
            run(
                settings,
                panel=client,
                mqtt=mqtt,
                idle=stop.wait,
                trust_poll_interval=60.0,
            )
        )
        for _ in range(150):
            if (
                mqtt.payloads_for("texecom/panel_connection/state")
                and "texecom/alarm/command" in mqtt.subscribed
            ):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        before_status = list(mqtt.payloads_for("texecom/status"))
        panel.nak_next_arm = True
        await mqtt.push_inbound("texecom/alarm/command", "ARM_HOME")
        for _ in range(100):
            if mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF":
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
        assert mqtt.payloads_for("texecom/status") == before_status
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_health_check_death_heals_without_restart() -> None:
    """ADR-011 / session-heal AC1: unanswered keepalive → reconnect heal + re-sync."""
    from texecom_alarm.protocol.frame import (
        CMD_GET_ZONE_STATE,
        CMD_LOGIN,
        CMD_SETEVENTMESSAGES,
    )

    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = Settings(
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
            reconnect_delay_seconds=0.01,
        )
        stop = asyncio.Event()
        client = PanelClient(
            panel.host,
            panel.port,
            udl_password="1234",
            login_delay=0.0,
            response_timeout=0.2,
            login_retries=0,
        )
        await client.connect()
        await client.login()

        task = asyncio.create_task(
            run(
                settings,
                panel=client,
                mqtt=mqtt,
                idle=stop.wait,
                idle_timeout=0.05,
                trust_poll_interval=60.0,
                # Fast patience (ADR-020) so a silenced keepalive still declares
                # the session dead well within this test's wait budget.
                trust_checkin_patience=0.15,
            )
        )
        for _ in range(150):
            if mqtt.payloads_for("texecom/panel_connection/state")[-1:] == ["ON"]:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
        before_status = list(mqtt.payloads_for("texecom/status"))
        zone_before = mqtt.payloads_for("texecom/zone/1/state")[-1]
        alarm_before = mqtt.payloads_for("texecom/alarm/state")[-1]
        cmds_before = list(panel.commands_seen)
        setevent_before = panel.seteventmessages_calls

        panel.silence_keepalive = True

        for _ in range(300):
            link = mqtt.payloads_for("texecom/panel_connection/state")
            resumed = (
                link.count("OFF") >= 1
                and link[-1] == "ON"
                and panel.seteventmessages_calls > setevent_before
            )
            if resumed:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        link = mqtt.payloads_for("texecom/panel_connection/state")
        assert "OFF" in link
        assert link[-1] == "ON"
        assert mqtt.payloads_for("texecom/status") == before_status or (
            mqtt.payloads_for("texecom/status")[-1] == AVAILABILITY_ONLINE
        )
        assert "offline" not in mqtt.payloads_for("texecom/status")[len(before_status) :]
        assert mqtt.payloads_for("texecom/zone/1/state")[-1] == zone_before
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == alarm_before
        new_cmds = panel.commands_seen[len(cmds_before) :]
        assert CMD_LOGIN in new_cmds
        assert CMD_GET_ZONE_STATE in new_cmds
        assert CMD_GET_AREA_FLAGS in new_cmds
        assert CMD_SETEVENTMESSAGES in new_cmds

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_stuck_trust_fail_window_relogins_without_arm_retry() -> None:
    """ADR-011 AC2/AC3: stuck trust past fail window → re-login; no arm auto-retry.

    Recover window is deliberately longer than the fail window so the single
    failed arm cannot self-heal via a resumed keepalive before the stuck path
    fires — the reconciliation poll no longer has any bearing on this (ADR-016).
    """
    from texecom_alarm.protocol.frame import (
        CMD_GET_ZONE_STATE,
        CMD_LOGIN,
        CMD_SET_AREA_ARM,
        CMD_SETEVENTMESSAGES,
    )

    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = Settings(
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
            reconnect_delay_seconds=0.01,
        )
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

        task = asyncio.create_task(
            run(
                settings,
                panel=client,
                mqtt=mqtt,
                idle=stop.wait,
                idle_timeout=0.05,
                trust_poll_interval=0.05,
                trust_recover_window=5.0,
                trust_fail_window=0.25,
            )
        )
        for _ in range(150):
            if (
                mqtt.payloads_for("texecom/panel_connection/state")[-1:] == ["ON"]
                and "texecom/alarm/command" in mqtt.subscribed
            ):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
        before_status = list(mqtt.payloads_for("texecom/status"))
        zone_before = mqtt.payloads_for("texecom/zone/1/state")[-1]
        alarm_before = mqtt.payloads_for("texecom/alarm/state")[-1]
        cmds_before = list(panel.commands_seen)
        setevent_before = panel.seteventmessages_calls

        panel.nak_next_arm = True
        await mqtt.push_inbound("texecom/alarm/command", "ARM_AWAY")
        for _ in range(100):
            if mqtt.payloads_for("texecom/panel_connection/state")[-1:] == ["OFF"]:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
        arm_calls_after_fail = list(panel.arm_calls)
        assert len(arm_calls_after_fail) == 1

        for _ in range(400):
            link = mqtt.payloads_for("texecom/panel_connection/state")
            resumed = (
                link.count("OFF") >= 1
                and link[-1] == "ON"
                and panel.seteventmessages_calls > setevent_before
                and panel.commands_seen.count(CMD_LOGIN) >= 2
            )
            if resumed:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        link = mqtt.payloads_for("texecom/panel_connection/state")
        assert "OFF" in link
        assert link[-1] == "ON"
        assert panel.arm_calls == arm_calls_after_fail
        assert panel.commands_seen.count(CMD_SET_AREA_ARM) == 1
        assert mqtt.payloads_for("texecom/status") == before_status or (
            mqtt.payloads_for("texecom/status")[-1] == AVAILABILITY_ONLINE
        )
        assert "offline" not in mqtt.payloads_for("texecom/status")[len(before_status) :]
        assert mqtt.payloads_for("texecom/zone/1/state")[-1] == zone_before
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == alarm_before
        new_cmds = panel.commands_seen[len(cmds_before) :]
        assert CMD_LOGIN in new_cmds
        assert CMD_GET_ZONE_STATE in new_cmds
        assert CMD_GET_AREA_FLAGS in new_cmds
        assert CMD_SETEVENTMESSAGES in new_cmds

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_ready_to_arm_switches_start_on_and_round_trip() -> None:
    """TASK-30 AC-1/AC-2/AC-3: three ready switches start ON; command/state round-trip."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR")],
        zone_count=12,
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
        command_topics = (
            "texecom/ready/away/command",
            "texecom/ready/home/command",
            "texecom/ready/night/command",
        )
        for _ in range(150):
            topics = [m.topic for m in mqtt.messages]
            if all(
                f"homeassistant/switch/texecom_alarm_ready_{mode}/config" in topics
                for mode in ("away", "home", "night")
            ) and all(t in mqtt.subscribed for t in command_topics):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        for mode, object_id, name in (
            ("away", "texecom_alarm_ready_away", "Ready to arm Away"),
            ("home", "texecom_alarm_ready_home", "Ready to arm Home"),
            ("night", "texecom_alarm_ready_night", "Ready to arm Night"),
        ):
            cfg_topic = f"homeassistant/switch/{object_id}/config"
            cfgs = [m for m in mqtt.messages if m.topic == cfg_topic]
            assert cfgs, f"missing discovery for {mode}"
            assert cfgs[0].retain is True
            payload = json.loads(
                cfgs[0].payload if isinstance(cfgs[0].payload, str) else cfgs[0].payload.decode()
            )
            assert payload["name"] == name
            assert payload["unique_id"] == object_id
            assert payload["object_id"] == object_id
            assert payload["default_entity_id"] == f"switch.{object_id}"
            assert payload["state_topic"] == f"texecom/ready/{mode}/state"
            assert payload["command_topic"] == f"texecom/ready/{mode}/command"
            assert payload["payload_on"] == "ON"
            assert payload["payload_off"] == "OFF"
            assert payload["device"]["identifiers"] == ["texecom_alarm"]
            states = [m for m in mqtt.messages if m.topic == f"texecom/ready/{mode}/state"]
            assert states
            assert states[0].retain is True
            assert states[0].payload == "ON"
            assert f"texecom/ready/{mode}/command" in mqtt.subscribed

        # Command/state round-trip: OFF then ON, retained, so later arm can read current on/off.
        await mqtt.push_inbound("texecom/ready/away/command", "OFF")
        for _ in range(50):
            away_states = mqtt.payloads_for("texecom/ready/away/state")
            if away_states and away_states[-1] == "OFF":
                break
            await asyncio.sleep(0.02)
        away_msgs = [m for m in mqtt.messages if m.topic == "texecom/ready/away/state"]
        assert away_msgs[-1].payload == "OFF"
        assert away_msgs[-1].retain is True
        # Home/Night stay on — only the commanded switch changes.
        assert mqtt.payloads_for("texecom/ready/home/state")[-1] == "ON"
        assert mqtt.payloads_for("texecom/ready/night/state")[-1] == "ON"

        await mqtt.push_inbound("texecom/ready/away/command", "ON")
        for _ in range(50):
            if mqtt.payloads_for("texecom/ready/away/state")[-1] == "ON":
                break
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/ready/away/state")[-1] == "ON"
        away_after_on = [m for m in mqtt.messages if m.topic == "texecom/ready/away/state"]
        assert away_after_on[-1].retain is True

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


async def _boot_e2e_app(
    panel: FakePanel,
) -> tuple[RecordingMqttPublisher, asyncio.Task[None], asyncio.Event]:
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
    for _ in range(150):
        if "texecom/alarm/command" in mqtt.subscribed:
            break
        if task.done():
            exc = task.exception()
            if exc is not None:
                raise exc
        await asyncio.sleep(0.02)
    assert "texecom/alarm/command" in mqtt.subscribed
    return mqtt, task, stop


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "arm_payload"),
    [
        ("away", "ARM_AWAY"),
        ("home", "ARM_HOME"),
        ("night", "ARM_NIGHT"),
    ],
)
async def test_e2e_unready_arm_skips_panel_and_publishes_blocked_event(
    mode: str, arm_payload: str
) -> None:
    """Matching ready switch OFF: no panel arm; MQTT arming then current; event names mode."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR")],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt, task, stop = await _boot_e2e_app(panel)
        cfg_topic = "homeassistant/event/texecom_alarm_blocked_arm/config"
        for _ in range(50):
            if any(m.topic == cfg_topic for m in mqtt.messages):
                break
            await asyncio.sleep(0.02)
        cfgs = [m for m in mqtt.messages if m.topic == cfg_topic]
        assert cfgs, "blocked-arm event discovery missing"
        assert cfgs[0].retain is True
        discovery = json.loads(
            cfgs[0].payload if isinstance(cfgs[0].payload, str) else cfgs[0].payload.decode()
        )
        assert discovery["unique_id"] == "texecom_alarm_blocked_arm"
        assert discovery["object_id"] == "texecom_alarm_blocked_arm"
        assert discovery["default_entity_id"] == "event.texecom_alarm_blocked_arm"
        assert discovery["state_topic"] == "texecom/blocked_arm/event"
        assert discovery["event_types"] == ["away", "home", "night"]
        assert "reason" not in discovery
        assert discovery["device"]["identifiers"] == ["texecom_alarm"]

        await mqtt.push_inbound(f"texecom/ready/{mode}/command", "OFF")
        for _ in range(50):
            states = mqtt.payloads_for(f"texecom/ready/{mode}/state")
            if states and states[-1] == "OFF":
                break
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for(f"texecom/ready/{mode}/state")[-1] == "OFF"

        alarm_before = list(mqtt.payloads_for("texecom/alarm/state"))
        current = alarm_before[-1]
        arm_mode_before = panel.last_arm_mode
        arm_body_before = panel.last_arm_body
        await mqtt.push_inbound("texecom/alarm/command", arm_payload)
        for _ in range(50):
            alarm_after = mqtt.payloads_for("texecom/alarm/state")
            if alarm_after[len(alarm_before) :] == ["arming", current]:
                break
            if panel.last_arm_mode != arm_mode_before:
                break
            await asyncio.sleep(0.02)

        assert panel.last_arm_mode == arm_mode_before
        assert panel.last_arm_body == arm_body_before
        alarm_after = mqtt.payloads_for("texecom/alarm/state")
        assert alarm_after[len(alarm_before) :] == ["arming", current]
        events = mqtt.payloads_for("texecom/blocked_arm/event")
        assert events
        body = json.loads(events[-1])
        assert body["event_type"] == mode
        assert "reason" not in body
        event_msgs = [m for m in mqtt.messages if m.topic == "texecom/blocked_arm/event"]
        assert event_msgs[-1].retain is False

        await mqtt.push_inbound(f"texecom/ready/{mode}/command", "ON")
        for _ in range(50):
            if mqtt.payloads_for(f"texecom/ready/{mode}/state")[-1] == "ON":
                break
            await asyncio.sleep(0.02)
        await mqtt.push_inbound("texecom/alarm/command", arm_payload)
        for _ in range(100):
            if panel.last_arm_mode is not None and panel.last_arm_mode != arm_mode_before:
                break
            await asyncio.sleep(0.02)
        assert panel.last_arm_mode is not None

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_disarm_still_sent_when_all_ready_switches_off() -> None:
    """All three ready switches OFF: DISARM still reaches FakePanel."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR")],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt, task, stop = await _boot_e2e_app(panel)
        for mode in ("away", "home", "night"):
            await mqtt.push_inbound(f"texecom/ready/{mode}/command", "OFF")
        for _ in range(50):
            if all(
                mqtt.payloads_for(f"texecom/ready/{m}/state")[-1:] == ["OFF"]
                for m in ("away", "home", "night")
            ):
                break
            await asyncio.sleep(0.02)
        disarm_before = panel.disarm_calls
        await mqtt.push_inbound("texecom/alarm/command", "DISARM")
        for _ in range(100):
            if panel.disarm_calls > disarm_before:
                break
            await asyncio.sleep(0.02)
        assert panel.disarm_calls == disarm_before + 1
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_ready_switch_off_while_armed_does_not_disarm() -> None:
    """Armed, then matching ready switch OFF: FakePanel receives no disarm."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR")],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt, task, stop = await _boot_e2e_app(panel)
        await mqtt.push_inbound("texecom/alarm/command", "ARM_AWAY")
        for _ in range(100):
            if panel.last_arm_mode == 0:
                break
            await asyncio.sleep(0.02)
        assert panel.last_arm_mode == 0
        disarm_before = panel.disarm_calls
        await mqtt.push_inbound("texecom/ready/away/command", "OFF")
        for _ in range(50):
            if mqtt.payloads_for("texecom/ready/away/state")[-1:] == ["OFF"]:
                break
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/ready/away/state")[-1] == "OFF"
        await asyncio.sleep(0.1)
        assert panel.disarm_calls == disarm_before
        assert panel.last_arm_mode == 0
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()
