"""Unit tests for MQTT alarm command → panel arm/disarm mapping (ADR-005)."""

from __future__ import annotations

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
    """AREA exit/entry wins over a lagging GetAreaFlags settled decode."""
    from texecom_alarm.area_state import AREA_FLAGS_COUNT, FLAG_PART_ARM_2, FLAG_PART_ARMED

    flags = bytearray(AREA_FLAGS_COUNT)
    flags[FLAG_PART_ARMED] = 0x01
    flags[FLAG_PART_ARM_2] = 0x01
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.get_area_flags = AsyncMock(return_value=bytes(flags))
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

    assert result is None
    assert mqtt.payloads_for("texecom/alarm/state") == ["arming"]


@pytest.mark.asyncio
async def test_snapshot_forced_disconnect_records_trust() -> None:
    """ForcedDisconnect during post-command flags refresh must degrade Connection."""
    from texecom_alarm.panel_trust import PanelTrust
    from texecom_alarm.protocol.client import ForcedDisconnect

    panel = MagicMock()
    panel.set_area_disarm = AsyncMock()
    panel.get_area_flags = AsyncMock(side_effect=ForcedDisconnect("gone"))
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
    )

    assert result is None
    assert trust.live is False
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"


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
async def test_snapshot_nak_after_disarm_records_trust_without_retry() -> None:
    """Snapshot failure after ACK degrades trust; must not re-issue disarm."""
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
    )

    panel.set_area_disarm.assert_awaited_once_with()
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    assert trust.live is False
    assert result is None


@pytest.mark.asyncio
async def test_arm_nak_records_trust_failure_and_publishes_panel_link_off() -> None:
    """ADR-010: arm NAK flips Alarm Panel Connection OFF via PanelTrust."""
    from texecom_alarm.panel_trust import PanelTrust

    panel = MagicMock()
    panel.set_area_arm = AsyncMock(side_effect=ProtocolError("SETAREAARM NAK"))
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    trust = PanelTrust(mqtt, topic_prefix="texecom", zone_count=12)
    trust.note_keepalive_ok()

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
    """ADR-010: disarm NAK flips Alarm Panel Connection OFF."""
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
