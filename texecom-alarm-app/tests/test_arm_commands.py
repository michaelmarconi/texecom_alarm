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
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    settings = _settings(part_arm_1="home", part_arm_2="away", part_arm_3="night")

    await handle_alarm_command(panel, settings, "ARM_HOME")
    panel.set_area_arm.assert_awaited_once_with(1)

    panel.set_area_arm.reset_mock()
    await handle_alarm_command(panel, settings, "ARM_AWAY")
    panel.set_area_arm.assert_awaited_once_with(2)

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
        current_alarm_state="disarmed",
    )

    panel.set_area_arm.assert_awaited_once_with(2)
    assert mqtt.payloads_for("texecom/alarm/state") == ["disarmed"]
    # Retained so HA refreshes selection even if the payload is unchanged.
    assert mqtt.messages[-1].retain is True


@pytest.mark.asyncio
async def test_successful_arm_does_not_publish_optimistic_state() -> None:
    """AC-2 / ADR: success path waits for AREA/snapshot — no optimistic armed_*."""
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()

    await handle_alarm_command(
        panel,
        _settings(),
        "ARM_HOME",
        mqtt=mqtt,
        topic_prefix="texecom",
        current_alarm_state="disarmed",
    )

    panel.set_area_arm.assert_awaited_once_with(2)
    assert mqtt.payloads_for("texecom/alarm/state") == []
