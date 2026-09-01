"""Single-delay panel reconnect + panel-link connectivity sensor (ADR-004 / ADR-018 / ADR-019)."""

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
from texecom_alarm.mqtt.discovery import (
    AVAILABILITY_OFFLINE,
    AVAILABILITY_ONLINE,
    availability_topic,
)
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.protocol.frame import (
    CMD_GET_AREA_FLAGS,
    CMD_GET_ZONE_STATE,
    CMD_LOGIN,
    CMD_SETEVENTMESSAGES,
)
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
        "reconnect_delay_seconds": 0.01,
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
        "reconnect_delay_seconds": 5.0,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_reconnect_delay_seconds_is_the_single_configured_wait() -> None:
    """One configured delay covers every disconnect — no trigger-specific interval (ADR-019)."""
    settings = _static_settings()
    assert settings.reconnect_delay_seconds == 5.0


@pytest.mark.asyncio
async def test_reconnect_connectivity_and_resume_sequence() -> None:
    """Ordinary disconnect → OFF→ON, LOGIN+snapshots+events."""
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
async def test_reconnect_uses_same_delay_after_triggered() -> None:
    """Disconnect after a real trigger uses the same delay as any other drop (ADR-019)."""
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
        settings = _settings(panel, reconnect_delay_seconds=0.03)
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
            # The spy patches the shared asyncio.sleep, so it also catches this
            # test's own 0.02s polling waits — filter those out to isolate the
            # reconnect helper's own delay.
            reconnect_sleeps = [s for s in sleeps if abs(s - 0.02) > 1e-9]
            assert reconnect_sleeps, "expected at least one reconnect sleep"
            assert all(
                abs(s - 0.03) < 1e-9 for s in reconnect_sleeps
            ), f"expected the single configured delay throughout, got {sleeps}"

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
            sleep=instant_sleep,
        )

        assert panel.zone_detail_queries == detail_before
        assert sleeps == [settings.reconnect_delay_seconds]
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
async def test_reconnect_always_awaits_close_before_next_connect_attempt() -> None:
    """Reconnect must fully await close() (bounded or not) before opening a new
    connection — otherwise the app could try to log back in while its own
    abandoned socket still occupies the panel's single connection slot."""
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

        events: list[str] = []
        real_close = client.close
        real_connect = client.connect

        async def tracked_close() -> None:
            events.append("close_start")
            await asyncio.sleep(0.05)  # simulate a slow (bounded) close taking a moment
            await real_close()
            events.append("close_done")

        async def tracked_connect() -> None:
            events.append("connect_start")
            await real_connect()

        client.close = tracked_close  # type: ignore[method-assign]
        client.connect = tracked_connect  # type: ignore[method-assign]

        async def instant_sleep(_delay: float) -> None:
            return None

        await reconnect_after_disconnect(
            client,
            mqtt,
            settings=settings,
            zones=zones,
            zone_count=12,
            sleep=instant_sleep,
        )

        assert "close_done" in events and "connect_start" in events
        assert events.index("close_done") < events.index("connect_start")
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_reconnect_helper_retries_after_failed_attempt() -> None:
    """Failed connect attempts keep retrying indefinitely (no attempt cap, ADR-018)."""
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
            login_retries=0,
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
                # Fast patience (ADR-020) so a silenced keepalive still declares
                # the session dead well within this test's wait budget.
                trust_checkin_patience=0.15,
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
async def test_keepalive_nak_enters_reconnect_path() -> None:
    """TASK-45/ADR-016: a rejected mid-run keepalive must reconnect, not abort listen."""
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
            login_retries=0,
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
                # Fast patience (ADR-020) so an every-check-in NAK still declares
                # the session dead well within this test's wait budget.
                trust_checkin_patience=0.15,
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
        panel.nak_keepalive = True

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
async def test_keepalive_wrong_shape_transient_burst_does_not_flip_connection() -> None:
    """ADR-020: a transient burst of wrong-shaped keepalive replies that clears
    within the patience window must not flip Alarm Panel Connection or tear down
    the session — mirrors the 2026-08-27 'near miss' incident
    (docs/protocol-reference.md), now absorbed by the app-level patience window
    across scheduled check-ins rather than a same-call retry inside keepalive()."""
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
                # Two failed check-ins (~0.1s) must clear well inside patience.
                trust_checkin_patience=1.0,
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

        attempts_before = panel.keepalive_attempts
        panel.wrong_shape_keepalive_replies = 2  # recovers on the final (3rd) attempt

        for _ in range(200):
            if (
                panel.wrong_shape_keepalive_replies == 0
                and panel.keepalive_attempts > attempts_before
            ):
                break
            if task.done():
                exc = task.exception()
                if exc is not None:
                    raise exc
            await asyncio.sleep(0.02)

        # Give a further beat to prove Connection never degraded afterward either.
        await asyncio.sleep(0.3)
        link = mqtt.payloads_for("texecom/panel_connection/state")
        assert "OFF" not in link
        assert link[-1] == "ON"
        assert task.done() is False

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_keepalive_wrong_shape_sustained_failure_still_reconnects() -> None:
    """ADR-020: once wrong-shaped keepalive replies persist past the patience
    window (every scheduled check-in still wrong-shaped, no M traffic, never
    recovering), the app still degrades Connection and reconnects rather than
    hanging on a zombie session."""
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
                # Fast patience (ADR-020) so a never-recovering wrong-shaped
                # keepalive still declares the session dead within this test's
                # wait budget.
                trust_checkin_patience=0.15,
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
        panel.wrong_shape_keepalive_replies = 1000  # never recovers within the budget

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
async def test_busy_panel_refusing_check_ins_is_still_declared_dead_after_patience() -> None:
    """ADR-020: a panel that keeps pushing zone traffic while NAKing every
    scheduled check-in must still be declared dead once patience runs out.
    Unprompted chatter is not proof the panel answers when asked, so it must
    not hold the patience window open — otherwise a session that talks all day
    while refusing every request would stay a zombie with Connection wrongly
    reading ON."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    pump: asyncio.Task[None] | None = None
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
                trust_checkin_patience=0.15,
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
        panel.nak_keepalive = True  # cleared again by a fresh login

        async def keep_pushing() -> None:
            """Zone frames arriving faster than the check-in interval."""
            status = 0x01
            while True:
                try:
                    await panel.inject_zone_message(1, status)
                except (RuntimeError, OSError):
                    pass  # no client attached while the app is reconnecting
                status ^= 0x01
                await asyncio.sleep(0.01)

        pump = asyncio.create_task(keep_pushing())

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
        assert panel.seteventmessages_calls > setevent_before
        assert task.done() is False

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        if pump is not None:
            pump.cancel()
            try:
                await pump
            except asyncio.CancelledError:
                pass
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


@pytest.mark.asyncio
async def test_connection_reset_enters_reconnect_path() -> None:
    """TCP RST during listen must keep-trying reconnect (not abort forever)."""
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
            response_timeout=0.5,
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
        assert client._reader is not None

        async def _rst(_n: int = 4096) -> bytes:
            raise ConnectionResetError("Connection reset by peer")

        client._reader.read = _rst  # type: ignore[method-assign]

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
async def test_send_side_connection_reset_enters_reconnect_path() -> None:
    """A socket that dies while the app is *sending* must reconnect too.

    The receive half already normalises a dead socket; this breaks only the write
    half so the next scheduled check-in — not the reader — is what discovers it.
    """
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
            response_timeout=0.5,
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
        login_before = panel.commands_seen.count(CMD_LOGIN)
        assert client._writer is not None

        def _rst(_data: bytes) -> None:
            raise ConnectionResetError("Connection reset by peer")

        client._writer.write = _rst  # type: ignore[method-assign]

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
        # A fresh LOGIN reached the panel — the session really was rebuilt.
        assert panel.commands_seen.count(CMD_LOGIN) > login_before
        assert panel.seteventmessages_calls > setevent_before
        assert task.done() is False

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_unexpected_listen_failure_stops_the_app_instead_of_idling() -> None:
    """An unexpected listen-task failure must never leave the add-on alive-but-idle
    behind frozen entities — run() surfaces it so the process exits and Home
    Assistant's last will marks the add-on unavailable."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = _settings(panel)
        never = asyncio.Event()
        client = PanelClient(
            panel.host,
            panel.port,
            udl_password="1234",
            login_delay=0.0,
            response_timeout=0.5,
        )
        await client.connect()
        await client.login()

        with patch(
            "texecom_alarm.app._listen_panel_messages",
            new_callable=AsyncMock,
            side_effect=RuntimeError("listen boom"),
        ):
            with pytest.raises(RuntimeError, match="listen boom"):
                await asyncio.wait_for(
                    run(
                        settings,
                        panel=client,
                        mqtt=mqtt,
                        idle=never.wait,
                        idle_timeout=0.05,
                        trust_poll_interval=60.0,
                    ),
                    timeout=5.0,
                )

        assert mqtt.will_topic == availability_topic("texecom")
        assert mqtt.will_payload == AVAILABILITY_OFFLINE
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_unexpected_command_listener_failure_stops_the_app_instead_of_idling() -> None:
    """The MQTT command listener dying silently is the same class of bug as the
    listen task dying: the add-on must stop rather than keep running deaf to taps."""
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    try:
        mqtt = RecordingMqttPublisher()
        settings = _settings(panel)
        never = asyncio.Event()
        client = PanelClient(
            panel.host,
            panel.port,
            udl_password="1234",
            login_delay=0.0,
            response_timeout=0.5,
        )
        await client.connect()
        await client.login()

        with patch(
            "texecom_alarm.app._listen_alarm_commands",
            new_callable=AsyncMock,
            side_effect=RuntimeError("command boom"),
        ):
            with pytest.raises(RuntimeError, match="command boom"):
                await asyncio.wait_for(
                    run(
                        settings,
                        panel=client,
                        mqtt=mqtt,
                        idle=never.wait,
                        idle_timeout=0.05,
                        trust_poll_interval=60.0,
                    ),
                    timeout=5.0,
                )
        await client.close()
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_mqtt_publish_error_does_not_abort_listen() -> None:
    """A single MQTT publish failure must not kill the panel listen cycle."""
    from texecom_alarm.app import _listen_panel_messages
    from texecom_alarm.protocol.frame import MSG_ZONE

    mqtt = RecordingMqttPublisher()
    await mqtt.connect()
    await mqtt.publish("texecom/panel_connection/state", "ON", retain=True)

    panel = AsyncMock()
    zone_body = bytes([MSG_ZONE, 1, 0x01])

    class _Frame:
        body = zone_body

    publish_calls = {"n": 0}
    original_publish = mqtt.publish

    async def _flaky_publish(*args: object, **kwargs: object) -> None:
        publish_calls["n"] += 1
        if publish_calls["n"] == 1:
            raise RuntimeError("broker hiccup")
        await original_publish(*args, **kwargs)

    mqtt.publish = _flaky_publish  # type: ignore[method-assign]

    recv_n = {"n": 0}

    async def _recv(*, timeout: float = 1.0) -> object:
        recv_n["n"] += 1
        if recv_n["n"] == 1:
            return _Frame()
        await asyncio.sleep(timeout)
        raise TimeoutError("idle")

    panel.recv_message = _recv
    panel.keepalive = AsyncMock()

    settings = _static_settings()
    task = asyncio.create_task(
        _listen_panel_messages(
            panel,
            mqtt,
            settings=settings,
            topic_prefix="texecom",
            in_use_zones={1},
            alarm_state=_SharedAlarmState(payload="disarmed"),
            idle_timeout=0.05,
        )
    )
    await asyncio.sleep(0.15)
    assert task.done() is False, "listen must survive MQTT publish errors"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
