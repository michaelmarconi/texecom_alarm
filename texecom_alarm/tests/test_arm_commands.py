"""Unit tests for MQTT alarm command → panel arm/disarm mapping (ADR-008)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.arm_commands import handle_alarm_command
from texecom_alarm.config import Settings
from texecom_alarm.protocol.client import ProtocolError


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = dict(
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
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_byte"),
    [
        ("ARM_AWAY", 0),
        ("ARM_NIGHT", 1),
        ("ARM_HOME", 2),
        (b"ARM_AWAY", 0),
    ],
)
async def test_arm_payloads_call_set_area_arm_with_settings_mode(
    payload: str | bytes, expected_byte: int
) -> None:
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.set_area_disarm = AsyncMock()
    settings = _settings()

    await handle_alarm_command(panel, settings, payload)

    panel.set_area_arm.assert_awaited_once_with(expected_byte)
    panel.set_area_disarm.assert_not_awaited()


@pytest.mark.asyncio
async def test_disarm_payload_calls_set_area_disarm() -> None:
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.set_area_disarm = AsyncMock()

    await handle_alarm_command(panel, _settings(), "DISARM")

    panel.set_area_disarm.assert_awaited_once_with()
    panel.set_area_arm.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_payload_is_ignored() -> None:
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.set_area_disarm = AsyncMock()

    await handle_alarm_command(panel, _settings(), "ARM_VACATION")
    await handle_alarm_command(panel, _settings(), "")

    panel.set_area_arm.assert_not_awaited()
    panel.set_area_disarm.assert_not_awaited()


@pytest.mark.asyncio
async def test_remapped_part_arm_slots_change_mode_bytes() -> None:
    """Home/Night use configured slots; ARM_AWAY always full-arm byte 0 (ADR-008)."""
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    settings = _settings(part_arm_1="home", part_arm_2="unused", part_arm_3="night")

    await handle_alarm_command(panel, settings, "ARM_HOME")
    panel.set_area_arm.assert_awaited_once_with(1)

    panel.set_area_arm.reset_mock()
    await handle_alarm_command(panel, settings, "ARM_AWAY")
    panel.set_area_arm.assert_awaited_once_with(0)

    panel.set_area_arm.reset_mock()
    await handle_alarm_command(panel, settings, "ARM_NIGHT")
    panel.set_area_arm.assert_awaited_once_with(3)


@pytest.mark.asyncio
async def test_unmapped_home_mode_is_ignored() -> None:
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    settings = _settings(part_arm_1="night", part_arm_2="unused", part_arm_3="unused")

    await handle_alarm_command(panel, settings, "ARM_HOME")

    panel.set_area_arm.assert_not_awaited()


@pytest.mark.asyncio
async def test_arm_nak_republishes_current_alarm_state() -> None:
    """AC-1: panel NAK must republish last known state (no stuck HA selection)."""
    panel = MagicMock()
    panel.set_area_arm = AsyncMock(side_effect=ProtocolError("SETAREAARM NAK"))
    panel.set_area_disarm = AsyncMock()
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    settings = _settings()

    await handle_alarm_command(
        panel,
        settings,
        "ARM_HOME",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "disarmed",
    )

    panel.set_area_arm.assert_awaited_once_with(2)
    assert mqtt.payloads_for("texecom/alarm/state") == ["disarmed"]
    # Retained so HA refreshes selection even if the payload is unchanged.
    assert mqtt.messages[-1].retain is True


@pytest.mark.asyncio
async def test_arm_nak_republishes_live_state_after_midflight_update() -> None:
    """NAK must read live last-known state, not a snapshot frozen at command receipt."""
    live_state = {"payload": "disarmed"}

    async def arm_then_update_and_nak(_mode: int) -> None:
        live_state["payload"] = "armed_away"
        raise ProtocolError("SETAREAARM NAK")

    panel = MagicMock()
    panel.set_area_arm = AsyncMock(side_effect=arm_then_update_and_nak)
    panel.set_area_disarm = AsyncMock()
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()

    await handle_alarm_command(
        panel,
        _settings(),
        "ARM_HOME",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: live_state["payload"],
    )

    panel.set_area_arm.assert_awaited_once_with(2)
    assert mqtt.payloads_for("texecom/alarm/state") == ["armed_away"]
    assert mqtt.messages[-1].retain is True


@pytest.mark.asyncio
async def test_successful_arm_does_not_publish_optimistic_state() -> None:
    """Success must not invent armed_* without a panel read; stale disarmed flags are skipped."""
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    # Quiet flags after arm are lag — must not publish disarmed over a just-armed session.
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()

    result = await handle_alarm_command(
        panel,
        _settings(),
        "ARM_HOME",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "disarmed",
        zone_count=12,
    )

    panel.set_area_arm.assert_awaited_once_with(2)
    panel.get_area_flags.assert_awaited()
    assert mqtt.payloads_for("texecom/alarm/state") == []
    assert result is None
    assert "armed_home" not in mqtt.payloads_for("texecom/alarm/state")


@pytest.mark.asyncio
async def test_successful_arm_skips_refresh_when_live_is_arming() -> None:
    """AREA already published exit — do not send a flags read whose answer we have."""
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/alarm/state", "arming", retain=True)

    result = await handle_alarm_command(
        panel,
        _settings(),
        "ARM_HOME",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "arming",
        zone_count=12,
    )

    panel.get_area_flags.assert_not_awaited()
    assert result is None
    assert mqtt.payloads_for("texecom/alarm/state") == ["arming"]


@pytest.mark.asyncio
async def test_successful_arm_omits_flags_when_live_already_armed() -> None:
    """Live AREA already published armed_* — skip the post-ACK flags round-trip."""
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()

    result = await handle_alarm_command(
        panel,
        _settings(),
        "ARM_AWAY",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "armed_away",
        zone_count=12,
    )

    panel.set_area_arm.assert_awaited_once_with(0)
    panel.get_area_flags.assert_not_awaited()
    assert mqtt.payloads_for("texecom/alarm/state") == []
    assert result is None


@pytest.mark.asyncio
async def test_successful_disarm_omits_flags_when_live_already_disarmed() -> None:
    """Live AREA already published disarmed — skip the post-ACK flags round-trip."""
    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()

    result = await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "disarmed",
        zone_count=12,
    )

    panel.set_area_disarm.assert_awaited_once_with()
    panel.get_area_flags.assert_not_awaited()
    assert mqtt.payloads_for("texecom/alarm/state") == []
    assert result is None


@pytest.mark.asyncio
async def test_successful_home_disarm_reads_flags_when_live_still_armed() -> None:
    """Home disarm that omits AREA still reads flags and publishes disarmed."""
    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/alarm/state", "armed_home", retain=True)

    result = await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "armed_home",
        zone_count=12,
    )

    panel.get_area_flags.assert_awaited()
    assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"
    assert result == "disarmed"


@pytest.mark.asyncio
async def test_post_ack_flags_forced_disconnect_is_collision_not_failed_disarm() -> None:
    """After the panel ACK'd disarm, an unreadable flags read is a collision.

    Connection stays on and the miss is re-raised so the session can log in
    again. The tap itself is not recorded as a failed disarm.
    """
    from texecom_alarm.panel_trust import PanelTrust
    from texecom_alarm.protocol.client import ForcedDisconnect

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.get_area_flags = AsyncMock(side_effect=ForcedDisconnect("torn frame"))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12)

    with pytest.raises(ForcedDisconnect):
        await handle_alarm_command(
            panel,
            _settings(),
            "DISARM",
            mqtt=mqtt,
            topic_prefix="texecom",
            zone_count=12,
            trust=trust,
        )

    panel.set_area_disarm.assert_awaited_once_with()
    assert trust.live is True
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
    assert trust.consume_session_collision() is True


@pytest.mark.asyncio
async def test_post_ack_flags_forced_disconnect_is_collision_not_failed_arm() -> None:
    """After the panel ACK'd arm, an unreadable flags read is a collision."""
    from texecom_alarm.panel_trust import PanelTrust
    from texecom_alarm.protocol.client import ForcedDisconnect

    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.get_area_flags = AsyncMock(side_effect=ForcedDisconnect("torn frame"))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12)

    with pytest.raises(ForcedDisconnect):
        await handle_alarm_command(
            panel,
            _settings(),
            "ARM_AWAY",
            mqtt=mqtt,
            topic_prefix="texecom",
            zone_count=12,
            trust=trust,
        )

    panel.set_area_arm.assert_awaited_once_with(0)
    assert trust.live is True
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
    assert trust.consume_session_collision() is True


@pytest.mark.asyncio
async def test_successful_disarm_publishes_area_flags_snapshot() -> None:
    """After ACK, refresh HA from GetAreaFlags (Home disarm often omits AREA push)."""
    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()

    result = await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        zone_count=12,
    )

    panel.set_area_disarm.assert_awaited_once_with()
    panel.get_area_flags.assert_awaited()
    assert mqtt.payloads_for("texecom/alarm/state") == ["disarmed"]
    assert result == "disarmed"


@pytest.mark.asyncio
async def test_disarm_refresh_rereads_live_state_after_ack() -> None:
    """Guard must see post-ACK MQTT (e.g. arming), not the pre-command snapshot."""
    live_state = {"payload": "disarmed"}

    async def disarm_then_arming() -> None:
        live_state["payload"] = "arming"

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock(side_effect=disarm_then_arming)
    panel.get_area_flags = AsyncMock(return_value=bytes(72))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/alarm/state", "disarmed", retain=True)

    result = await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        zone_count=12,
        get_current_alarm_state=lambda: live_state["payload"],
    )

    assert result == "disarmed"
    assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"


@pytest.mark.asyncio
async def test_successful_arm_home_publishes_part_arm_snapshot() -> None:
    """Successful ARM_HOME snapshot uses the same Part-Arm decode as ADR-009."""
    from texecom_alarm.area_state import AREA_FLAGS_COUNT, FLAG_PART_ARM_2, FLAG_PART_ARMED

    flags = bytearray(AREA_FLAGS_COUNT)
    flags[FLAG_PART_ARMED] = 0x01
    flags[FLAG_PART_ARM_2] = 0x01
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(flags))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()

    result = await handle_alarm_command(
        panel,
        _settings(),
        "ARM_HOME",
        mqtt=mqtt,
        topic_prefix="texecom",
        zone_count=12,
    )

    assert mqtt.payloads_for("texecom/alarm/state") == ["armed_home"]
    assert result == "armed_home"


@pytest.mark.asyncio
async def test_flags_nak_after_disarm_ack_does_not_retry_disarm() -> None:
    """Housekeeping NAK after a successful disarm ACK must not send disarm again."""
    from texecom_alarm.panel_trust import PanelTrust

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.get_area_flags = AsyncMock(side_effect=ProtocolError("GetAreaFlags NAK"))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12)

    result = await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        zone_count=12,
        trust=trust,
        get_current_alarm_state=lambda: "armed_away",
    )

    panel.set_area_disarm.assert_awaited_once_with()
    panel.get_area_flags.assert_awaited()
    assert result is None


@pytest.mark.asyncio
async def test_flags_nak_after_disarm_ack_does_not_turn_connection_off() -> None:
    """Disarm already ACK'd; a rejected flags read is busy, not a failed disarm."""
    from texecom_alarm.panel_trust import PanelTrust

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.get_area_flags = AsyncMock(side_effect=ProtocolError("GetAreaFlags NAK"))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12)
    await trust.note_keepalive_ok()

    result = await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        zone_count=12,
        trust=trust,
        get_current_alarm_state=lambda: "armed_away",
    )

    panel.set_area_disarm.assert_awaited_once_with()
    panel.get_area_flags.assert_awaited()
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
    assert trust.live is True
    assert result is None


@pytest.mark.asyncio
async def test_flags_timeout_after_disarm_ack_does_not_turn_connection_off() -> None:
    """Disarm already ACK'd; a starved flags read is busy, not a failed disarm."""
    from texecom_alarm.panel_trust import PanelTrust

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.get_area_flags = AsyncMock(
        side_effect=TimeoutError("Panel at 192.168.1.51:10001 did not answer GetAreaFlags in time.")
    )
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12)
    await trust.note_keepalive_ok()

    result = await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        zone_count=12,
        trust=trust,
        get_current_alarm_state=lambda: "armed_away",
    )

    panel.set_area_disarm.assert_awaited_once_with()
    panel.get_area_flags.assert_awaited()
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
    assert trust.live is True
    assert result is None


@pytest.mark.asyncio
async def test_arm_nak_records_trust_failure_and_publishes_panel_link_off() -> None:
    """ADR-016: arm NAK flips Alarm Panel Connection OFF via PanelTrust."""
    from texecom_alarm.panel_trust import PanelTrust

    panel = MagicMock()
    panel.set_area_arm = AsyncMock(side_effect=ProtocolError("SETAREAARM NAK"))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12)
    await trust.note_keepalive_ok()

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
    assert mqtt.payloads_for("texecom/alarm/state") == ["disarmed"]
    assert trust.live is False


@pytest.mark.asyncio
async def test_disarm_nak_records_trust_failure() -> None:
    """ADR-016: disarm NAK flips Alarm Panel Connection OFF."""
    from texecom_alarm.panel_trust import PanelTrust

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock(side_effect=ProtocolError("SETAREADISARM NAK"))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12)

    await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        trust=trust,
    )

    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    assert trust.live is False


@pytest.mark.asyncio
async def test_arm_forced_disconnect_records_trust_without_reraise() -> None:
    """Session kill mid-arm must degrade Connection and not propagate."""
    from texecom_alarm.panel_trust import PanelTrust
    from texecom_alarm.protocol.client import ForcedDisconnect

    panel = MagicMock()
    panel.set_area_arm = AsyncMock(side_effect=ForcedDisconnect("panel +++"))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    await mqtt.publish("texecom/alarm/state", "disarmed", retain=True)
    trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12)

    result = await handle_alarm_command(
        panel,
        _settings(),
        "ARM_AWAY",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "disarmed",
        trust=trust,
    )

    panel.set_area_arm.assert_awaited_once()
    assert result is None
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    assert mqtt.payloads_for("texecom/alarm/state")[-1] == "disarmed"
    assert trust.live is False


@pytest.mark.asyncio
async def test_disarm_forced_disconnect_records_trust_without_reraise() -> None:
    from texecom_alarm.panel_trust import PanelTrust
    from texecom_alarm.protocol.client import ForcedDisconnect

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock(side_effect=ForcedDisconnect("panel +++"))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12)

    result = await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        mqtt=mqtt,
        topic_prefix="texecom",
        trust=trust,
    )

    panel.set_area_disarm.assert_awaited_once()
    assert result is None
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    assert trust.live is False
    assert mqtt.payloads_for("texecom/alarm/state") == []


def _ready(*, away: bool = True, home: bool = True, night: bool = True) -> SimpleNamespace:
    return SimpleNamespace(away=away, home=home, night=night)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "payload"),
    [
        ("away", "ARM_AWAY"),
        ("home", "ARM_HOME"),
        ("night", "ARM_NIGHT"),
    ],
)
async def test_unready_arm_does_not_call_panel_or_change_alarm_state(
    mode: str, payload: str
) -> None:
    """Matching ready flag off: no panel arm; MQTT arming then current; blocked event."""
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.set_area_disarm = AsyncMock()
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/alarm/state", "disarmed", retain=True)
    flags = {m: m == mode for m in ("away", "home", "night")}
    ready = _ready(**{k: not v for k, v in flags.items()})

    alarm_before = list(mqtt.payloads_for("texecom/alarm/state"))
    result = await handle_alarm_command(
        panel,
        _settings(),
        payload,
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "disarmed",
        ready_state=ready,
    )

    panel.set_area_arm.assert_not_awaited()
    panel.set_area_disarm.assert_not_awaited()
    assert result is None
    alarm_after = mqtt.payloads_for("texecom/alarm/state")
    assert alarm_after[len(alarm_before) :] == ["arming", "disarmed"]
    alarm_msgs = [m for m in mqtt.messages if m.topic == "texecom/alarm/state"]
    assert alarm_msgs[-1].retain is True
    assert alarm_msgs[-2].retain is True
    assert alarm_msgs[-2].payload == "arming"
    events = [m for m in mqtt.messages if m.topic == "texecom/blocked_arm/event"]
    assert events
    assert events[-1].retain is False
    body = json.loads(
        events[-1].payload if isinstance(events[-1].payload, str) else events[-1].payload.decode()
    )
    assert body["event_type"] == mode
    assert "reason" not in body
    assert "why" not in body


@pytest.mark.asyncio
async def test_disarm_ignores_ready_flags() -> None:
    """DISARM must reach the panel even when every ready flag is off."""
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.set_area_disarm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(72))

    await handle_alarm_command(
        panel,
        _settings(),
        "DISARM",
        ready_state=_ready(away=False, home=False, night=False),
        zone_count=12,
    )

    panel.set_area_disarm.assert_awaited_once()
    panel.set_area_arm.assert_not_awaited()


@pytest.mark.asyncio
async def test_ready_on_still_sends_arm() -> None:
    """Matching ready flag on: existing arm path is unchanged."""
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.set_area_disarm = AsyncMock()

    await handle_alarm_command(
        panel,
        _settings(),
        "ARM_AWAY",
        ready_state=_ready(),
    )

    panel.set_area_arm.assert_awaited_once_with(0)
    panel.set_area_disarm.assert_not_awaited()


@pytest.mark.asyncio
async def test_unready_arm_while_armed_republishes_armed_state() -> None:
    """Refuse while already armed: MQTT arming then that armed payload; do not disarm."""
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.set_area_disarm = AsyncMock()
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/alarm/state", "armed_home", retain=True)

    result = await handle_alarm_command(
        panel,
        _settings(),
        "ARM_AWAY",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "armed_home",
        ready_state=_ready(away=False, home=True, night=True),
    )

    panel.set_area_arm.assert_not_awaited()
    panel.set_area_disarm.assert_not_awaited()
    assert result is None
    alarm_payloads = mqtt.payloads_for("texecom/alarm/state")
    assert alarm_payloads == ["armed_home", "arming", "armed_home"]
    assert "disarmed" not in alarm_payloads
    alarm_msgs = [m for m in mqtt.messages if m.topic == "texecom/alarm/state"]
    assert alarm_msgs[-1].retain is True
    assert alarm_msgs[-2].payload == "arming"
    assert alarm_msgs[-2].retain is True
    events = [m for m in mqtt.messages if m.topic == "texecom/blocked_arm/event"]
    assert events
    body = json.loads(
        events[-1].payload if isinstance(events[-1].payload, str) else events[-1].payload.decode()
    )
    assert body["event_type"] == "away"
    assert "reason" not in body


@pytest.mark.asyncio
async def test_unready_arm_when_already_arming_skips_extra_arming_publish() -> None:
    """If MQTT is already arming, refuse still re-publishes current and does not arm."""
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.set_area_disarm = AsyncMock()
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/alarm/state", "arming", retain=True)

    result = await handle_alarm_command(
        panel,
        _settings(),
        "ARM_HOME",
        mqtt=mqtt,
        topic_prefix="texecom",
        get_current_alarm_state=lambda: "arming",
        ready_state=_ready(away=True, home=False, night=True),
    )

    panel.set_area_arm.assert_not_awaited()
    panel.set_area_disarm.assert_not_awaited()
    assert result is None
    assert mqtt.payloads_for("texecom/alarm/state") == ["arming", "arming"]
    events = [m for m in mqtt.messages if m.topic == "texecom/blocked_arm/event"]
    assert events
    body = json.loads(
        events[-1].payload if isinstance(events[-1].payload, str) else events[-1].payload.decode()
    )
    assert body["event_type"] == "home"
