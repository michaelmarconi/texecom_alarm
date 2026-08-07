"""Operator-facing error text must be readable without reading the codebase."""

from __future__ import annotations

import asyncio
import logging

import pytest
from tests.fake_panel import FakePanel, FakeZone
from tests.recording_mqtt import RecordingMqttPublisher

from texecom_alarm.app import run
from texecom_alarm.config import Settings
from texecom_alarm.protocol.client import PanelClient
from texecom_alarm.protocol.frame import CMD_LOGIN


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


def test_login_timeout_message_is_operator_readable() -> None:
    text = PanelClient.timeout_message(CMD_LOGIN, host="192.0.2.10", port=10001)
    assert "LOGIN" in text or "login" in text.lower()
    assert "192.0.2.10" in text
    assert "10001" in text
    assert text != "timed out waiting for frame"
    lowered = text.lower()
    assert "another" in lowered or "comip" in lowered or "busy" in lowered


def test_protocol_error_login_message_is_operator_readable() -> None:
    text = PanelClient.login_failure_message(b"\x15").lower()
    assert "login" in text
    assert "password" in text or "udl" in text


@pytest.mark.asyncio
async def test_startup_retries_silent_login_then_succeeds(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First LOGIN timeouts must keep the process alive and retry (continuous-operation)."""
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
    panel.drop_login_responses = 2
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
                    startup_retry_interval=0.01,
                    startup_sleep=_sleep,
                )
            )
            for _ in range(200):
                if mqtt.connected and any(str(m.payload) == "online" for m in mqtt.messages):
                    break
                if task.done():
                    exc = task.exception()
                    if exc is not None:
                        raise exc
                    break
                await asyncio.sleep(0.02)

            assert mqtt.connected
            assert any(str(m.payload) == "online" for m in mqtt.messages)
            error_msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
            assert error_msgs, "expected ERROR logs while LOGIN was silent"
            joined = " ".join(error_msgs).lower()
            assert "login" in joined or "panel" in joined
            assert "another" in joined or "comip" in joined or "busy" in joined or "retry" in joined
            stop.set()
            await asyncio.wait_for(task, timeout=5.0)
        assert panel.drop_login_responses == 0
        assert sleeps, "expected backoff sleeps between startup retries"
    finally:
        await panel.stop()
