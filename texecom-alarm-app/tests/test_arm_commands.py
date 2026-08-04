"""Unit tests for MQTT alarm command → panel arm/disarm mapping (ADR-005)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from texecom_alarm.arm_commands import handle_alarm_command
from texecom_alarm.config import Settings


def _settings(**overrides: int) -> Settings:
    base = dict(
        panel_host="127.0.0.1",
        panel_port=10001,
        udl_password="1234",
        mqtt_host="127.0.0.1",
        mqtt_port=1883,
        mqtt_username="",
        mqtt_password="",
        mqtt_topic_prefix="texecom",
        part_arm_away=0,
        part_arm_night=1,
        part_arm_home=2,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "mode_attr"),
    [
        ("ARM_AWAY", "part_arm_away"),
        ("ARM_NIGHT", "part_arm_night"),
        ("ARM_HOME", "part_arm_home"),
        (b"ARM_AWAY", "part_arm_away"),
    ],
)
async def test_arm_payloads_call_set_area_arm_with_settings_mode(
    payload: str | bytes, mode_attr: str
) -> None:
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    panel.set_area_disarm = AsyncMock()
    settings = _settings(part_arm_away=10, part_arm_night=11, part_arm_home=12)

    await handle_alarm_command(panel, settings, payload)

    panel.set_area_arm.assert_awaited_once_with(getattr(settings, mode_attr))
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
async def test_remapped_part_arm_bytes_are_used() -> None:
    panel = MagicMock()
    panel.set_area_arm = AsyncMock()
    settings = _settings(part_arm_away=7, part_arm_night=8, part_arm_home=9)

    await handle_alarm_command(panel, settings, "ARM_HOME")

    panel.set_area_arm.assert_awaited_once_with(9)
