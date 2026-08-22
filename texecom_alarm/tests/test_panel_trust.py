"""Silent panel-path death detection (ADR-010 / TASK-24)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.app import _listen_panel_messages, _SharedAlarmState, run
from texecom_alarm.arm_commands import handle_alarm_command
from texecom_alarm.config import Settings
from texecom_alarm.mqtt.discovery import AVAILABILITY_ONLINE, availability_topic
from texecom_alarm.panel_trust import (
    REASON_ARM_NAK,
    REASON_ARM_TIMEOUT,
    REASON_DISARM_NAK,
    REASON_DISARM_TIMEOUT,
    REASON_TRUST_POLL_NAK,
    REASON_TRUST_POLL_OK,
    REASON_TRUST_POLL_TIMEOUT,
    PanelTrust,
)
from texecom_alarm.protocol.client import PanelClient, ProtocolError


def _settings(panel: FakePanel | None = None, **overrides: object) -> Settings:
    base: dict[str, object] = dict(
        panel_host=panel.host if panel is not None else "127.0.0.1",
        panel_port=panel.port if panel is not None else 10001,
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
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _attach_capture(logger_name: str = "texecom_alarm.panel_trust") -> _Capture:
    capture = _Capture()
    logging.getLogger(logger_name).addHandler(capture)
    logging.getLogger(logger_name).setLevel(logging.DEBUG)
    return capture


def _extra(record: logging.LogRecord) -> dict[str, Any]:
    return {
        k: getattr(record, k)
        for k in (
            "reason",
            "ha_mode",
            "keepalive_still_ok",
            "seconds_since_last_successful_trust_poll",
            "seconds_since_last_command_failure",
            "panel_link_payload",
        )
        if hasattr(record, k)
    }


def _trust(
    mqtt: RecordingMqttPublisher,
    *,
    zone_count: int = 12,
    poll_interval: float = 30.0,
    recover_window: float = 30.0,
    fail_window: float = 90.0,
    clock: Callable[[], float] | None = None,
) -> PanelTrust:
    return PanelTrust(
        mqtt,
        topic_prefix="texecom",
        zone_count=zone_count,
        poll_interval=poll_interval,
        recover_window=recover_window,
        fail_window=fail_window,
        clock=clock,
    )


@pytest.mark.asyncio
async def test_arm_nak_publishes_panel_link_off_while_keepalive_ok() -> None:
    """AC1: arm NAK → Alarm Panel Connection OFF; zones/alarm stay available."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish(availability_topic("texecom"), AVAILABILITY_ONLINE, retain=True)
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    await mqtt.publish("texecom/alarm/state", "disarmed", retain=True)
    await mqtt.publish("texecom/zone/1/state", "OFF", retain=True)

    clock = {"t": 100.0}
    trust = _trust(mqtt, clock=lambda: clock["t"])
    trust.note_keepalive_ok()
    capture = _attach_capture()

    panel = MagicMock()
    panel.set_area_arm = AsyncMock(side_effect=ProtocolError("SETAREAARM NAK"))
    panel.set_area_disarm = AsyncMock()

    await handle_alarm_command(
        panel,
        _settings(),
        "ARM_AWAY",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "disarmed",
        trust=trust,
    )

    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"
    assert mqtt.payloads_for("texecom/zone/1/state")[-1] == "OFF"
    assert mqtt.payloads_for(availability_topic("texecom"))[-1] == AVAILABILITY_ONLINE

    warnings = [r for r in capture.records if r.levelno == logging.WARNING]
    assert warnings
    extra = _extra(warnings[-1])
    assert extra["reason"] == REASON_ARM_NAK
    assert extra["ha_mode"] == "away"
    assert extra["keepalive_still_ok"] is True
    assert extra["panel_link_payload"] == "OFF"
    assert "1234" not in warnings[-1].getMessage()
    msg = warnings[-1].getMessage()
    assert "away" in msg or "ha_mode=away" in msg
    lowered = msg.lower()
    assert (
        "trust poll" in lowered
        or "successful trust poll" in lowered
        or "last successful" in lowered
    )


@pytest.mark.asyncio
async def test_disarm_timeout_publishes_panel_link_off() -> None:
    """AC1: disarm timeout → OFF with disarm_timeout reason."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    trust = _trust(mqtt)
    trust.note_keepalive_ok()
    capture = _attach_capture()

    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.set_area_disarm = AsyncMock(side_effect=TimeoutError("disarm timed out"))

    await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        trust=trust,
    )

    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    warnings = [r for r in capture.records if r.levelno == logging.WARNING]
    assert warnings
    extra = _extra(warnings[-1])
    assert extra["reason"] == REASON_DISARM_TIMEOUT
    assert extra["keepalive_still_ok"] is True
    assert extra["panel_link_payload"] == "OFF"


@pytest.mark.asyncio
async def test_arm_timeout_and_disarm_nak_reasons() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    trust = _trust(mqtt)
    trust.note_keepalive_ok()
    capture = _attach_capture()

    panel = MagicMock()
    panel.set_area_arm = AsyncMock(side_effect=TimeoutError("arm timed out"))
    panel.set_area_disarm = AsyncMock()
    await handle_alarm_command(
        panel, _settings(), "ARM_HOME", mqtt=mqtt, topic_prefix="texecom", trust=trust
    )
    assert (
        _extra([r for r in capture.records if r.levelno == logging.WARNING][-1])["reason"]
        == REASON_ARM_TIMEOUT
    )

    capture.records.clear()
    panel.set_area_disarm = AsyncMock(side_effect=ProtocolError("SETAREADISARM NAK"))
    await handle_alarm_command(
        panel, _settings(), "DISARM", mqtt=mqtt, topic_prefix="texecom", trust=trust
    )
    assert (
        _extra([r for r in capture.records if r.levelno == logging.WARNING][-1])["reason"]
        == REASON_DISARM_NAK
    )


@pytest.mark.asyncio
async def test_quiet_house_stays_live_without_zone_pushes() -> None:
    """AC2: no zone push traffic alone must not degrade connectivity."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

    clock = {"t": 0.0}
    trust = _trust(mqtt, poll_interval=1.0, recover_window=1.0, clock=lambda: clock["t"])

    panel = MagicMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))

    for step in range(5):
        clock["t"] = float(step) * 1.0
        trust.note_keepalive_ok()
        await trust.maybe_poll(panel)
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"

    assert panel.get_area_flags.await_count >= 1


@pytest.mark.asyncio
async def test_trust_poll_publishes_when_area_flags_differ() -> None:
    """Successful poll updates alarm MQTT when decoded flags disagree with last HA state."""
    from texecom_alarm.area_state import AREA_FLAGS_COUNT, FLAG_PART_ARM_2, FLAG_PART_ARMED

    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/alarm/state", "armed_home", retain=True)

    clock = {"t": 0.0}
    settings = _settings()
    trust = PanelTrust(
        mqtt,
        topic_prefix="texecom",
        zone_count=12,
        poll_interval=0.0,
        clock=lambda: clock["t"],
        settings=settings,
    )
    panel = MagicMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(AREA_FLAGS_COUNT))  # quiet → disarmed

    new_payload = await trust.poll(panel, current_alarm_payload="armed_home")
    assert new_payload == "disarmed"
    assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"

    # Identical flags → no extra publish.
    before = len(mqtt.payloads_for("texecom/alarm/state"))
    again = await trust.poll(panel, current_alarm_payload="disarmed")
    assert again is None
    assert len(mqtt.payloads_for("texecom/alarm/state")) == before

    # Part-arm home flags while HA thinks disarmed → publish armed_home.
    flags = bytearray(AREA_FLAGS_COUNT)
    flags[FLAG_PART_ARMED] = 0x01
    flags[FLAG_PART_ARM_2] = 0x01
    panel.get_area_flags = AsyncMock(return_value=bytes(flags))
    home = await trust.poll(panel, current_alarm_payload="disarmed")
    assert home == "armed_home"
    assert mqtt.payloads_for("texecom/alarm/state")[-1] == "armed_home"


@pytest.mark.asyncio
async def test_trust_poll_does_not_clobber_arming_or_pending() -> None:
    """During exit, lagging disarmed/armed flags must not overwrite arming/pending."""
    from texecom_alarm.area_state import AREA_FLAGS_COUNT, FLAG_ARMED, FLAG_FULL_ARMED

    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/alarm/state", "arming", retain=True)
    trust = PanelTrust(
        mqtt,
        topic_prefix="texecom",
        zone_count=12,
        poll_interval=0.0,
        settings=_settings(),
    )
    panel = MagicMock()
    # Quiet / disarmed flags during exit — must not clear arming.
    panel.get_area_flags = AsyncMock(return_value=bytes(AREA_FLAGS_COUNT))
    assert await trust.poll(panel, current_alarm_payload="arming") is None
    assert await trust.poll(panel, current_alarm_payload="pending") is None

    flags = bytearray(AREA_FLAGS_COUNT)
    flags[FLAG_ARMED] = 0x01
    flags[FLAG_FULL_ARMED] = 0x01
    panel.get_area_flags = AsyncMock(return_value=bytes(flags))
    assert await trust.poll(panel, current_alarm_payload="arming") is None
    assert mqtt.payloads_for("texecom/alarm/state") == ["arming"]


@pytest.mark.asyncio
async def test_disarm_during_arming_publishes_disarmed_snapshot() -> None:
    """Cancel-during-exit: disarm ACK + flags must clear stuck arming MQTT."""
    from texecom_alarm.arm_commands import handle_alarm_command

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/alarm/state", "arming", retain=True)

    result = await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "arming",
        zone_count=12,
    )

    assert result == "disarmed"
    assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"


@pytest.mark.asyncio
async def test_disarm_during_arming_coerces_lagging_armed_flags() -> None:
    """Post-disarm GetAreaFlags still armed_* → publish disarmed (ACK wins)."""
    from texecom_alarm.area_state import AREA_FLAGS_COUNT, FLAG_ARMED, FLAG_FULL_ARMED
    from texecom_alarm.arm_commands import handle_alarm_command

    flags = bytearray(AREA_FLAGS_COUNT)
    flags[FLAG_ARMED] = 0x01
    flags[FLAG_FULL_ARMED] = 0x01
    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(flags))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/alarm/state", "arming", retain=True)

    result = await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "arming",
        zone_count=12,
    )

    assert result == "disarmed"
    assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"


@pytest.mark.asyncio
async def test_trust_poll_nak_publishes_off_with_timing_context() -> None:
    """AC2: failed trust poll → OFF with trust_poll_nak + timing fields."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

    clock = {"t": 10.0}
    trust = _trust(mqtt, poll_interval=1.0, clock=lambda: clock["t"])
    trust.note_keepalive_ok()
    # Seed a prior successful poll so "seconds since" is defined.
    panel_ok = MagicMock()
    panel_ok.get_area_flags = AsyncMock(return_value=bytes(72))
    await trust.maybe_poll(panel_ok)

    clock["t"] = 12.0
    capture = _attach_capture()
    panel_fail = MagicMock()
    panel_fail.get_area_flags = AsyncMock(side_effect=ProtocolError("GetAreaFlags NAK"))
    await trust.maybe_poll(panel_fail)

    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    warnings = [r for r in capture.records if r.levelno == logging.WARNING]
    assert warnings
    extra = _extra(warnings[-1])
    assert extra["reason"] == REASON_TRUST_POLL_NAK
    assert extra["keepalive_still_ok"] is True
    assert extra["panel_link_payload"] == "OFF"
    assert isinstance(extra["seconds_since_last_successful_trust_poll"], int | float)


@pytest.mark.asyncio
async def test_trust_poll_timeout_reason() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    clock = {"t": 0.0}
    trust = _trust(mqtt, poll_interval=0.0, clock=lambda: clock["t"])
    capture = _attach_capture()
    panel = MagicMock()
    panel.get_area_flags = AsyncMock(side_effect=TimeoutError("poll timed out"))
    await trust.maybe_poll(panel)
    warnings = [r for r in capture.records if r.levelno == logging.WARNING]
    assert warnings
    assert _extra(warnings[-1])["reason"] == REASON_TRUST_POLL_TIMEOUT
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"


@pytest.mark.asyncio
async def test_transient_command_reject_recovers_after_window() -> None:
    """AC3: single NAK → OFF; after recover window + successful poll → ON without restart."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

    clock = {"t": 0.0}
    trust = _trust(mqtt, poll_interval=1.0, recover_window=30.0, clock=lambda: clock["t"])
    trust.note_keepalive_ok()
    capture = _attach_capture()

    await trust.record_command_failure(REASON_ARM_NAK, ha_mode="away")
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"

    panel = MagicMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))

    # Successful poll inside recover window must stay OFF.
    clock["t"] = 10.0
    await trust.maybe_poll(panel)
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"

    # Past recover window: successful poll returns to live.
    clock["t"] = 31.0
    await trust.maybe_poll(panel)
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"

    infos = [r for r in capture.records if r.levelno == logging.INFO]
    assert infos
    recover = [r for r in infos if getattr(r, "panel_link_payload", None) == "ON"]
    assert recover
    assert recover[-1].reason == REASON_TRUST_POLL_OK
    msg = recover[-1].getMessage().lower()
    assert "live" in msg or "recover" in msg


@pytest.mark.asyncio
async def test_corroboration_within_fail_window_does_not_request_relogin() -> None:
    """AC1: successful trust poll inside fail window recovers without tear-down."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

    clock = {"t": 0.0}
    trust = _trust(
        mqtt,
        poll_interval=1.0,
        recover_window=1.0,
        fail_window=90.0,
        clock=lambda: clock["t"],
    )
    trust.note_keepalive_ok()
    await trust.record_command_failure(REASON_ARM_NAK, ha_mode="away")
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    assert trust.needs_session_relogin() is False

    clock["t"] = 2.0
    panel = MagicMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    await trust.maybe_poll(panel)

    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
    assert trust.live is True
    assert trust.needs_session_relogin() is False
    clock["t"] = 200.0
    assert trust.needs_session_relogin() is False


@pytest.mark.asyncio
async def test_stuck_past_fail_window_requests_session_relogin() -> None:
    """AC2: Connection continuously OFF past fail window → session relogin needed."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

    clock = {"t": 10.0}
    trust = _trust(mqtt, poll_interval=1.0, fail_window=90.0, clock=lambda: clock["t"])
    trust.note_keepalive_ok()
    capture = _attach_capture()

    panel_fail = MagicMock()
    panel_fail.get_area_flags = AsyncMock(side_effect=ProtocolError("GetAreaFlags NAK"))
    await trust.maybe_poll(panel_fail)
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    assert trust.needs_session_relogin() is False

    clock["t"] = 99.0
    assert trust.needs_session_relogin() is False

    clock["t"] = 100.0
    assert trust.needs_session_relogin() is True
    trust.log_stuck_fail_window_expiry()
    infos = [r for r in capture.records if r.levelno >= logging.INFO]
    assert infos
    assert any(
        "fail window" in r.getMessage().lower() or "stuck" in r.getMessage().lower() for r in infos
    )


@pytest.mark.asyncio
async def test_reset_after_reconnect_republishes_panel_link_on() -> None:
    """Command OFF after reconnect ON must not stick: reset republishes ON.

    Race: reconnect publishes panel-link ON, then a command failure publishes OFF,
    then reset_after_reconnect sets _live True. Without republishing ON, MQTT stays
    OFF and _maybe_recover early-returns because _live is already True.
    """
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

    clock = {"t": 0.0}
    trust = _trust(mqtt, poll_interval=1.0, recover_window=1.0, clock=lambda: clock["t"])
    trust.note_keepalive_ok()

    # Simulates MQTT command handler publishing OFF after reconnect already ON.
    await trust.record_command_failure(REASON_ARM_NAK, ha_mode="away")
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    assert trust.live is False

    await trust.reset_after_reconnect()
    assert trust.live is True
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"

    # Successful trust poll must remain ON (would stay OFF if reset skipped publish
    # and left _live True so _maybe_recover never republished).
    clock["t"] = 2.0
    panel = MagicMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    await trust.maybe_poll(panel)
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
    assert trust.live is True


@pytest.mark.asyncio
async def test_listen_loop_runs_trust_poll_alongside_keepalive() -> None:
    """Trust poll rides the listen loop; quiet (no ZONE) stays ON when poll OK."""
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
        await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

        trust = PanelTrust(
            mqtt,
            topic_prefix="texecom",
            zone_count=12,
            poll_interval=0.05,
            recover_window=0.05,
        )
        task = asyncio.create_task(
            _listen_panel_messages(
                client,
                mqtt,
                settings=_settings(panel),
                topic_prefix="texecom",
                in_use_zones={1},
                alarm_state=_SharedAlarmState(payload="disarmed"),
                idle_timeout=0.05,
                trust=trust,
            )
        )
        for _ in range(80):
            if panel.area_flags_calls >= 1 and panel.keepalive_attempts >= 1:
                break
            await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert panel.keepalive_attempts >= 1
        assert panel.area_flags_calls >= 1
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_arm_nak_while_keepalive_ok_marks_degraded() -> None:
    """FakePanel: keepalive OK + arm NAK → panel_connection OFF; availability unchanged."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="FRONT DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
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
                _settings(panel),
                panel=client,
                mqtt=mqtt,
                idle=stop.wait,
                trust_poll_interval=60.0,
                trust_recover_window=30.0,
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

        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
        assert mqtt.payloads_for(availability_topic("texecom"))[-1] == AVAILABILITY_ONLINE
        before_avail = list(mqtt.payloads_for(availability_topic("texecom")))

        panel.nak_next_arm = True
        await mqtt.push_inbound("texecom/alarm/command", "ARM_AWAY")
        for _ in range(100):
            if mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF":
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
        assert mqtt.payloads_for(availability_topic("texecom")) == before_avail
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_e2e_trust_poll_fail_then_recover() -> None:
    """FakePanel: trust-poll NAK → OFF; later success past recover → ON."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
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
                _settings(panel),
                panel=client,
                mqtt=mqtt,
                idle=stop.wait,
                trust_poll_interval=0.08,
                trust_recover_window=0.05,
            )
        )
        for _ in range(150):
            if mqtt.payloads_for("texecom/panel_connection/state") == ["ON"] or (
                mqtt.payloads_for("texecom/panel_connection/state")
                and mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
            ):
                if "texecom/alarm/command" in mqtt.subscribed:
                    break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"

        # Fail the next trust poll only (startup snapshot already completed).
        panel.nak_next_area_flags = 1
        for _ in range(200):
            if "OFF" in mqtt.payloads_for("texecom/panel_connection/state"):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert "OFF" in mqtt.payloads_for("texecom/panel_connection/state")

        for _ in range(200):
            payloads = mqtt.payloads_for("texecom/panel_connection/state")
            if "OFF" in payloads and payloads[-1] == "ON":
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        payloads = mqtt.payloads_for("texecom/panel_connection/state")
        assert "OFF" in payloads
        assert payloads[-1] == "ON"

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()
