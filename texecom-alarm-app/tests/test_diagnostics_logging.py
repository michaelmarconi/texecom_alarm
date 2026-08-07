"""Integration tests for DEBUG handling and TRACE panel-session logging (AC4–AC6)."""

from __future__ import annotations

import logging
import re

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.arm_commands import handle_alarm_command
from texecom_alarm.config import Settings
from texecom_alarm.logging_setup import TRACE_LEVEL, configure_logging
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.protocol.frame import MSG_ZONE
from texecom_alarm.zone_state import handle_zone_message

# Modem-style piping observed in SPIKE-002 / ADR-002.
_MODEM_JUNK = b"ATH0\rATZ\r"


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
        )

        app_msgs = _messages(_app_records(capture.records))
        assert any("mqtt_zone_state" in m for m in app_msgs)
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

        await handle_alarm_command(client, settings, "ARM_AWAY")
        await handle_alarm_command(client, settings, "DISARM")

        app_msgs = _messages(_app_records(capture.records))
        assert any("alarm_command_arm" in m for m in app_msgs)
        assert any("panel_set_area_arm_ok" in m or "alarm_command_arm" in m for m in app_msgs)
        assert any("alarm_command_disarm" in m for m in app_msgs)
        assert any("panel_set_area_disarm_ok" in m or "alarm_command_disarm" in m for m in app_msgs)
        assert panel.arm_calls == [0]
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
        assert any(r.levelno == TRACE_LEVEL for r in app_recs if "panel_tx" in r.getMessage())
        assert any(r.levelno == TRACE_LEVEL for r in app_recs if "panel_rx" in r.getMessage())
        await client.close()
    finally:
        root.removeHandler(capture)
        await panel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("level", ["WARNING", "INFO", "DEBUG"])
async def test_modem_skip_does_not_dump_raw_piping_below_trace(
    level: str,
    restore_root_logging: None,
) -> None:
    """AC6: WARNING–DEBUG must not dump modem piping or flood with skip noise."""
    configure_logging(level)
    capture, root = _attach_capture()
    panel = FakePanel(udl_password="1234")
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        capture.records.clear()

        panel.inject_before_next_response(_MODEM_JUNK)
        await client.keepalive()

        app_msgs = _messages(_app_records(capture.records))
        joined = " ".join(app_msgs).lower()
        assert "ath0" not in joined
        assert "atz" not in joined
        assert _MODEM_JUNK.hex() not in joined
        # Modem/non-frame skips stay silent at WARNING–DEBUG (no skip flood).
        assert not any("resync" in m.lower() for m in app_msgs)
        assert not any(re.search(r"skipped\s+\d+\s+bytes", m) for m in app_msgs)
        await client.close()
    finally:
        root.removeHandler(capture)
        await panel.stop()


@pytest.mark.asyncio
async def test_trace_emits_compact_resync_skip_notice(
    restore_root_logging: None,
) -> None:
    """AC6: TRACE shows at most a compact skip notice, not a raw modem dump."""
    configure_logging("TRACE")
    capture, root = _attach_capture()
    panel = FakePanel(udl_password="1234")
    await panel.start()
    try:
        client = await _logged_in_client(panel)
        capture.records.clear()

        panel.inject_before_next_response(_MODEM_JUNK)
        await client.keepalive()

        app_recs = _app_records(capture.records)
        app_msgs = _messages(app_recs)
        skip_msgs = [
            m for m in app_msgs if "panel_resync" in m or re.search(r"skipped\s+\d+\s+bytes", m)
        ]
        assert skip_msgs, f"expected compact resync notice at TRACE, got {app_msgs!r}"
        assert any(r.levelno == TRACE_LEVEL for r in app_recs if r.getMessage() in skip_msgs)
        joined = " ".join(skip_msgs).lower()
        assert "ath0" not in joined
        assert "atz" not in joined
        assert _MODEM_JUNK.hex() not in " ".join(app_msgs)
        # Compact: one notice naming skipped byte count, not a raw stream dump.
        assert any(re.search(r"skipped\s+\d+\s+bytes", m) for m in skip_msgs)
        await client.close()
    finally:
        root.removeHandler(capture)
        await panel.stop()
