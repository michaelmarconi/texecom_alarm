"""Integration tests for DEBUG handling and TRACE panel-session logging (AC4–AC5)."""

from __future__ import annotations

import asyncio
import logging

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.app import _listen_panel_messages, _SharedAlarmState
from texecom_alarm.arm_commands import handle_alarm_command
from texecom_alarm.config import Settings
from texecom_alarm.logging_setup import TRACE_LEVEL, configure_logging
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.protocol.frame import MSG_LOG, MSG_OUTPUT, MSG_ZONE
from texecom_alarm.zone_state import handle_zone_message
from texecom_alarm.zones import Zone


def _settings() -> Settings:
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
        log_level="DEBUG",
    )


@pytest.fixture
def restore_root_logging() -> None:
    """Keep configure_logging from leaking level/handlers across tests."""
    root = logging.getLogger()
    before_level = root.level
    before_handlers = list(root.handlers)
    yield
    root.handlers.clear()
    for handler in before_handlers:
        root.addHandler(handler)
    root.setLevel(before_level)


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _attach_capture() -> tuple[_Capture, logging.Logger]:
    capture = _Capture()
    root = logging.getLogger()
    root.addHandler(capture)
    return capture, root


def _messages(records: list[logging.LogRecord]) -> list[str]:
    return [r.getMessage() for r in records]


def _app_records(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    """Drop FakePanel double noise — assert only production package logs."""
    return [r for r in records if r.name.startswith("texecom_alarm")]


async def _logged_in_client(panel: FakePanel) -> PanelClient:
    client = PanelClient(
        panel.host,
        panel.port,
        udl_password="1234",
        login_delay=0.0,
        response_timeout=0.5,
    )
    await client.connect()
    await client.login()
    return client


@pytest.mark.asyncio
async def test_debug_zone_change_logs_handling_without_raw_frames(
    restore_root_logging: None,
) -> None:
    """AC4: DEBUG shows zone → MQTT outcome; no raw frame dump required."""
    configure_logging("DEBUG")
    capture, root = _attach_capture()
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=1,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()

        await panel.inject_zone_message(zone_number=1, status=0x01)
        frame = await client.recv_message(timeout=1.0)
        assert frame.body[0] == MSG_ZONE
        await handle_zone_message(
            mqtt,
            frame.body,
            topic_prefix="texecom",
            in_use_zones={1},
            zones={1: Zone(number=1, zone_type=1, name="DOOR")},
        )

        app_msgs = _messages(_app_records(capture.records))
        assert any("mqtt_zone_state" in m for m in app_msgs)
        zone_msgs = [m for m in app_msgs if "mqtt_zone_state" in m]
        assert any("DOOR" in m and "Active" in m and "0x01" in m for m in zone_msgs), zone_msgs
        # Outcome path must not require dumping the raw ZONE frame body.
        joined = " ".join(app_msgs)
        assert frame.body.hex() not in joined
        assert mqtt.payloads_for("texecom/zone/1/state") == ["1"]
        await client.close()
    finally:
        root.removeHandler(capture)
        await panel.stop()


@pytest.mark.asyncio
async def test_debug_arm_disarm_logs_command_outcomes(
    restore_root_logging: None,
) -> None:
    """AC4: DEBUG shows arm/disarm command path outcomes without raw dumps."""
    configure_logging("DEBUG")
    capture, root = _attach_capture()
    panel = FakePanel(udl_password="1234")
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        settings = _settings()

        await handle_alarm_command(client, settings, "ARM_HOME")
        await handle_alarm_command(client, settings, "DISARM")

        app_msgs = _messages(_app_records(capture.records))
        arm_msgs = [m for m in app_msgs if "alarm_command_arm" in m]
        assert arm_msgs, app_msgs
        assert any(
            "home" in m and ("2" in m or "byte=2" in m or "mode=2" in m) for m in arm_msgs
        ), arm_msgs
        assert any("panel_set_area_arm_ok" in m and "2" in m for m in app_msgs), app_msgs
        assert any("alarm_command_disarm" in m for m in app_msgs)
        assert any("panel_set_area_disarm_ok" in m or "alarm_command_disarm" in m for m in app_msgs)
        assert panel.arm_calls == [2]
        assert panel.disarm_calls == 1
        await client.close()
    finally:
        root.removeHandler(capture)
        await panel.stop()


@pytest.mark.asyncio
async def test_trace_logs_panel_tx_rx_for_command_and_unsolicited(
    restore_root_logging: None,
) -> None:
    """AC5: TRACE includes panel tx/rx for commands and unsolicited frames."""
    configure_logging("TRACE")
    capture, root = _attach_capture()
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=1,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        # Clear login traffic so assertions focus on the keepalive + zone push.
        capture.records.clear()

        await client.keepalive()
        await panel.inject_zone_message(zone_number=1, status=0x01)
        await client.recv_message(timeout=1.0)

        app_recs = _app_records(capture.records)
        app_msgs = _messages(app_recs)
        tx = [m for m in app_msgs if m.startswith("panel_tx") or "panel_tx" in m]
        rx = [m for m in app_msgs if m.startswith("panel_rx") or "panel_rx" in m]
        assert tx, f"expected panel_tx lines at TRACE, got {app_msgs!r}"
        assert rx, f"expected panel_rx lines at TRACE, got {app_msgs!r}"
        assert any("GETDATETIME" in m and "seq=" in m for m in tx), tx
        assert any("seq=" in m for m in rx), rx
        assert any(r.levelno == TRACE_LEVEL for r in app_recs if "panel_tx" in r.getMessage())
        assert any(r.levelno == TRACE_LEVEL for r in app_recs if "panel_rx" in r.getMessage())
        await client.close()
    finally:
        root.removeHandler(capture)
        await panel.stop()


@pytest.mark.asyncio
async def test_trace_logs_ignored_push_subtypes(
    restore_root_logging: None,
) -> None:
    """TRACE names ignored push types (e.g. OUTPUT) with body hex for protocol hunts."""
    configure_logging("TRACE")
    capture, root = _attach_capture()
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        capture.records.clear()
        task = asyncio.create_task(
            _listen_panel_messages(
                client,
                mqtt,
                settings=_settings(),
                topic_prefix="texecom",
                in_use_zones={1},
                alarm_state=_SharedAlarmState(),
                idle_timeout=0.2,
            )
        )
        body = bytes([MSG_OUTPUT, 0x01, 0x02])
        await panel.inject_push_body(body)
        for _ in range(50):
            if any("ignored for MQTT" in r.getMessage() for r in capture.records):
                break
            await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        app_msgs = _messages(_app_records(capture.records))
        assert any("OUTPUT" in m and "ignored for MQTT" in m for m in app_msgs), app_msgs
        assert any(body.hex() in m for m in app_msgs)
        await client.close()
    finally:
        root.removeHandler(capture)
        await panel.stop()


@pytest.mark.asyncio
async def test_debug_logs_named_log_events_without_body_hex(
    restore_root_logging: None,
) -> None:
    """DEBUG names LOG events; TRACE keeps body hex; INFO stays quiet."""
    configure_logging("DEBUG")
    capture, root = _attach_capture()
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        capture.records.clear()
        task = asyncio.create_task(
            _listen_panel_messages(
                client,
                mqtt,
                settings=_settings(),
                topic_prefix="texecom",
                in_use_zones={1},
                alarm_state=_SharedAlarmState(),
                idle_timeout=0.2,
            )
        )
        # LOG Alarm Active (type=27) group=0
        body = bytes([MSG_LOG, 27, 0])
        await panel.inject_push_body(body)
        for _ in range(50):
            if any("Alarm Active" in r.getMessage() for r in capture.records):
                break
            await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        app_recs = _app_records(capture.records)
        app_msgs = _messages(app_recs)
        debug_msgs = [r.getMessage() for r in app_recs if r.levelno == logging.DEBUG]
        assert any("LOG" in m and "Alarm Active" in m and "27" in m for m in debug_msgs), debug_msgs
        # DEBUG must not require full body hex.
        assert not any(body.hex() in m for m in debug_msgs), debug_msgs
        await client.close()
    finally:
        root.removeHandler(capture)
        await panel.stop()

    # TRACE includes body hex for the same event.
    configure_logging("TRACE")
    capture, root = _attach_capture()
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        capture.records.clear()
        task = asyncio.create_task(
            _listen_panel_messages(
                client,
                mqtt,
                settings=_settings(),
                topic_prefix="texecom",
                in_use_zones={1},
                alarm_state=_SharedAlarmState(),
                idle_timeout=0.2,
            )
        )
        body = bytes([MSG_LOG, 28, 0])  # Bell Active
        await panel.inject_push_body(body)
        for _ in range(50):
            if any(body.hex() in r.getMessage() for r in capture.records):
                break
            await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        app_msgs = _messages(_app_records(capture.records))
        assert any("Bell Active" in m for m in app_msgs), app_msgs
        assert any(body.hex() in m for m in app_msgs), app_msgs
        await client.close()
    finally:
        root.removeHandler(capture)
        await panel.stop()

    # INFO: no LOG lines.
    configure_logging("INFO")
    capture, root = _attach_capture()
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        capture.records.clear()
        task = asyncio.create_task(
            _listen_panel_messages(
                client,
                mqtt,
                settings=_settings(),
                topic_prefix="texecom",
                in_use_zones={1},
                alarm_state=_SharedAlarmState(),
                idle_timeout=0.2,
            )
        )
        await panel.inject_push_body(bytes([MSG_LOG, 27, 0]))
        await asyncio.sleep(0.15)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        app_msgs = _messages(_app_records(capture.records))
        assert not any(
            "LOG" in m and ("Alarm Active" in m or "type=" in m) for m in app_msgs
        ), app_msgs
        await client.close()
    finally:
        root.removeHandler(capture)
        await panel.stop()
