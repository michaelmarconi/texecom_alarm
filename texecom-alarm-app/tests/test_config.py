"""Unit tests for typed add-on settings — no broker or panel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from texecom_alarm.config import (
    DEFAULT_MQTT_PORT,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_PANEL_PORT,
    DEFAULT_PART_ARM_1,
    DEFAULT_PART_ARM_2,
    DEFAULT_PART_ARM_3,
    DEFAULT_RECONNECT_NORMAL_ATTEMPTS,
    DEFAULT_RECONNECT_NORMAL_INTERVAL_SECONDS,
    DEFAULT_RECONNECT_TRIGGER_ATTEMPTS,
    DEFAULT_RECONNECT_TRIGGER_INTERVAL_SECONDS,
    DEFAULT_UDL_PASSWORD,
    FULL_ARM_AWAY_MODE_BYTE,
    ConfigError,
    Settings,
    load_settings,
)


def _valid_options(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "panel_host": "192.0.2.10",
        "panel_port": DEFAULT_PANEL_PORT,
        "udl_password": DEFAULT_UDL_PASSWORD,
        "mqtt_host": "core-mosquitto",
        "mqtt_port": DEFAULT_MQTT_PORT,
        "mqtt_username": "",
        "mqtt_password": "",
        "mqtt_topic_prefix": DEFAULT_MQTT_TOPIC_PREFIX,
        "part_arm_1": DEFAULT_PART_ARM_1,
        "part_arm_2": DEFAULT_PART_ARM_2,
        "part_arm_3": DEFAULT_PART_ARM_3,
        "reconnect_normal_attempts": DEFAULT_RECONNECT_NORMAL_ATTEMPTS,
        "reconnect_normal_interval_seconds": DEFAULT_RECONNECT_NORMAL_INTERVAL_SECONDS,
        "reconnect_trigger_attempts": DEFAULT_RECONNECT_TRIGGER_ATTEMPTS,
        "reconnect_trigger_interval_seconds": DEFAULT_RECONNECT_TRIGGER_INTERVAL_SECONDS,
    }
    data.update(overrides)
    return data


def test_load_settings_applies_schema_defaults() -> None:
    settings = load_settings(
        {
            "panel_host": "10.0.0.2",
            "mqtt_host": "mqtt.local",
        }
    )
    assert settings == Settings(
        panel_host="10.0.0.2",
        panel_port=DEFAULT_PANEL_PORT,
        udl_password=DEFAULT_UDL_PASSWORD,
        mqtt_host="mqtt.local",
        mqtt_port=DEFAULT_MQTT_PORT,
        mqtt_username="",
        mqtt_password="",
        mqtt_topic_prefix=DEFAULT_MQTT_TOPIC_PREFIX,
        part_arm_1=DEFAULT_PART_ARM_1,
        part_arm_2=DEFAULT_PART_ARM_2,
        part_arm_3=DEFAULT_PART_ARM_3,
        reconnect_normal_attempts=DEFAULT_RECONNECT_NORMAL_ATTEMPTS,
        reconnect_normal_interval_seconds=DEFAULT_RECONNECT_NORMAL_INTERVAL_SECONDS,
        reconnect_trigger_attempts=DEFAULT_RECONNECT_TRIGGER_ATTEMPTS,
        reconnect_trigger_interval_seconds=DEFAULT_RECONNECT_TRIGGER_INTERVAL_SECONDS,
    )


def test_udl_password_defaults_to_factory_1234() -> None:
    settings = load_settings(
        {
            "panel_host": "10.0.0.2",
            "mqtt_host": "mqtt.local",
        }
    )
    assert settings.udl_password == "1234"

    overridden = load_settings(_valid_options(udl_password="custom-udl"))
    assert overridden.udl_password == "custom-udl"


def test_reconnect_settings_defaults_and_overrides() -> None:
    defaults = load_settings(
        {
            "panel_host": "10.0.0.2",
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


def test_part_arm_slot_defaults_and_mode_bytes() -> None:
    settings = load_settings(
        {
            "panel_host": "10.0.0.2",
            "mqtt_host": "mqtt.local",
        }
    )
    assert settings.part_arm_1 == "night"
    assert settings.part_arm_2 == "home"
    assert settings.part_arm_3 == "unused"
    assert settings.mode_byte_for_ha_mode("night") == 1
    assert settings.mode_byte_for_ha_mode("home") == 2
    assert settings.mode_byte_for_ha_mode("away") == FULL_ARM_AWAY_MODE_BYTE
    assert settings.ha_mode_for_part_arm_slot(3) is None
    assert "arm_night" in settings.supported_arm_features()
    assert "arm_home" in settings.supported_arm_features()
    assert "arm_away" in settings.supported_arm_features()


def test_part_arm_remapping_changes_mode_bytes() -> None:
    settings = load_settings(
        _valid_options(part_arm_1="home", part_arm_2="away", part_arm_3="night")
    )
    assert settings.mode_byte_for_ha_mode("home") == 1
    assert settings.mode_byte_for_ha_mode("away") == 2
    assert settings.mode_byte_for_ha_mode("night") == 3
    assert settings.supported_arm_features() == ["arm_home", "arm_away", "arm_night"]


def test_unused_slot_not_offered_as_arm_target() -> None:
    settings = load_settings(
        _valid_options(part_arm_1="night", part_arm_2="unused", part_arm_3="unused")
    )
    assert settings.mode_byte_for_ha_mode("night") == 1
    assert settings.mode_byte_for_ha_mode("home") is None
    features = settings.supported_arm_features()
    assert "arm_night" in features
    assert "arm_home" not in features
    assert "arm_away" in features  # full-arm Away when not on a Part-Arm slot


def test_duplicate_part_arm_mode_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="night"):
        load_settings(_valid_options(part_arm_1="night", part_arm_2="night"))


def test_invalid_part_arm_label_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="part_arm_1"):
        load_settings(_valid_options(part_arm_1="vacation"))


@pytest.mark.parametrize(
    "missing_key",
    ["panel_host", "mqtt_host"],
)
def test_missing_required_option_raises_clear_error(missing_key: str) -> None:
    options = _valid_options()
    del options[missing_key]
    with pytest.raises(ConfigError, match=missing_key):
        load_settings(options)


@pytest.mark.parametrize(
    "missing_key",
    ["panel_host", "mqtt_host"],
)
def test_blank_required_option_raises_clear_error(missing_key: str) -> None:
    with pytest.raises(ConfigError, match=missing_key):
        load_settings(_valid_options(**{missing_key: "   "}))


def test_invalid_port_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="panel_port"):
        load_settings(_valid_options(panel_port=70000))


def test_invalid_integer_string_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="mqtt_port"):
        load_settings(_valid_options(mqtt_port="not-a-number"))


def test_load_settings_from_options_file(tmp_path: Path) -> None:
    path = tmp_path / "options.json"
    path.write_text(json.dumps(_valid_options(panel_host="panel.lan")), encoding="utf-8")
    settings = load_settings(options_path=path, environ={})
    assert settings.panel_host == "panel.lan"
    assert settings.part_arm_1 == DEFAULT_PART_ARM_1


def test_load_settings_from_environ() -> None:
    settings = load_settings(
        environ={
            "TEXECOM_PANEL_HOST": "panel.env",
            "TEXECOM_UDL_PASSWORD": "udl",
            "TEXECOM_MQTT_HOST": "broker.env",
            "TEXECOM_PART_ARM_1": "away",
            "TEXECOM_PART_ARM_2": "night",
            "TEXECOM_PART_ARM_3": "home",
        },
        options_path="/nonexistent/options.json",
    )
    assert settings.panel_host == "panel.env"
    assert settings.mqtt_host == "broker.env"
    assert settings.part_arm_1 == "away"
    assert settings.part_arm_2 == "night"
    assert settings.part_arm_3 == "home"
    assert settings.mode_byte_for_ha_mode("away") == 1
    assert settings.mode_byte_for_ha_mode("night") == 2
    assert settings.mode_byte_for_ha_mode("home") == 3


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
