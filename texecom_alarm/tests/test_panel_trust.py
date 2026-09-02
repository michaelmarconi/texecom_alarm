"""Silent panel-path death detection (ADR-016)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.app import (
    _listen_panel_messages,
    _send_scheduled_checkin,
    _SharedAlarmState,
    run,
)
from texecom_alarm.arm_commands import handle_alarm_command
from texecom_alarm.config import Settings
from texecom_alarm.mqtt.discovery import AVAILABILITY_ONLINE, availability_topic
from texecom_alarm.panel_trust import (
    REASON_ARM_NAK,
    REASON_ARM_TIMEOUT,
    REASON_DISARM_DISCONNECT,
    REASON_DISARM_NAK,
    REASON_DISARM_TIMEOUT,
    REASON_KEEPALIVE_OK,
    REASON_PANEL_TRAFFIC,
    REASON_TRUST_POLL_NAK,
    REASON_TRUST_POLL_TIMEOUT,
    PanelTrust,
)
from texecom_alarm.protocol.client import ForcedDisconnect, PanelClient, ProtocolError
from texecom_alarm.protocol.frame import CMD_GET_AREA_FLAGS, CMD_GET_ZONE_STATE, CMD_LOGIN
from texecom_alarm.reconnect import reconnect_after_disconnect
from texecom_alarm.zones import Zone


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
    checkin_patience: float = 45.0,
    clock: Callable[[], float] | None = None,
) -> PanelTrust:
    return PanelTrust(
        mqtt,
        topic_prefix="texecom",
        zone_count=zone_count,
        poll_interval=poll_interval,
        recover_window=recover_window,
        fail_window=fail_window,
        checkin_patience=checkin_patience,
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
    await trust.note_keepalive_ok()
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
    await trust.note_keepalive_ok()
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
    await trust.note_keepalive_ok()
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
async def test_disarm_on_a_dead_socket_records_a_command_failure() -> None:
    """A disarm that fails because the socket died must be recorded as a command
    failure and turn Alarm Panel Connection off — not escape as an unclassified
    network error that leaves Connection reading healthy."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
        await mqtt.publish(availability_topic("texecom"), AVAILABILITY_ONLINE, retain=True)
        trust = _trust(mqtt)
        await trust.note_keepalive_ok()
        capture = _attach_capture()

        client = PanelClient(
            panel.host,
            panel.port,
            udl_password="1234",
            login_delay=0.0,
            response_timeout=0.5,
        )
        await client.connect()
        await client.login()
        assert client._writer is not None

        def _rst(_data: bytes) -> None:
            raise ConnectionResetError("Connection reset by peer")

        client._writer.write = _rst  # type: ignore[method-assign]

        await handle_alarm_command(
            client,
            _settings(panel),
            "DISARM",
            mqtt=mqtt,
            topic_prefix="texecom",
            trust=trust,
        )

        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
        warnings = [r for r in capture.records if r.levelno == logging.WARNING]
        assert warnings
        assert _extra(warnings[-1])["reason"] == REASON_DISARM_DISCONNECT
        # Availability still belongs to the process alone (ADR-004).
        assert mqtt.payloads_for(availability_topic("texecom"))[-1] == AVAILABILITY_ONLINE
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_session_collision_does_not_record_a_command_failure() -> None:
    """An unreadable follow-up after a successful tap is not a failed arm/disarm."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    trust = _trust(mqtt)
    await trust.note_keepalive_ok()

    trust.note_session_collision()

    assert trust.live is True
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
    assert trust.consume_session_collision() is True
    assert trust.consume_session_collision() is False


@pytest.mark.asyncio
async def test_collision_resync_keeps_connection_on_when_first_relogin_succeeds() -> None:
    """First re-login after a post-ACK parse miss must not publish Connection off."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        client = PanelClient(
            panel.host, panel.port, udl_password="1234", login_delay=0.0, response_timeout=0.5
        )
        await client.connect()
        await client.login()
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
        settings = _settings(panel, reconnect_delay_seconds=0.01)
        zones = [Zone(number=1, zone_type=1, name="DOOR")]
        cmds_before = list(panel.commands_seen)

        async def instant_sleep(_delay: float) -> None:
            return None

        await reconnect_after_disconnect(
            client,
            mqtt,
            settings=settings,
            zones=zones,
            zone_count=12,
            sleep=instant_sleep,
            collision=True,
        )

        link = mqtt.payloads_for("texecom/panel_connection/state")
        assert "OFF" not in link
        assert link[-1] == "ON"
        new_cmds = panel.commands_seen[len(cmds_before) :]
        assert CMD_LOGIN in new_cmds
        assert CMD_GET_ZONE_STATE in new_cmds
        assert CMD_GET_AREA_FLAGS in new_cmds
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_collision_resync_turns_connection_off_when_first_relogin_fails() -> None:
    """If the first collision re-login fails, Connection goes off and keep-trying continues."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        client = PanelClient(
            panel.host, panel.port, udl_password="1234", login_delay=0.0, response_timeout=0.5
        )
        await client.connect()
        await client.login()
        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
        settings = _settings(panel, reconnect_delay_seconds=0.01)
        zones = [Zone(number=1, zone_type=1, name="DOOR")]

        fails_left = {"n": 1}
        real_connect = client.connect

        async def flaky_connect() -> None:
            if fails_left["n"] > 0:
                fails_left["n"] -= 1
                raise OSError("connection refused")
            await real_connect()

        client.connect = flaky_connect  # type: ignore[method-assign]

        async def instant_sleep(_delay: float) -> None:
            return None

        await reconnect_after_disconnect(
            client,
            mqtt,
            settings=settings,
            zones=zones,
            zone_count=12,
            sleep=instant_sleep,
            collision=True,
        )

        link = mqtt.payloads_for("texecom/panel_connection/state")
        assert "OFF" in link
        assert link[-1] == "ON"
        await client.close()
    finally:
        await panel.stop()


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
        await trust.note_keepalive_ok()
        await trust.maybe_poll(panel)
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"

    assert panel.get_area_flags.await_count >= 1


def test_poll_interval_is_configurable_and_does_not_affect_default() -> None:
    """AC2: a household-configured interval changes poll cadence directly."""
    mqtt = RecordingMqttPublisher()
    clock = {"t": 0.0}
    fast = _trust(mqtt, poll_interval=60.0, clock=lambda: clock["t"])
    slow = _trust(mqtt, poll_interval=300.0, clock=lambda: clock["t"])

    # Both are due on first check (no prior attempt recorded yet).
    assert fast.poll_due() is True
    assert slow.poll_due() is True


@pytest.mark.asyncio
async def test_configured_poll_interval_changes_cadence_not_connection() -> None:
    """AC2/AC3: interval controls poll cadence only; Connection stays untouched."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

    clock = {"t": 0.0}
    trust = _trust(mqtt, poll_interval=60.0, clock=lambda: clock["t"])
    panel = MagicMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))

    # First poll always runs (no prior attempt).
    await trust.maybe_poll(panel)
    assert panel.get_area_flags.await_count == 1

    # Well inside the 60s interval: not due yet, poll does not fire again.
    clock["t"] = 30.0
    await trust.maybe_poll(panel)
    assert panel.get_area_flags.await_count == 1

    # Past the configured interval: due again.
    clock["t"] = 61.0
    await trust.maybe_poll(panel)
    assert panel.get_area_flags.await_count == 2

    # Cadence changes alone must never move Connection off ON.
    assert trust.live is True
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"


@pytest.mark.asyncio
async def test_default_poll_interval_matches_five_minute_default() -> None:
    """AC1: a trust built with the shipping default fires on a 5-minute cadence."""
    from texecom_alarm.panel_trust import TRUST_POLL_INTERVAL_SECONDS

    assert TRUST_POLL_INTERVAL_SECONDS == 300.0

    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    clock = {"t": 0.0}
    trust = PanelTrust(
        mqtt,
        topic_prefix="texecom",
        zone_count=12,
        clock=lambda: clock["t"],
    )
    panel = MagicMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))

    await trust.maybe_poll(panel)
    assert panel.get_area_flags.await_count == 1

    clock["t"] = 299.0
    await trust.maybe_poll(panel)
    assert panel.get_area_flags.await_count == 1, "must not poll again before 300s elapse"

    clock["t"] = 300.0
    await trust.maybe_poll(panel)
    assert panel.get_area_flags.await_count == 2


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
async def test_isolated_trust_poll_nak_does_not_publish_off() -> None:
    """ADR-016 / SPIKE-011 S6: a lone reconciliation-poll NAK, with keepalive
    healthy and no command failure, must never flip Alarm Panel Connection OFF."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

    clock = {"t": 10.0}
    trust = _trust(mqtt, poll_interval=1.0, clock=lambda: clock["t"])
    await trust.note_keepalive_ok()
    # Seed a prior successful poll so "seconds since" is defined.
    panel_ok = MagicMock()
    panel_ok.get_area_flags = AsyncMock(return_value=bytes(72))
    await trust.maybe_poll(panel_ok)

    clock["t"] = 12.0
    capture = _attach_capture()
    panel_fail = MagicMock()
    panel_fail.get_area_flags = AsyncMock(side_effect=ProtocolError("GetAreaFlags NAK"))
    await trust.maybe_poll(panel_fail)

    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
    assert trust.live is True
    warnings = [r for r in capture.records if r.levelno == logging.WARNING]
    assert not warnings, "a lone poll NAK must never warn as a Connection degrade"
    debugs = [r for r in capture.records if r.levelno == logging.DEBUG]
    assert debugs
    extra = _extra(debugs[-1])
    assert extra["reason"] == REASON_TRUST_POLL_NAK
    assert extra["keepalive_still_ok"] is True
    assert extra["panel_link_payload"] == "ON"


@pytest.mark.asyncio
async def test_isolated_trust_poll_timeout_does_not_publish_off() -> None:
    """ADR-016 / SPIKE-011 S6: a lone reconciliation-poll timeout, with keepalive
    healthy, must never flip Alarm Panel Connection OFF."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    clock = {"t": 0.0}
    trust = _trust(mqtt, poll_interval=0.0, clock=lambda: clock["t"])
    await trust.note_keepalive_ok()
    capture = _attach_capture()
    panel = MagicMock()
    panel.get_area_flags = AsyncMock(side_effect=TimeoutError("poll timed out"))
    await trust.maybe_poll(panel)
    warnings = [r for r in capture.records if r.levelno == logging.WARNING]
    assert not warnings, "a lone poll timeout must never warn as a Connection degrade"
    debugs = [r for r in capture.records if r.levelno == logging.DEBUG]
    assert debugs
    assert _extra(debugs[-1])["reason"] == REASON_TRUST_POLL_TIMEOUT
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
    assert trust.live is True


@pytest.mark.asyncio
async def test_transient_command_reject_recovers_after_window() -> None:
    """AC2: single NAK → OFF; recovers via resumed keepalives (not a poll) once
    the command-failure recover window has cleared."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

    clock = {"t": 0.0}
    trust = _trust(mqtt, poll_interval=1.0, recover_window=30.0, clock=lambda: clock["t"])
    await trust.note_keepalive_ok()
    capture = _attach_capture()

    await trust.record_command_failure(REASON_ARM_NAK, ha_mode="away")
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"

    # A poll failing while OFF changes nothing — recovery never depends on it.
    panel = MagicMock()
    panel.get_area_flags = AsyncMock(side_effect=ProtocolError("GetAreaFlags NAK"))
    clock["t"] = 10.0
    await trust.maybe_poll(panel)
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"

    # Keepalive success inside the recover window must stay OFF.
    await trust.note_keepalive_ok()
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"

    # Past the recover window: a resumed keepalive returns to live.
    clock["t"] = 31.0
    await trust.note_keepalive_ok()
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"

    infos = [r for r in capture.records if r.levelno == logging.INFO]
    assert infos
    recover = [r for r in infos if getattr(r, "panel_link_payload", None) == "ON"]
    assert recover
    assert recover[-1].reason == REASON_KEEPALIVE_OK
    msg = recover[-1].getMessage().lower()
    assert "live" in msg or "recover" in msg


@pytest.mark.asyncio
async def test_continuous_panel_traffic_still_recovers_connection() -> None:
    """A busy panel that never goes idle must not stall Connection recovery.

    If ordinary zone/area/log frames keep arriving faster than the idle
    timeout, ``recv_message`` never raises ``TimeoutError`` and the
    keepalive branch (the only place recovery used to be driven from) never
    runs. Any well-formed frame is itself evidence the panel is alive, so it
    must drive the same recovery as a successful keepalive.
    """
    from texecom_alarm.protocol.frame import MSG_ZONE

    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

    clock = {"t": 0.0}
    trust = _trust(mqtt, poll_interval=1000.0, recover_window=1.0, clock=lambda: clock["t"])
    await trust.note_keepalive_ok()
    await trust.record_command_failure(REASON_ARM_NAK, ha_mode="away")
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    capture = _attach_capture()

    panel = MagicMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    panel.keepalive = AsyncMock()
    zone_body = bytes([MSG_ZONE, 1, 0x01])

    class _Frame:
        body = zone_body

    async def _recv(*, timeout: float = 1.0) -> object:
        # Yield once so the test's watchdog loop below still gets scheduled,
        # then advance the clock — frames keep arriving well inside the idle
        # window, so recv_message must never time out.
        await asyncio.sleep(0)
        clock["t"] += 0.1
        return _Frame()

    panel.recv_message = _recv

    task = asyncio.create_task(
        _listen_panel_messages(
            panel,
            mqtt,
            settings=_settings(),
            topic_prefix="texecom",
            in_use_zones={1},
            alarm_state=_SharedAlarmState(payload="disarmed"),
            idle_timeout=5.0,
            trust=trust,
        )
    )
    try:
        for _ in range(500):
            if trust.live:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert trust.live is True
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
    # Recovered via the frame-received path, not the idle-timeout keepalive.
    assert panel.keepalive.await_count == 0
    infos = [r for r in capture.records if r.levelno == logging.INFO]
    recover = [r for r in infos if getattr(r, "panel_link_payload", None) == "ON"]
    assert recover
    assert recover[-1].reason == REASON_PANEL_TRAFFIC


@pytest.mark.asyncio
async def test_corroboration_within_fail_window_does_not_request_relogin() -> None:
    """AC2: a resumed keepalive inside the fail window recovers without tear-down."""
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
    await trust.note_keepalive_ok()
    await trust.record_command_failure(REASON_ARM_NAK, ha_mode="away")
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    assert trust.needs_session_relogin() is False

    clock["t"] = 2.0
    await trust.note_keepalive_ok()

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
    await trust.note_keepalive_ok()
    capture = _attach_capture()

    await trust.record_command_failure(REASON_ARM_NAK, ha_mode="away")
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
    await trust.note_keepalive_ok()

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
async def test_checkin_schedule_independent_of_reconciliation_poll_interval() -> None:
    """The check-in schedule and the reconciliation poll interval must never
    affect each other (per ADR-020): a slow poll must not slow check-ins, and
    a slow check-in must not slow the poll."""
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

        # Fast check-in, deliberately slow (effectively never-due) poll: the
        # check-in must still fire repeatedly on its own schedule.
        trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12, poll_interval=1000.0)
        task = asyncio.create_task(
            _listen_panel_messages(
                client,
                mqtt,
                settings=_settings(panel),
                topic_prefix="texecom",
                in_use_zones={1},
                alarm_state=_SharedAlarmState(payload="disarmed"),
                idle_timeout=0.03,
                trust=trust,
            )
        )
        for _ in range(150):
            if panel.keepalive_attempts >= 5:
                break
            await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert (
            panel.keepalive_attempts >= 5
        ), "a slow reconciliation poll interval must not slow the check-in schedule"
        # The poll runs once immediately (nothing polled yet), then not again
        # for 1000s — it must not have ridden along with the fast check-ins.
        assert panel.area_flags_calls <= 1
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_reconciliation_poll_independent_of_checkin_interval() -> None:
    """The other direction of the same independence guarantee (per ADR-020):
    a slow check-in must not slow the separate reconciliation poll."""
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

        # Fast poll, deliberately slow (effectively never-due) check-in: the
        # poll must still fire repeatedly on its own schedule.
        trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12, poll_interval=0.03)
        task = asyncio.create_task(
            _listen_panel_messages(
                client,
                mqtt,
                settings=_settings(panel),
                topic_prefix="texecom",
                in_use_zones={1},
                alarm_state=_SharedAlarmState(payload="disarmed"),
                idle_timeout=1000.0,
                trust=trust,
            )
        )
        for _ in range(150):
            if panel.area_flags_calls >= 5:
                break
            await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert (
            panel.area_flags_calls >= 5
        ), "a slow check-in interval must not slow the reconciliation poll"
        assert panel.keepalive_attempts == 0
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
    """FakePanel: command reject → OFF; recovers via resumed keepalives even
    while the reconciliation poll keeps failing throughout (ADR-016 decouples
    the two)."""
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
                idle_timeout=0.05,
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

        # Fail every reconciliation poll from here on — it must never block
        # recovery. Check-ins fire on their own fixed schedule (idle_timeout
        # above, ADR-020) independent of the poll interval below.
        panel.nak_next_area_flags = 1000
        panel.nak_next_arm = True
        await mqtt.push_inbound("texecom/alarm/command", "ARM_AWAY")
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
        # The reconciliation poll kept running (and kept failing) the whole time —
        # it had no bearing on this recovery (ADR-016).
        assert panel.area_flags_calls >= 1
        assert panel.nak_next_area_flags > 0

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_checkin_failure_without_a_trust_tracker_still_ends_the_session() -> None:
    """No ``PanelTrust`` to hold patience open with — falls back to the
    pre-ADR-020 immediate-death behaviour rather than silently ignoring every
    future check-in failure forever."""
    panel = MagicMock()
    panel.keepalive = AsyncMock(side_effect=TimeoutError("no reply"))
    with pytest.raises(ForcedDisconnect):
        await _send_scheduled_checkin(panel, None)


@pytest.mark.asyncio
async def test_outright_disconnect_without_a_trust_tracker_still_propagates() -> None:
    """A transport-level ForcedDisconnect must still propagate with no tracker."""
    panel = MagicMock()
    panel.keepalive = AsyncMock(side_effect=ForcedDisconnect("peer closed the session"))
    with pytest.raises(ForcedDisconnect):
        await _send_scheduled_checkin(panel, None)


@pytest.mark.asyncio
async def test_checkin_failure_within_patience_stays_live_and_does_not_raise() -> None:
    """AC1: a refused/unanswered check-in that has not yet run past the
    configured patience must not raise ForcedDisconnect and must not touch
    Alarm Panel Connection at all — it stays exactly as it was."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    clock = {"t": 0.0}
    trust = _trust(mqtt, checkin_patience=10.0, clock=lambda: clock["t"])
    await trust.note_keepalive_ok()

    panel = MagicMock()
    panel.keepalive = AsyncMock(side_effect=ProtocolError("GETDATETIME NAK"))

    clock["t"] = 1.0
    await _send_scheduled_checkin(panel, trust)
    assert trust.live is True
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"

    clock["t"] = 5.0
    await _send_scheduled_checkin(panel, trust)
    assert trust.live is True
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
    assert trust.checkin_patience_exceeded() is False


@pytest.mark.asyncio
async def test_checkin_failure_past_patience_raises_forced_disconnect() -> None:
    """AC2: continuous check-in failure that has run past the configured
    patience must declare the session dead (ForcedDisconnect), so the
    existing reconnect-after-disconnect flow runs."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    clock = {"t": 0.0}
    trust = _trust(mqtt, checkin_patience=10.0, clock=lambda: clock["t"])
    await trust.note_keepalive_ok()

    panel = MagicMock()
    panel.keepalive = AsyncMock(side_effect=TimeoutError("no reply"))

    clock["t"] = 1.0
    await _send_scheduled_checkin(panel, trust)  # first failure — starts the streak

    clock["t"] = 11.0
    with pytest.raises(ForcedDisconnect):
        await _send_scheduled_checkin(panel, trust)


@pytest.mark.asyncio
async def test_checkin_success_restarts_the_patience_clock() -> None:
    """A successful check-in in between two failures must clear the streak —
    the second failure starts a brand-new patience window, not a continuation
    of the first."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    clock = {"t": 0.0}
    trust = _trust(mqtt, checkin_patience=5.0, clock=lambda: clock["t"])
    await trust.note_keepalive_ok()

    panel = MagicMock()
    panel.keepalive = AsyncMock(side_effect=TimeoutError("no reply"))
    clock["t"] = 1.0
    await _send_scheduled_checkin(panel, trust)
    assert trust.checkin_patience_exceeded() is False

    panel.keepalive = AsyncMock(return_value=b"\x00" * 6)
    clock["t"] = 2.0
    await _send_scheduled_checkin(panel, trust)
    assert trust.checkin_patience_exceeded() is False

    panel.keepalive = AsyncMock(side_effect=TimeoutError("no reply"))
    clock["t"] = 6.0
    # 4s since the restart at t=2.0 — still inside the 5s patience window,
    # even though 6s have passed since the original failure at t=1.0.
    await _send_scheduled_checkin(panel, trust)
    assert trust.checkin_patience_exceeded() is False


@pytest.mark.asyncio
async def test_unsolicited_panel_traffic_does_not_hold_the_patience_window_open() -> None:
    """A panel that keeps pushing zone/area/log frames while refusing every
    check-in must still be declared dead once patience runs out. Only a
    check-in that actually got a valid reply proves the panel still answers
    when asked; its own unprompted chatter never does, or a busy-but-refusing
    session would reset the patience clock with its own traffic and never be
    recovered (ADR-020)."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    clock = {"t": 0.0}
    trust = _trust(mqtt, checkin_patience=10.0, clock=lambda: clock["t"])
    await trust.note_keepalive_ok()

    panel = MagicMock()
    panel.keepalive = AsyncMock(side_effect=ProtocolError("GETDATETIME NAK"))

    # Each tick mirrors one busy listen-loop iteration: the due check-in is
    # refused, then the frame that arrived is recorded as panel traffic.
    for tick in (1.0, 4.0, 7.0):
        clock["t"] = tick
        await _send_scheduled_checkin(panel, trust)
        await trust.note_panel_traffic()
        assert trust.checkin_patience_exceeded() is False
        assert trust.live is True

    # 10s of unbroken refusals since the streak began at t=1.0, all of it
    # under a steady stream of panel traffic.
    clock["t"] = 11.0
    assert trust.checkin_patience_exceeded() is True
    with pytest.raises(ForcedDisconnect):
        await _send_scheduled_checkin(panel, trust)


@pytest.mark.asyncio
async def test_outright_disconnect_bypasses_patience_immediately() -> None:
    """AC2: a transport-level ForcedDisconnect from keepalive() (peer close,
    ``+++``, non-conforming data) must end the session immediately, with no
    patience delay, even with a very long configured patience."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    clock = {"t": 0.0}
    trust = _trust(mqtt, checkin_patience=1000.0, clock=lambda: clock["t"])
    await trust.note_keepalive_ok()

    panel = MagicMock()
    panel.keepalive = AsyncMock(side_effect=ForcedDisconnect("peer closed the session"))

    with pytest.raises(ForcedDisconnect):
        await _send_scheduled_checkin(panel, trust)
    # A ForcedDisconnect must never start (or count toward) a patience streak.
    assert trust.checkin_patience_exceeded() is False


@pytest.mark.asyncio
async def test_command_watchdog_fail_window_independent_of_checkin_patience() -> None:
    """The command-rejection countdown and the check-in patience clock are
    separate fields: a long patience window does not stop the command
    watchdog from becoming due on *its* timer.

    This uses a fail window shorter than the recover window so the
    countdown can expire before a successful check-in is allowed to clear
    the degrade. That is the inverse of the shipped 90s-against-30s
    ratio, where a healthy check-in restores Connection first — this test
    does not claim the watchdog fires at those shipped numbers."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    clock = {"t": 0.0}
    trust = _trust(
        mqtt,
        fail_window=10.0,
        checkin_patience=10_000.0,
        clock=lambda: clock["t"],
    )
    await trust.note_keepalive_ok()

    panel = MagicMock()
    panel.keepalive = AsyncMock(return_value=b"\x00" * 6)

    clock["t"] = 1.0
    await _send_scheduled_checkin(panel, trust)
    assert trust.live is True

    await trust.record_command_failure(REASON_ARM_NAK, ha_mode="away")
    assert trust.live is False
    assert trust.needs_session_relogin() is False

    # Check-ins keep succeeding the whole time — must not reset or otherwise
    # interact with the command watchdog's own countdown.
    clock["t"] = 5.0
    await _send_scheduled_checkin(panel, trust)
    assert trust.needs_session_relogin() is False

    clock["t"] = 9.0
    await _send_scheduled_checkin(panel, trust)
    assert trust.needs_session_relogin() is False

    clock["t"] = 11.0
    await _send_scheduled_checkin(panel, trust)
    assert trust.needs_session_relogin() is True


@pytest.mark.asyncio
async def test_arm_timeout_uses_command_fail_window_not_checkin_patience() -> None:
    """A silent or exhausted Arm timeout degrades Connection on the
    refused-command clock. A long hello-patience window must not delay that
    countdown.
    """
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    clock = {"t": 0.0}
    trust = _trust(
        mqtt,
        fail_window=10.0,
        checkin_patience=10_000.0,
        clock=lambda: clock["t"],
    )
    await trust.note_keepalive_ok()

    panel = MagicMock()
    panel.set_area_arm = AsyncMock(side_effect=TimeoutError("arm timed out"))
    panel.keepalive = AsyncMock(return_value=b"\x00" * 6)

    await handle_alarm_command(
        panel, _settings(), "ARM_AWAY", mqtt=mqtt, topic_prefix="texecom", trust=trust
    )
    assert trust.live is False
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    assert trust.needs_session_relogin() is False

    clock["t"] = 5.0
    await _send_scheduled_checkin(panel, trust)
    assert trust.needs_session_relogin() is False

    clock["t"] = 11.0
    await _send_scheduled_checkin(panel, trust)
    assert trust.needs_session_relogin() is True
