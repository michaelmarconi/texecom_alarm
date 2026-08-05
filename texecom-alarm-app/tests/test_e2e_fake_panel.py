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
from texecom_alarm.protocol.frame import CMD_SET_AREA_ARM, CMD_SET_AREA_DISARM

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
                    return
            except OSError:
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


def test_e2e_discovery_retained_and_lwt_on_app_stop() -> None:
    """FakePanel + Mosquitto: retained discovery; LWT offline when app drops."""
    asyncio.run(_e2e_discovery_retained_and_lwt())


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
            await observer.subscribe("texecom/panel_link/state")

            app_task = asyncio.create_task(
                run(settings, panel=panel_client, mqtt=mqtt, idle=stop.wait)
            )
            try:
                deadline = asyncio.get_running_loop().time() + 15.0
                alarm_cfg = "homeassistant/alarm_control_panel/texecom_alarm_arm_status/config"
                link_cfg = "homeassistant/binary_sensor/texecom_alarm_panel_link/config"
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
                    elif topic == "texecom/panel_link/state":
                        link_states.append(payload)

                assert "homeassistant/binary_sensor/texecom_alarm_front_door_1/config" in discovered
                assert (
                    "homeassistant/binary_sensor/texecom_alarm_kitchen_pir_3/config" in discovered
                )
                assert alarm_cfg in discovered
                assert link_cfg in discovered
                assert AVAILABILITY_ONLINE in status_payloads
                assert link_states and link_states[-1] == "ON"

                front = discovered["homeassistant/binary_sensor/texecom_alarm_front_door_1/config"]
                assert front["availability_topic"] == "texecom/status"
                assert front["unique_id"] == "texecom_alarm_front_door_1"
                assert front["default_entity_id"] == "binary_sensor.texecom_alarm_front_door_1"
                assert front["name"] == "Front Door"
                assert front["device"]["identifiers"] == ["texecom_alarm"]

                link = discovered[link_cfg]
                assert link["availability_topic"] == "texecom/status"
                assert link["device_class"] == "connectivity"
                assert link["state_topic"] == "texecom/panel_link/state"
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
                    await late.subscribe("texecom/panel_link/state")
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
                        elif topic == "texecom/panel_link/state":
                            got_state = payload
                    assert got_cfg is not None, "panel_link discovery was not retained on broker"
                    assert got_cfg["device_class"] == "connectivity"
                    assert got_state == "ON", "panel_link state was not retained ON on broker"

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
        assert "homeassistant/binary_sensor/texecom_alarm_front_door_1/config" in topics
        assert "homeassistant/alarm_control_panel/texecom_alarm_arm_status/config" in topics
        link_cfg = "homeassistant/binary_sensor/texecom_alarm_panel_link/config"
        assert link_cfg in topics
        assert "texecom/panel_link/state" in topics
        assert mqtt.payloads_for("texecom/panel_link/state")[0] == "ON"
        # TASK-10 AC-1/AC-2/AC-3: discovery + panel-link state must be retained.
        link_disc = next(m for m in mqtt.messages if m.topic == link_cfg)
        assert link_disc.retain is True
        link_state = next(m for m in mqtt.messages if m.topic == "texecom/panel_link/state")
        assert link_state.retain is True
        assert link_state.payload == "ON"
        assert "texecom/status" in topics
        assert mqtt.will_payload == AVAILABILITY_OFFLINE
        assert mqtt.payloads_for("texecom/status")[-1] == AVAILABILITY_OFFLINE
        # ADR-004: zone/alarm availability stays on app LWT, not panel-link.
        zone_disc = next(
            m
            for m in mqtt.messages
            if m.topic == "homeassistant/binary_sensor/texecom_alarm_front_door_1/config"
        )
        zone_payload = json.loads(
            zone_disc.payload if isinstance(zone_disc.payload, str) else zone_disc.payload.decode()
        )
        assert zone_payload["availability_topic"] == "texecom/status"
        assert zone_payload["availability_topic"] != "texecom/panel_link/state"
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
        assert panel.last_command == CMD_SET_AREA_ARM

        await mqtt.push_inbound("texecom/alarm/command", "ARM_NIGHT")
        await _wait_arm(1)

        await mqtt.push_inbound("texecom/alarm/command", "ARM_HOME")
        await _wait_arm(2)

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
        assert panel.last_command == CMD_SET_AREA_DISARM

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
            part_arm_2="away",
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
            if panel.last_arm_body == bytes([0x02, 0x01]):
                break
            await asyncio.sleep(0.02)
        assert panel.last_arm_body == bytes([0x02, 0x01])

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
