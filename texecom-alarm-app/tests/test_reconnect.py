"""Asymmetric reconnect + panel-link connectivity sensor (ADR-002 / ADR-004)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.app import _listen_with_reconnect, _SharedAlarmState, run
from texecom_alarm.area_state import AREA_FLAGS_COUNT
from texecom_alarm.config import Settings
from texecom_alarm.mqtt.discovery import AVAILABILITY_ONLINE, availability_topic
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.protocol.frame import (
    CMD_GET_AREA_FLAGS,
    CMD_GET_ZONE_STATE,
    CMD_LOGIN,
    CMD_SETEVENTMESSAGES,
)
from texecom_alarm.reconnect import ReconnectProfile, select_reconnect_profile
from texecom_alarm.zones import Zone


def _quiet_flags(area_size: int = 1) -> bytes:
    return bytes(AREA_FLAGS_COUNT * area_size)


def _set_flag(flags: bytearray, flag_index: int, area_number: int, *, area_size: int = 1) -> None:
    offset = flag_index * area_size
    value = int.from_bytes(flags[offset : offset + area_size], "little")
    value |= 1 << (area_number - 1)
    flags[offset : offset + area_size] = value.to_bytes(area_size, "little")


def _settings(panel: FakePanel, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "panel_host": panel.host,
        "panel_port": panel.port,
        "udl_password": "1234",
        "mqtt_host": "127.0.0.1",
        "mqtt_port": 1883,
        "mqtt_username": "",
        "mqtt_password": "",
        "mqtt_topic_prefix": "texecom",
        "part_arm_1": "night",
        "part_arm_2": "home",
        "part_arm_3": "unused",
        "reconnect_normal_attempts": 2,
        "reconnect_normal_interval_seconds": 0.01,
        "reconnect_trigger_attempts": 3,
        "reconnect_trigger_interval_seconds": 0.02,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _static_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "panel_host": "127.0.0.1",
        "panel_port": 10001,
        "udl_password": "1234",
        "mqtt_host": "127.0.0.1",
        "mqtt_port": 1883,
        "mqtt_username": "",
        "mqtt_password": "",
        "mqtt_topic_prefix": "texecom",
        "part_arm_1": "night",
        "part_arm_2": "home",
        "part_arm_3": "unused",
        "reconnect_normal_attempts": 4,
        "reconnect_normal_interval_seconds": 2.5,
        "reconnect_trigger_attempts": 18,
        "reconnect_trigger_interval_seconds": 5.0,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_select_reconnect_profile_normal_when_not_triggered() -> None:
    settings = _static_settings()
    for payload in (None, "disarmed", "armed_away", "armed_home", "armed_night"):
        profile = select_reconnect_profile(settings, last_alarm_payload=payload)
        assert profile == ReconnectProfile(name="normal", attempts=4, interval_seconds=2.5)


def test_select_reconnect_profile_trigger_when_triggered() -> None:
    settings = _static_settings()
    profile = select_reconnect_profile(settings, last_alarm_payload="triggered")
    assert profile == ReconnectProfile(name="trigger", attempts=18, interval_seconds=5.0)


@pytest.mark.asyncio
async def test_reconnect_normal_budget_connectivity_and_resume_sequence() -> None:
    """AC-1: ordinary disconnect → normal budget, OFF→ON, LOGIN+snapshots+events."""
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
        settings = _settings(panel)
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
            if mqtt.payloads_for("texecom/panel_connection/state"):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
        assert mqtt.payloads_for(availability_topic("texecom"))[-1] == AVAILABILITY_ONLINE

        # Snapshot + SETEVENTMESSAGES already happened at startup.
        cmds_before = list(panel.commands_seen)
        setevent_before = panel.seteventmessages_calls
        status_before = list(mqtt.payloads_for(availability_topic("texecom")))

        await panel.force_disconnect()

        for _ in range(200):
            link = mqtt.payloads_for("texecom/panel_connection/state")
            resumed = (
                link.count("OFF") >= 1
                and link[-1] == "ON"
                and panel.seteventmessages_calls > setevent_before
            )
            if resumed:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        link = mqtt.payloads_for("texecom/panel_connection/state")
        assert "OFF" in link
        assert link[-1] == "ON"

        # Availability must not flip offline during panel-link recovery (ADR-004).
        status_after = mqtt.payloads_for(availability_topic("texecom"))
        assert status_after == status_before or status_after[-1] == AVAILABILITY_ONLINE
        assert "offline" not in status_after[len(status_before) :]

        # Post-reconnect resume: LOGIN + GetZoneState + GetAreaFlags + SETEVENTMESSAGES.
        new_cmds = panel.commands_seen[len(cmds_before) :]
        assert CMD_LOGIN in new_cmds
        assert CMD_GET_ZONE_STATE in new_cmds
        assert CMD_GET_AREA_FLAGS in new_cmds
        assert CMD_SETEVENTMESSAGES in new_cmds
        assert panel.seteventmessages_calls > setevent_before

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_reconnect_trigger_budget_after_triggered() -> None:
    """AC-2: disconnect after triggered uses longer trigger profile (shortened)."""
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
        # Distinct interval so a sleep spy can prove trigger profile selection.
        settings = _settings(
            panel,
            reconnect_normal_interval_seconds=0.01,
            reconnect_trigger_interval_seconds=0.05,
            reconnect_normal_attempts=2,
            reconnect_trigger_attempts=3,
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

        sleeps: list[float] = []
        real_sleep = asyncio.sleep

        async def spy_sleep(delay: float) -> None:
            sleeps.append(delay)
            await real_sleep(0)  # yield without waiting the full interval

        # Patch reconnect module sleep used by the helper.
        import texecom_alarm.reconnect as reconnect_mod

        original_sleep = reconnect_mod.asyncio.sleep
        reconnect_mod.asyncio.sleep = spy_sleep  # type: ignore[assignment]
        try:
            task = asyncio.create_task(run(settings, panel=client, mqtt=mqtt, idle=stop.wait))
            for _ in range(150):
                if mqtt.payloads_for("texecom/alarm/state"):
                    break
                if task.done():
                    exc = task.exception()
                    if exc is not None:
                        raise exc
                await asyncio.sleep(0.02)

            await panel.inject_area_message(area_number=1, state=5)  # triggered
            for _ in range(100):
                if mqtt.payloads_for("texecom/alarm/state")[-1] == "triggered":
                    break
                await asyncio.sleep(0.02)
            assert mqtt.payloads_for("texecom/alarm/state")[-1] == "triggered"

            sleeps.clear()
            await panel.force_disconnect()

            for _ in range(200):
                link = mqtt.payloads_for("texecom/panel_connection/state")
                if link.count("OFF") >= 1 and link[-1] == "ON":
                    break
                if task.done():
                    exc = task.exception()
                    if exc is not None:
                        raise exc
                await asyncio.sleep(0.02)

            assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
            assert any(
                abs(s - 0.05) < 1e-9 for s in sleeps
            ), f"expected trigger interval in {sleeps}"
            assert not any(
                abs(s - 0.01) < 1e-9 for s in sleeps
            ), f"normal interval leaked: {sleeps}"

            stop.set()
            await asyncio.wait_for(task, timeout=2.0)
        finally:
            reconnect_mod.asyncio.sleep = original_sleep  # type: ignore[assignment]
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_reconnect_helper_uses_existing_zones_no_reenumeration() -> None:
    """Resume must not re-run GETZONEDETAILS (architecture: LOGIN+snapshots+events)."""
    from texecom_alarm.reconnect import reconnect_after_disconnect

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
        await panel.force_disconnect()

        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        settings = _settings(panel)
        zones = [Zone(number=1, zone_type=1, name="DOOR")]
        detail_before = list(panel.zone_detail_queries)

        sleeps: list[float] = []

        async def instant_sleep(delay: float) -> None:
            sleeps.append(delay)

        await reconnect_after_disconnect(
            client,
            mqtt,
            settings=settings,
            zones=zones,
            zone_count=12,
            last_alarm_payload="disarmed",
            sleep=instant_sleep,
        )

        assert panel.zone_detail_queries == detail_before
        assert sleeps == [settings.reconnect_normal_interval_seconds]
        assert mqtt.payloads_for("texecom/panel_connection/state")[0] == "OFF"
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
        assert CMD_LOGIN in panel.commands_seen
        assert CMD_GET_ZONE_STATE in panel.commands_seen
        assert CMD_GET_AREA_FLAGS in panel.commands_seen
        assert CMD_SETEVENTMESSAGES in panel.commands_seen
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_reconnect_helper_retries_after_failed_attempt() -> None:
    """Failed connect attempts keep retrying; named budget does not exit the process."""
    from texecom_alarm.reconnect import reconnect_after_disconnect

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
        await panel.force_disconnect()

        mqtt = RecordingMqttPublisher()
        await mqtt.connect()
        settings = _settings(panel)
        zones = [Zone(number=1, zone_type=1, name="DOOR")]

        fails_left = {"n": 1}
        real_connect = client.connect

        async def flaky_connect() -> None:
            if fails_left["n"] > 0:
                fails_left["n"] -= 1
                raise OSError("connection refused")
            await real_connect()

        client.connect = flaky_connect  # type: ignore[method-assign]
        sleeps: list[float] = []

        async def instant_sleep(delay: float) -> None:
            sleeps.append(delay)

        payload = await reconnect_after_disconnect(
            client,
            mqtt,
            settings=settings,
            zones=zones,
            zone_count=12,
            last_alarm_payload="disarmed",
            sleep=instant_sleep,
        )
        assert payload == "disarmed"
        assert len(sleeps) == 2  # one failed attempt + one success
        assert mqtt.payloads_for("texecom/panel_connection/state")[0] == "OFF"
        assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_reconnect_publishes_trigger_snapshot_from_preserved_buffer() -> None:
    """After reconnect, enter-triggered snapshot uses pre-outage zone activity (ADR-004)."""
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
        settings = _settings(panel)
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

        # Next GetAreaFlags (post-reconnect snapshot) reports Alarm for area 1.
        triggered_flags = bytearray(_quiet_flags())
        _set_flag(triggered_flags, 0, 1)
        panel.area_flags_override = bytes(triggered_flags)

        await panel.force_disconnect()

        for _ in range(200):
            link = mqtt.payloads_for("texecom/panel_connection/state")
            attrs = mqtt.payloads_for("texecom/alarm/attributes")
            if link.count("OFF") >= 1 and link[-1] == "ON" and attrs:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "triggered"
        attrs = json.loads(mqtt.payloads_for("texecom/alarm/attributes")[-1])
        assert attrs["last_trigger_zone"] == 1
        assert isinstance(attrs["last_trigger_time"], str)

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_reconnect_already_triggered_does_not_invent_snapshot() -> None:
    """Already-triggered across reconnect must not invent a second snapshot (TASK-8)."""
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
        settings = _settings(panel)
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

        await panel.inject_area_message(area_number=1, state=5)  # triggered, empty buffer
        for _ in range(100):
            if mqtt.payloads_for("texecom/alarm/state")[-1] == "triggered":
                break
            await asyncio.sleep(0.02)
        attrs_before = list(mqtt.payloads_for("texecom/alarm/attributes"))

        triggered_flags = bytearray(_quiet_flags())
        _set_flag(triggered_flags, 0, 1)
        panel.area_flags_override = bytes(triggered_flags)

        await panel.force_disconnect()

        for _ in range(200):
            link = mqtt.payloads_for("texecom/panel_connection/state")
            if link.count("OFF") >= 1 and link[-1] == "ON":
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        assert mqtt.payloads_for("texecom/alarm/state")[-1] == "triggered"
        # No additional invent on already-triggered → already-triggered edge.
        assert mqtt.payloads_for("texecom/alarm/attributes") == attrs_before

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_keepalive_timeout_enters_reconnect_path() -> None:
    """ADR-011: unanswered mid-run keepalive must reconnect, not abort listen."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = _settings(panel)
        stop = asyncio.Event()
        client = PanelClient(
            panel.host,
            panel.port,
            udl_password="1234",
            login_delay=0.0,
            response_timeout=0.2,
            keepalive_retries=0,
        )
        await client.connect()
        await client.login()

        task = asyncio.create_task(
            run(
                settings,
                panel=client,
                mqtt=mqtt,
                idle=stop.wait,
                idle_timeout=0.05,
                trust_poll_interval=60.0,
            )
        )
        for _ in range(150):
            if mqtt.payloads_for("texecom/panel_connection/state")[-1:] == ["ON"]:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        setevent_before = panel.seteventmessages_calls
        panel.silence_keepalive = True

        for _ in range(300):
            link = mqtt.payloads_for("texecom/panel_connection/state")
            resumed = (
                link.count("OFF") >= 1
                and link[-1] == "ON"
                and panel.seteventmessages_calls > setevent_before
            )
            if resumed:
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        link = mqtt.payloads_for("texecom/panel_connection/state")
        assert "OFF" in link
        assert link[-1] == "ON"
        assert task.done() is False

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_non_recoverable_listen_failure_publishes_panel_link_off() -> None:
    """Listen crash must flip panel-link OFF; must not touch alarm/zone availability."""
    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)
    await mqtt.publish(availability_topic("texecom"), AVAILABILITY_ONLINE, retain=True)
    settings = _static_settings()
    zones = [Zone(number=1, zone_type=1, name="DOOR")]

    with patch(
        "texecom_alarm.app._listen_panel_messages",
        new_callable=AsyncMock,
        side_effect=RuntimeError("listen boom"),
    ):
        with pytest.raises(RuntimeError, match="listen boom"):
            await _listen_with_reconnect(
                AsyncMock(),
                mqtt,
                settings=settings,
                zones=zones,
                zone_count=12,
                topic_prefix="texecom",
                in_use_zones={1},
                alarm_state=_SharedAlarmState(payload="disarmed"),
            )

    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
    # Availability unchanged — only app LWT / clean shutdown may flip it (ADR-004).
    assert mqtt.payloads_for(availability_topic("texecom")) == [AVAILABILITY_ONLINE]
