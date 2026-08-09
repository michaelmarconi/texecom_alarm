"""Startup first-login progressive backoff (spec-startup-login-backoff)."""

from __future__ import annotations

import asyncio
import logging
import re

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.app import run, startup_login_wait_seconds
from texecom_alarm.config import Settings
from texecom_alarm.protocol.client import PanelClient

# Accepted schedule: after k-th failure, min(5 × 2^(k-1), 30).
_EXPECTED_SCHEDULE = [5.0, 10.0, 20.0, 30.0, 30.0, 30.0, 30.0]


def _settings(panel: FakePanel) -> Settings:
    return Settings(
        panel_host=panel.host,
        panel_port=panel.port,
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


def test_startup_login_wait_schedule_shape() -> None:
    """Production schedule: 5 → 10 → 20 → 30, then 30 forever (never above cap)."""
    waits = [startup_login_wait_seconds(k) for k in range(1, len(_EXPECTED_SCHEDULE) + 1)]
    assert waits == _EXPECTED_SCHEDULE
    assert all(w <= 30.0 for w in waits)
    assert waits[0] < waits[1]  # increases at least once
    for earlier, later in zip(waits, waits[1:], strict=False):
        assert later >= earlier


async def _wait_until_online(mqtt: RecordingMqttPublisher, task: asyncio.Task[None]) -> None:
    for _ in range(400):
        if mqtt.connected and any(str(m.payload) == "online" for m in mqtt.messages):
            return
        if task.done():
            exc = task.exception()
            if exc is not None:
                raise exc
            raise AssertionError("run() finished before MQTT online")
        await asyncio.sleep(0.02)
    raise AssertionError("timed out waiting for MQTT online after startup retries")


async def _wait_until_monitoring(mqtt: RecordingMqttPublisher, task: asyncio.Task[None]) -> None:
    """Wait until post-login monitoring has published alarm + panel-link state.

    MQTT availability goes online during discovery, before zone/area snapshots and
    panel_link — so online alone is not enough for AC3 monitoring evidence.
    """
    for _ in range(400):
        has_online = mqtt.connected and any(str(m.payload) == "online" for m in mqtt.messages)
        has_alarm = any(m.topic.endswith("/alarm/state") for m in mqtt.messages)
        has_panel_link = any(
            m.topic.endswith("/panel_link/state") and str(m.payload) == "ON" for m in mqtt.messages
        )
        if has_online and has_alarm and has_panel_link:
            return
        if task.done():
            exc = task.exception()
            if exc is not None:
                raise exc
            raise AssertionError("run() finished before monitoring state published")
        await asyncio.sleep(0.02)
    raise AssertionError(
        "timed out waiting for alarm/state and panel_link/state after startup recovery"
    )


@pytest.mark.asyncio
async def test_startup_backoff_waits_grow_then_cap(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC1+AC2+AC4: recorded waits grow, cap at 30, logs name next wait."""
    real_init = PanelClient.__init__

    def _fast_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("response_timeout", 0.15)
        kwargs.setdefault("keepalive_retries", 0)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(PanelClient, "__init__", _fast_init)

    # Five failures → waits 5,10,20,30,30 then success on 6th attempt.
    fail_count = 5
    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    panel.drop_login_responses = fail_count
    mqtt = RecordingMqttPublisher()
    stop = asyncio.Event()
    sleeps: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    try:
        with caplog.at_level(logging.ERROR):
            task = asyncio.create_task(
                run(
                    _settings(panel),
                    mqtt=mqtt,
                    idle=stop.wait,
                    login_delay=0.0,
                    startup_sleep=_sleep,
                )
            )
            await _wait_until_online(mqtt, task)
            stop.set()
            await asyncio.wait_for(task, timeout=5.0)

        assert panel.drop_login_responses == 0
        assert len(sleeps) == fail_count
        assert sleeps == _EXPECTED_SCHEDULE[:fail_count]
        assert sleeps == sorted(sleeps)
        assert sleeps[0] < sleeps[1]
        assert all(w <= 30.0 for w in sleeps)
        assert sleeps[-1] == 30.0

        error_msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_msgs) >= fail_count
        wait_mentions = [
            float(m.group(1))
            for msg in error_msgs
            if (m := re.search(r"retrying in ([0-9.]+) seconds", msg))
        ]
        assert wait_mentions[:fail_count] == sleeps
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_startup_backoff_recovers_into_monitoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3: after several failed logins under backoff, success continues into monitoring."""
    real_init = PanelClient.__init__

    def _fast_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("response_timeout", 0.15)
        kwargs.setdefault("keepalive_retries", 0)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(PanelClient, "__init__", _fast_init)

    panel = FakePanel(
        udl_password="1234",
        zones=[FakeZone(number=1, zone_type=1, name="DOOR", status=0x00)],
        zone_count=12,
    )
    await panel.start()
    panel.drop_login_responses = 3
    mqtt = RecordingMqttPublisher()
    stop = asyncio.Event()
    sleeps: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    try:
        task = asyncio.create_task(
            run(
                _settings(panel),
                mqtt=mqtt,
                idle=stop.wait,
                login_delay=0.0,
                startup_sleep=_sleep,
            )
        )
        await _wait_until_monitoring(mqtt, task)

        # Monitoring path: discovery + zone/alarm state + panel-link live published.
        assert any("binary_sensor" in m.topic and "config" in m.topic for m in mqtt.messages)
        assert any(m.topic.endswith("/alarm/state") for m in mqtt.messages)
        assert any(
            m.topic.endswith("/panel_link/state") and str(m.payload) == "ON" for m in mqtt.messages
        )
        assert not task.done(), "process must stay running after recovery"

        stop.set()
        await asyncio.wait_for(task, timeout=5.0)
        assert sleeps == _EXPECTED_SCHEDULE[:3]
    finally:
        await panel.stop()
