"""Area-flags decode, MQTT snapshot, and live AREA push helpers (ADR-007)."""

from __future__ import annotations

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.area_state import (
    AREA_FLAGS_COUNT,
    decode_area_ha_state,
    flag_bit,
    handle_area_message,
    mqtt_payload_for_area_state,
    publish_area_state_snapshot,
)
from texecom_alarm.config import Settings
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.protocol.frame import CMD_GET_AREA_FLAGS


def _settings(**overrides: object) -> Settings:
    base = dict(
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


def _quiet_flags(area_size: int = 1) -> bytes:
    return bytes(AREA_FLAGS_COUNT * area_size)


def _set_flag(flags: bytearray, flag_index: int, area_number: int, *, area_size: int = 1) -> None:
    offset = flag_index * area_size
    value = int.from_bytes(flags[offset : offset + area_size], "little")
    value |= 1 << (area_number - 1)
    flags[offset : offset + area_size] = value.to_bytes(area_size, "little")


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (0, "disarmed"),
        (1, "arming"),
        (2, "pending"),
        (3, "armed_away"),
        (4, "arming"),
        (5, "triggered"),
        (6, "armed_night"),
        (7, "armed_home"),
    ],
)
def test_mqtt_payload_for_live_area_state(state: int, expected: str) -> None:
    assert mqtt_payload_for_area_state(state, _settings()) == expected


def test_mqtt_payload_for_live_part_arm_uses_remapped_settings() -> None:
    """AREA 6/7 are Part-Arm slots 1/2 — HA mode follows Settings (ADR-005)."""
    remapped = _settings(part_arm_1="home", part_arm_2="night", part_arm_3="unused")
    assert mqtt_payload_for_area_state(6, remapped) == "armed_home"
    assert mqtt_payload_for_area_state(7, remapped) == "armed_night"


def test_flag_bit_reads_area_bit() -> None:
    flags = bytearray(_quiet_flags())
    _set_flag(flags, 21, 1)  # Armed for area 1
    assert flag_bit(bytes(flags), 21, area_size=1, area_number=1) is True
    assert flag_bit(bytes(flags), 21, area_size=1, area_number=2) is False


def test_decode_quiet_flags_is_disarmed() -> None:
    settings = _settings()
    assert decode_area_ha_state(_quiet_flags(), area_size=1, area_number=1, settings=settings) == (
        "disarmed"
    )


def test_decode_alarm_bit_is_triggered() -> None:
    flags = bytearray(_quiet_flags())
    _set_flag(flags, 0, 1)  # Alarm
    settings = _settings()
    assert (
        decode_area_ha_state(bytes(flags), area_size=1, area_number=1, settings=settings)
        == "triggered"
    )


def test_decode_armed_full_is_armed_away() -> None:
    flags = bytearray(_quiet_flags())
    _set_flag(flags, 21, 1)  # Armed
    settings = _settings()
    assert (
        decode_area_ha_state(bytes(flags), area_size=1, area_number=1, settings=settings)
        == "armed_away"
    )


def test_decode_part_armed_slot_maps_via_settings() -> None:
    settings = _settings(part_arm_1="night", part_arm_2="home")
    flags_night = bytearray(_quiet_flags())
    _set_flag(flags_night, 23, 1)  # PartArmed
    _set_flag(flags_night, 50, 1)  # PartArm1
    assert (
        decode_area_ha_state(bytes(flags_night), area_size=1, area_number=1, settings=settings)
        == "armed_night"
    )

    flags_home = bytearray(_quiet_flags())
    _set_flag(flags_home, 23, 1)
    _set_flag(flags_home, 51, 1)  # PartArm2
    assert (
        decode_area_ha_state(bytes(flags_home), area_size=1, area_number=1, settings=settings)
        == "armed_home"
    )


@pytest.mark.asyncio
async def test_snapshot_publishes_area_1_disarmed_only() -> None:
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
        settings = _settings()

        await publish_area_state_snapshot(
            client,
            mqtt,
            settings=settings,
            topic_prefix="texecom",
            zone_count=12,
        )

        assert mqtt.payloads_for("texecom/alarm/state") == ["disarmed"]
        assert mqtt.messages[-1].retain is True
        assert CMD_GET_AREA_FLAGS in panel.commands_seen
        # No arm / disarm / omit during snapshot.
        forbidden = {4, 5, 6, 8, 9}
        assert forbidden.isdisjoint(panel.commands_seen)
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_handle_area_message_publishes_mapped_states() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    settings = _settings()
    # MSG_AREA, area 1, state 3 → armed_away
    published = await handle_area_message(
        mqtt, bytes([2, 1, 3]), settings=settings, topic_prefix="texecom"
    )
    assert published == "armed_away"
    assert mqtt.payloads_for("texecom/alarm/state") == ["armed_away"]

    published = await handle_area_message(
        mqtt, bytes([2, 1, 5]), settings=settings, topic_prefix="texecom"
    )
    assert published == "triggered"
    assert mqtt.payloads_for("texecom/alarm/state")[-1] == "triggered"

    # Unused area 2 — no publish.
    before = len(mqtt.messages)
    published = await handle_area_message(
        mqtt, bytes([2, 2, 3]), settings=settings, topic_prefix="texecom"
    )
    assert published is None
    assert len(mqtt.messages) == before


@pytest.mark.asyncio
async def test_handle_area_message_remapped_part_arm_publishes_correct_ha_mode() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    # Swap Night/Home slots vs defaults: slot 1 → Home, slot 2 → Night.
    settings = _settings(part_arm_1="home", part_arm_2="night", part_arm_3="unused")
    # AREA state 6 = Part Arm 1 → armed_home under remapped Settings.
    published = await handle_area_message(
        mqtt, bytes([2, 1, 6]), settings=settings, topic_prefix="texecom"
    )
    assert published == "armed_home"
    assert mqtt.payloads_for("texecom/alarm/state") == ["armed_home"]
    # AREA state 7 = Part Arm 2 → armed_night.
    published = await handle_area_message(
        mqtt, bytes([2, 1, 7]), settings=settings, topic_prefix="texecom"
    )
    assert published == "armed_night"
    assert mqtt.payloads_for("texecom/alarm/state")[-1] == "armed_night"


@pytest.mark.asyncio
async def test_handle_area_message_ignores_short_body() -> None:
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    published = await handle_area_message(
        mqtt, bytes([2, 1]), settings=_settings(), topic_prefix="texecom"
    )
    assert published is None
    assert mqtt.payloads_for("texecom/alarm/state") == []
