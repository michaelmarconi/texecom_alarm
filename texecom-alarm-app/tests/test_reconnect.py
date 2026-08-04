"""Asymmetric reconnect + panel-link connectivity sensor (ADR-002 / ADR-004)."""

from __future__ import annotations

import asyncio

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.app import run
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
        "part_arm_away": 0,
        "part_arm_night": 1,
        "part_arm_home": 2,
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
        "part_arm_away": 0,
        "part_arm_night": 1,
        "part_arm_home": 2,
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
            if mqtt.payloads_for("texecom/panel_link/state"):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)
        assert mqtt.payloads_for("texecom/panel_link/state")[-1] == "ON"
        assert mqtt.payloads_for(availability_topic("texecom"))[-1] == AVAILABILITY_ONLINE

        # Snapshot + SETEVENTMESSAGES already happened at startup.
        cmds_before = list(panel.commands_seen)
        setevent_before = panel.seteventmessages_calls
        status_before = list(mqtt.payloads_for(availability_topic("texecom")))

        await panel.force_disconnect()

        for _ in range(200):
            link = mqtt.payloads_for("texecom/panel_link/state")
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

        link = mqtt.payloads_for("texecom/panel_link/state")
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
                link = mqtt.payloads_for("texecom/panel_link/state")
                if link.count("OFF") >= 1 and link[-1] == "ON":
                    break
                if task.done():
                    exc = task.exception()
                    if exc is not None:
                        raise exc
                await asyncio.sleep(0.02)

            assert mqtt.payloads_for("texecom/panel_link/state")[-1] == "ON"
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
        assert mqtt.payloads_for("texecom/panel_link/state")[0] == "OFF"
        assert mqtt.payloads_for("texecom/panel_link/state")[-1] == "ON"
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
        assert mqtt.payloads_for("texecom/panel_link/state")[0] == "OFF"
        assert mqtt.payloads_for("texecom/panel_link/state")[-1] == "ON"
        await client.close()
    finally:
        await panel.stop()
