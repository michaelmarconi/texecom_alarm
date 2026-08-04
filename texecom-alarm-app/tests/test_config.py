"""Unit tests for typed add-on settings — no broker or panel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from texecom_alarm.config import (
    DEFAULT_MQTT_PORT,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_PANEL_PORT,
    DEFAULT_PART_ARM_AWAY,
    DEFAULT_PART_ARM_HOME,
    DEFAULT_PART_ARM_NIGHT,
    DEFAULT_RECONNECT_NORMAL_ATTEMPTS,
    DEFAULT_RECONNECT_NORMAL_INTERVAL_SECONDS,
    DEFAULT_RECONNECT_TRIGGER_ATTEMPTS,
    DEFAULT_RECONNECT_TRIGGER_INTERVAL_SECONDS,
    ConfigError,
    Settings,
    load_settings,
)


def _valid_options(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "panel_host": "192.168.1.183",
        "panel_port": DEFAULT_PANEL_PORT,
        "udl_password": "1234",
        "mqtt_host": "core-mosquitto",
        "mqtt_port": DEFAULT_MQTT_PORT,
        "mqtt_username": "",
        "mqtt_password": "",
        "mqtt_topic_prefix": DEFAULT_MQTT_TOPIC_PREFIX,
        "part_arm_away": DEFAULT_PART_ARM_AWAY,
        "part_arm_night": DEFAULT_PART_ARM_NIGHT,
        "part_arm_home": DEFAULT_PART_ARM_HOME,
        "reconnect_normal_attempts": DEFAULT_RECONNECT_NORMAL_ATTEMPTS,
        "reconnect_normal_interval_seconds": DEFAULT_RECONNECT_NORMAL_INTERVAL_SECONDS,
        "reconnect_trigger_attempts": DEFAULT_RECONNECT_TRIGGER_ATTEMPTS,
        "reconnect_trigger_interval_seconds": DEFAULT_RECONNECT_TRIGGER_INTERVAL_SECONDS,
    }
    data.update(overrides)
    return data


def test_load_settings_applies_schema_defaults() -> None:
    udl = "udl-test"
    settings = load_settings(
        {
            "panel_host": "10.0.0.2",
            "udl_password": udl,
            "mqtt_host": "mqtt.local",
        }
    )
    assert settings == Settings(
        panel_host="10.0.0.2",
        panel_port=DEFAULT_PANEL_PORT,
        udl_password=udl,
        mqtt_host="mqtt.local",
        mqtt_port=DEFAULT_MQTT_PORT,
        mqtt_username="",
        mqtt_password="",
        mqtt_topic_prefix=DEFAULT_MQTT_TOPIC_PREFIX,
        part_arm_away=DEFAULT_PART_ARM_AWAY,
        part_arm_night=DEFAULT_PART_ARM_NIGHT,
        part_arm_home=DEFAULT_PART_ARM_HOME,
        reconnect_normal_attempts=DEFAULT_RECONNECT_NORMAL_ATTEMPTS,
        reconnect_normal_interval_seconds=DEFAULT_RECONNECT_NORMAL_INTERVAL_SECONDS,
        reconnect_trigger_attempts=DEFAULT_RECONNECT_TRIGGER_ATTEMPTS,
        reconnect_trigger_interval_seconds=DEFAULT_RECONNECT_TRIGGER_INTERVAL_SECONDS,
    )


def test_reconnect_settings_defaults_and_overrides() -> None:
    defaults = load_settings(
        {
            "panel_host": "10.0.0.2",
            "udl_password": "udl",
            "mqtt_host": "mqtt.local",
        }
    )
    assert defaults.reconnect_normal_attempts == 4
    assert defaults.reconnect_normal_interval_seconds == 2.5
    assert defaults.reconnect_trigger_attempts == 18
    assert defaults.reconnect_trigger_interval_seconds == 5.0

    tuned = load_settings(
        _valid_options(
            reconnect_normal_attempts=2,
            reconnect_normal_interval_seconds=0.5,
            reconnect_trigger_attempts=6,
            reconnect_trigger_interval_seconds=1.25,
        )
    )
    assert tuned.reconnect_normal_attempts == 2
    assert tuned.reconnect_normal_interval_seconds == 0.5
    assert tuned.reconnect_trigger_attempts == 6
    assert tuned.reconnect_trigger_interval_seconds == 1.25


def test_invalid_reconnect_interval_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="reconnect_normal_interval_seconds"):
        load_settings(_valid_options(reconnect_normal_interval_seconds=-1))


def test_invalid_reconnect_interval_string_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="reconnect_trigger_interval_seconds"):
        load_settings(_valid_options(reconnect_trigger_interval_seconds="nope"))


def test_reconnect_settings_from_environ() -> None:
    settings = load_settings(
        environ={
            "TEXECOM_PANEL_HOST": "panel.env",
            "TEXECOM_UDL_PASSWORD": "udl",
            "TEXECOM_MQTT_HOST": "broker.env",
            "TEXECOM_RECONNECT_NORMAL_ATTEMPTS": "3",
            "TEXECOM_RECONNECT_NORMAL_INTERVAL_SECONDS": "1.5",
            "TEXECOM_RECONNECT_TRIGGER_ATTEMPTS": "9",
            "TEXECOM_RECONNECT_TRIGGER_INTERVAL_SECONDS": "3.0",
        },
        options_path="/nonexistent/options.json",
    )
    assert settings.reconnect_normal_attempts == 3
    assert settings.reconnect_normal_interval_seconds == 1.5
    assert settings.reconnect_trigger_attempts == 9
    assert settings.reconnect_trigger_interval_seconds == 3.0


def test_part_arm_mapping_parses_mode_bytes() -> None:
    settings = load_settings(_valid_options(part_arm_away=2, part_arm_night=0, part_arm_home=1))
    assert settings.part_arm_away == 2
    assert settings.part_arm_night == 0
    assert settings.part_arm_home == 1


@pytest.mark.parametrize(
    "missing_key",
    ["panel_host", "udl_password", "mqtt_host"],
)
def test_missing_required_option_raises_clear_error(missing_key: str) -> None:
    options = _valid_options()
    del options[missing_key]
    with pytest.raises(ConfigError, match=missing_key):
        load_settings(options)


@pytest.mark.parametrize(
    "missing_key",
    ["panel_host", "udl_password", "mqtt_host"],
)
def test_blank_required_option_raises_clear_error(missing_key: str) -> None:
    with pytest.raises(ConfigError, match=missing_key):
        load_settings(_valid_options(**{missing_key: "   "}))


def test_invalid_port_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="panel_port"):
        load_settings(_valid_options(panel_port=70000))


def test_invalid_part_arm_mode_byte_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="part_arm_home"):
        load_settings(_valid_options(part_arm_home=256))


def test_invalid_integer_string_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="mqtt_port"):
        load_settings(_valid_options(mqtt_port="not-a-number"))


def test_load_settings_from_options_file(tmp_path: Path) -> None:
    path = tmp_path / "options.json"
    path.write_text(json.dumps(_valid_options(panel_host="panel.lan")), encoding="utf-8")
    settings = load_settings(options_path=path, environ={})
    assert settings.panel_host == "panel.lan"
    assert settings.part_arm_away == DEFAULT_PART_ARM_AWAY


def test_load_settings_from_environ() -> None:
    settings = load_settings(
        environ={
            "TEXECOM_PANEL_HOST": "panel.env",
            "TEXECOM_UDL_PASSWORD": "udl",
            "TEXECOM_MQTT_HOST": "broker.env",
            "TEXECOM_PART_ARM_AWAY": "10",
            "TEXECOM_PART_ARM_NIGHT": "11",
            "TEXECOM_PART_ARM_HOME": "12",
        },
        options_path="/nonexistent/options.json",
    )
    assert settings.panel_host == "panel.env"
    assert settings.mqtt_host == "broker.env"
    assert settings.part_arm_away == 10
    assert settings.part_arm_night == 11
    assert settings.part_arm_home == 12


def test_invalid_options_json_raises_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "options.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ConfigError, match="failed to read options file"):
        load_settings(options_path=path, environ={})


def test_options_file_must_be_object(tmp_path: Path) -> None:
    path = tmp_path / "options.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON object"):
        load_settings(options_path=path, environ={})


def test_default_options_path_from_environ(tmp_path: Path) -> None:
    path = tmp_path / "options.json"
    path.write_text(json.dumps(_valid_options(panel_host="via-env-path")), encoding="utf-8")
    settings = load_settings(environ={"TEXECOM_OPTIONS_FILE": str(path)})
    assert settings.panel_host == "via-env-path"


def test_empty_mqtt_topic_prefix_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="mqtt_topic_prefix"):
        load_settings(_valid_options(mqtt_topic_prefix=""))


def test_non_string_required_option_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="panel_host must be a string"):
        load_settings(_valid_options(panel_host=123))


def test_non_string_optional_option_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="mqtt_username must be a string"):
        load_settings(_valid_options(mqtt_username=1))
