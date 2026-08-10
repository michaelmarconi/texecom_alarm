"""Mid-run session heal after health-check death (ADR-011 / session-heal AC1/AC3/AC4)."""

from __future__ import annotations

import asyncio
import logging

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


async def _wait_until(predicate, *, task: asyncio.Task[None], ticks: int = 200) -> None:
    for _ in range(ticks):
        if predicate():
            return
        if task.done():
            exc = task.exception()
            if exc is not None:
                raise exc
            raise AssertionError("app task finished before condition was met")
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


@pytest.mark.asyncio
async def test_health_check_death_heals_without_restart() -> None:
    """AC1: unanswered mid-run keepalive → keep-trying reconnect → live + re-sync."""
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
        await _wait_until(
            lambda: mqtt.payloads_for("texecom/panel_connection/state")[-1:] == ["ON"],
            task=task,
        )
        assert mqtt.payloads_for(availability_topic("texecom"))[-1] == AVAILABILITY_ONLINE
        zone_before = mqtt.payloads_for("texecom/zone/1/state")[-1]
        alarm_before = mqtt.payloads_for("texecom/alarm/state")[-1]
        status_before = list(mqtt.payloads_for(availability_topic("texecom")))
        cmds_before = list(panel.commands_seen)
        setevent_before = panel.seteventmessages_calls

        panel.silence_keepalive = True

        await _wait_until(
            lambda: "OFF" in mqtt.payloads_for("texecom/panel_connection/state"),
            task=task,
            ticks=300,
        )
        assert task.done() is False
        # May already be recovering; last payload can be OFF or briefly ON after heal.
        assert mqtt.payloads_for("texecom/panel_connection/state").count("OFF") >= 1

        # Availability must not flip offline solely for panel recovery (ADR-004).
        status_mid = mqtt.payloads_for(availability_topic("texecom"))
        assert status_mid == status_before or status_mid[-1] == AVAILABILITY_ONLINE
        assert "offline" not in status_mid[len(status_before) :]
        assert mqtt.payloads_for("texecom/zone/1/state")[-1] == zone_before
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == alarm_before

        await _wait_until(
            lambda: (
                mqtt.payloads_for("texecom/panel_connection/state").count("OFF") >= 1
                and mqtt.payloads_for("texecom/panel_connection/state")[-1] == "ON"
                and panel.seteventmessages_calls > setevent_before
            ),
            task=task,
            ticks=300,
        )

        link = mqtt.payloads_for("texecom/panel_connection/state")
        assert "OFF" in link
        assert link[-1] == "ON"
        new_cmds = panel.commands_seen[len(cmds_before) :]
        assert CMD_LOGIN in new_cmds
        assert CMD_GET_ZONE_STATE in new_cmds
        assert CMD_GET_AREA_FLAGS in new_cmds
        assert CMD_SETEVENTMESSAGES in new_cmds
        assert mqtt.payloads_for(availability_topic("texecom"))[-1] == AVAILABILITY_ONLINE
        assert mqtt.payloads_for("texecom/zone/1/state")[-1] == zone_before
        assert mqtt.payloads_for("texecom/alarm/state")[-1] == alarm_before

        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()


@pytest.mark.asyncio
async def test_failing_health_check_recovery_stays_off_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC4: while reconnect still fails, Connection stays OFF; attempts at normal logs."""
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

        with caplog.at_level(logging.INFO):
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
            await _wait_until(
                lambda: mqtt.payloads_for("texecom/panel_connection/state")[-1:] == ["ON"],
                task=task,
            )
            status_before = list(mqtt.payloads_for(availability_topic("texecom")))

            # Kill health-check and refuse LOGIN so reconnect stays failing.
            panel.silence_keepalive = True
            panel.drop_login_responses = 50

            await _wait_until(
                lambda: mqtt.payloads_for("texecom/panel_connection/state")[-1:] == ["OFF"],
                task=task,
                ticks=300,
            )
            # Stay OFF across several failed reconnect attempts.
            for _ in range(40):
                assert task.done() is False
                assert mqtt.payloads_for("texecom/panel_connection/state")[-1] == "OFF"
                await asyncio.sleep(0.02)

            status_after = mqtt.payloads_for(availability_topic("texecom"))
            assert status_after == status_before or status_after[-1] == AVAILABILITY_ONLINE
            assert "offline" not in status_after[len(status_before) :]

            messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.INFO]
            assert any("Reconnecting" in m or "reconnect" in m.lower() for m in messages)
            assert any(
                "failed" in m.lower()
                or "keep trying" in m.lower()
                or "will keep trying" in m.lower()
                for m in messages
            )
            recovery_logs = [
                r
                for r in caplog.records
                if r.levelno >= logging.INFO
                and ("reconnect" in r.getMessage().lower() or "Reconnecting" in r.getMessage())
            ]
            assert recovery_logs, "recovery attempts/failures must appear at INFO+"

            stop.set()
            await asyncio.wait_for(task, timeout=2.0)
    finally:
        await panel.stop()
