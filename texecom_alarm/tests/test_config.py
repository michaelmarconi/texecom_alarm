"""Unit tests for typed add-on settings — no broker or panel."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from texecom_alarm.config import (
    DEFAULT_CHECKIN_INTERVAL_SECONDS,
    DEFAULT_CHECKIN_PATIENCE_SECONDS,
    DEFAULT_MQTT_PORT,
    DEFAULT_MQTT_TOPIC_PREFIX,
    DEFAULT_PANEL_PORT,
    DEFAULT_PART_ARM_1,
    DEFAULT_PART_ARM_2,
    DEFAULT_PART_ARM_3,
    DEFAULT_RECONCILIATION_POLL_INTERVAL_SECONDS,
    DEFAULT_RECONNECT_DELAY_SECONDS,
    DEFAULT_TRUST_FAIL_WINDOW_SECONDS,
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
        "reconnect_delay_seconds": DEFAULT_RECONNECT_DELAY_SECONDS,
        "trust_fail_window_seconds": DEFAULT_TRUST_FAIL_WINDOW_SECONDS,
        "reconciliation_poll_interval_seconds": DEFAULT_RECONCILIATION_POLL_INTERVAL_SECONDS,
        "checkin_interval_seconds": DEFAULT_CHECKIN_INTERVAL_SECONDS,
        "checkin_patience_seconds": DEFAULT_CHECKIN_PATIENCE_SECONDS,
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
        reconnect_delay_seconds=DEFAULT_RECONNECT_DELAY_SECONDS,
        trust_fail_window_seconds=DEFAULT_TRUST_FAIL_WINDOW_SECONDS,
        reconciliation_poll_interval_seconds=DEFAULT_RECONCILIATION_POLL_INTERVAL_SECONDS,
        checkin_interval_seconds=DEFAULT_CHECKIN_INTERVAL_SECONDS,
        checkin_patience_seconds=DEFAULT_CHECKIN_PATIENCE_SECONDS,
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


def test_settings_repr_hides_passwords() -> None:
    settings = load_settings(_valid_options(udl_password="secret-udl", mqtt_password="secret-mqtt"))
    text = repr(settings)
    assert "secret-udl" not in text
    assert "secret-mqtt" not in text


def test_factory_udl_warns_without_logging_password(caplog: pytest.LogCaptureFixture) -> None:
    from texecom_alarm.config import warn_if_factory_udl

    with caplog.at_level(logging.INFO, logger="texecom_alarm.config"):
        warn_if_factory_udl(load_settings(_valid_options(udl_password="1234")))
    assert any("factory-default UDL" in r.message for r in caplog.records)
    assert all("1234" not in r.message for r in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="texecom_alarm.config"):
        warn_if_factory_udl(load_settings(_valid_options(udl_password="custom")))
    assert not any("factory-default UDL" in r.message for r in caplog.records)


def test_reconnect_delay_defaults_and_overrides() -> None:
    defaults = load_settings(
        {
            "panel_host": "10.0.0.2",
            "mqtt_host": "mqtt.local",
        }
    )
    assert defaults.reconnect_delay_seconds == 5.0
    assert defaults.trust_fail_window_seconds == 90.0

    tuned = load_settings(
        _valid_options(
            reconnect_delay_seconds=0.5,
            trust_fail_window_seconds=45.0,
        )
    )
    assert tuned.reconnect_delay_seconds == 0.5
    assert tuned.trust_fail_window_seconds == 45.0


def test_reconciliation_poll_interval_defaults_to_five_minutes() -> None:
    """AC1: unset add-on option → 300s default (ADR-017)."""
    defaults = load_settings(
        {
            "panel_host": "10.0.0.2",
            "mqtt_host": "mqtt.local",
        }
    )
    assert defaults.reconciliation_poll_interval_seconds == 300.0
    assert DEFAULT_RECONCILIATION_POLL_INTERVAL_SECONDS == 300.0


def test_reconciliation_poll_interval_override_via_options() -> None:
    """AC2: add-on option changes the parsed interval."""
    tuned = load_settings(_valid_options(reconciliation_poll_interval_seconds=60.0))
    assert tuned.reconciliation_poll_interval_seconds == 60.0


def test_reconciliation_poll_interval_from_environ() -> None:
    settings = load_settings(
        environ={
            "TEXECOM_PANEL_HOST": "panel.env",
            "TEXECOM_UDL_PASSWORD": "udl",
            "TEXECOM_MQTT_HOST": "broker.env",
            "TEXECOM_RECONCILIATION_POLL_INTERVAL_SECONDS": "120",
        },
        options_path="/nonexistent/options.json",
    )
    assert settings.reconciliation_poll_interval_seconds == 120.0


def test_invalid_reconciliation_poll_interval_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="reconciliation_poll_interval_seconds"):
        load_settings(_valid_options(reconciliation_poll_interval_seconds=-1))


def test_checkin_settings_defaults() -> None:
    """AC1: unset add-on options fall back to documented defaults (ADR-020)."""
    defaults = load_settings(
        {
            "panel_host": "10.0.0.2",
            "mqtt_host": "mqtt.local",
        }
    )
    assert defaults.checkin_interval_seconds == 15.0
    assert defaults.checkin_patience_seconds == 45.0
    assert DEFAULT_CHECKIN_INTERVAL_SECONDS == 15.0
    assert DEFAULT_CHECKIN_PATIENCE_SECONDS == 45.0


def test_checkin_settings_override_via_options() -> None:
    """AC2: add-on options change the parsed cadence and patience."""
    tuned = load_settings(
        _valid_options(checkin_interval_seconds=10.0, checkin_patience_seconds=30.0)
    )
    assert tuned.checkin_interval_seconds == 10.0
    assert tuned.checkin_patience_seconds == 30.0


def test_checkin_settings_override_via_environ() -> None:
    """AC2: the equivalent environment variables override too."""
    settings = load_settings(
        environ={
            "TEXECOM_PANEL_HOST": "panel.env",
            "TEXECOM_UDL_PASSWORD": "udl",
            "TEXECOM_MQTT_HOST": "broker.env",
            "TEXECOM_CHECKIN_INTERVAL_SECONDS": "20",
            "TEXECOM_CHECKIN_PATIENCE_SECONDS": "60",
        },
        options_path="/nonexistent/options.json",
    )
    assert settings.checkin_interval_seconds == 20.0
    assert settings.checkin_patience_seconds == 60.0


def test_checkin_patience_shorter_than_interval_raises_clear_error() -> None:
    """AC3: patience shorter than one check-in interval is rejected."""
    with pytest.raises(ConfigError, match="checkin_patience_seconds"):
        load_settings(_valid_options(checkin_interval_seconds=15.0, checkin_patience_seconds=10.0))


def test_checkin_patience_equal_to_interval_is_allowed() -> None:
    """Patience exactly one interval is the boundary case, not rejected."""
    settings = load_settings(
        _valid_options(checkin_interval_seconds=15.0, checkin_patience_seconds=15.0)
    )
    assert settings.checkin_interval_seconds == 15.0
    assert settings.checkin_patience_seconds == 15.0


def test_invalid_checkin_interval_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="checkin_interval_seconds"):
        load_settings(_valid_options(checkin_interval_seconds=-1))


def test_invalid_checkin_patience_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="checkin_patience_seconds"):
        load_settings(_valid_options(checkin_patience_seconds="nope"))


def test_invalid_trust_fail_window_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="trust_fail_window_seconds"):
        load_settings(_valid_options(trust_fail_window_seconds=-1))


def test_invalid_reconnect_delay_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="reconnect_delay_seconds"):
        load_settings(_valid_options(reconnect_delay_seconds=-1))


def test_invalid_reconnect_delay_string_raises_clear_error() -> None:
    with pytest.raises(ConfigError, match="reconnect_delay_seconds"):
        load_settings(_valid_options(reconnect_delay_seconds="nope"))


def test_reconnect_delay_from_environ() -> None:
    settings = load_settings(
        environ={
            "TEXECOM_PANEL_HOST": "panel.env",
            "TEXECOM_UDL_PASSWORD": "udl",
            "TEXECOM_MQTT_HOST": "broker.env",
            "TEXECOM_RECONNECT_DELAY_SECONDS": "1.5",
            "TEXECOM_TRUST_FAIL_WINDOW_SECONDS": "120",
        },
        options_path="/nonexistent/options.json",
    )
    assert settings.reconnect_delay_seconds == 1.5
    assert settings.trust_fail_window_seconds == 120.0


def test_part_arm_slot_defaults_and_mode_bytes() -> None:
    settings = load_settings(
        {
            "panel_host": "10.0.0.2",
            "mqtt_host": "mqtt.local",
        }
    )
    assert settings.part_arm_1 == "unused"
    assert settings.part_arm_2 == "unused"
    assert settings.part_arm_3 == "unused"
    assert settings.mode_byte_for_ha_mode("night") is None
    assert settings.mode_byte_for_ha_mode("home") is None
    assert settings.mode_byte_for_ha_mode("away") == FULL_ARM_AWAY_MODE_BYTE
    assert settings.ha_mode_for_part_arm_slot(1) is None
    assert settings.ha_mode_for_part_arm_slot(2) is None
    assert settings.ha_mode_for_part_arm_slot(3) is None
    assert settings.supported_arm_features() == ["arm_away"]


def test_part_arm_supervisor_display_labels_parse_to_canonical() -> None:
    """Python still normalises Title Case + emoji if present; Settings stay canonical."""
    settings = load_settings(
        _valid_options(
            part_arm_1="Night 🌙",
            part_arm_2="Home 🏠",
            part_arm_3="Unused",
        )
    )
    assert settings.part_arm_1 == "night"
    assert settings.part_arm_2 == "home"
    assert settings.part_arm_3 == "unused"
    assert settings.mode_byte_for_ha_mode("night") == 1
    assert settings.mode_byte_for_ha_mode("home") == 2
    assert settings.mode_byte_for_ha_mode("away") == FULL_ARM_AWAY_MODE_BYTE


def test_addon_config_schema_uses_display_part_arm_tokens() -> None:
    """Supervisor list(...) tokens are the Configuration radio labels (ADR-008).

    Schema must use Title Case + emoji display tokens for Home / Night / Unused
    only — Away is never a Part-Arm option. Settings still normalise both
    display and legacy lowercase forms to canonical home|night|unused.
    """
    config_path = Path(__file__).resolve().parents[1] / "config.yaml"
    text = config_path.read_text(encoding="utf-8")
    display_list = "list(Home 🏠|Night 🌙|Unused)"
    for slot in ("part_arm_1", "part_arm_2", "part_arm_3"):
        assert f"{slot}: {display_list}" in text
        assert f"{slot}: Unused" in text
    assert "Away 🔒" not in text
    assert "list(home|night|away|unused)" not in text
    assert "list(Home 🏠|Night 🌙|Away 🔒|Unused)" not in text

    display = load_settings(
        _valid_options(
            part_arm_1="Home 🏠",
            part_arm_2="Night 🌙",
            part_arm_3="Unused",
        )
    )
    assert display.part_arm_1 == "home"
    assert display.part_arm_2 == "night"
    assert display.part_arm_3 == "unused"


def test_legacy_away_slot_coerces_to_unused(caplog: pytest.LogCaptureFixture) -> None:
    """Persisted Away on a Part-Arm slot migrates to Unused (ADR-008)."""
    with caplog.at_level(logging.WARNING, logger="texecom_alarm.config"):
        settings = load_settings(
            _valid_options(part_arm_1="home", part_arm_2="night", part_arm_3="away")
        )
    assert settings.part_arm_1 == "home"
    assert settings.part_arm_2 == "night"
    assert settings.part_arm_3 == "unused"
    assert settings.mode_byte_for_ha_mode("away") == FULL_ARM_AWAY_MODE_BYTE
    assert settings.ha_mode_for_part_arm_slot(3) is None
    assert any("Away" in r.message and "part_arm_3" in r.message for r in caplog.records)

    with caplog.at_level(logging.WARNING, logger="texecom_alarm.config"):
        display_away = load_settings(_valid_options(part_arm_1="Away 🔒"))
    assert display_away.part_arm_1 == "unused"
    assert display_away.mode_byte_for_ha_mode("away") == FULL_ARM_AWAY_MODE_BYTE


def test_part_arm_remapping_changes_mode_bytes() -> None:
    """Home/Night remap across slots; Away is always full-arm byte 0 (ADR-008)."""
    settings = load_settings(
        _valid_options(part_arm_1="home", part_arm_2="unused", part_arm_3="night")
    )
    assert settings.mode_byte_for_ha_mode("home") == 1
    assert settings.mode_byte_for_ha_mode("night") == 3
    assert settings.mode_byte_for_ha_mode("away") == FULL_ARM_AWAY_MODE_BYTE
    assert settings.ha_mode_for_part_arm_slot(1) == "home"
    assert settings.ha_mode_for_part_arm_slot(2) is None
    assert settings.ha_mode_for_part_arm_slot(3) == "night"
    assert settings.supported_arm_features() == ["arm_home", "arm_night", "arm_away"]
    # Away must never be returned as a Part-Arm label, even if somehow stored.
    leaked = Settings(
        panel_host="10.0.0.2",
        panel_port=DEFAULT_PANEL_PORT,
        udl_password=DEFAULT_UDL_PASSWORD,
        mqtt_host="mqtt.local",
        mqtt_port=DEFAULT_MQTT_PORT,
        mqtt_username="",
        mqtt_password="",
        mqtt_topic_prefix=DEFAULT_MQTT_TOPIC_PREFIX,
        part_arm_1="home",  # type: ignore[arg-type]
        part_arm_2="away",  # type: ignore[arg-type]
        part_arm_3="night",  # type: ignore[arg-type]
    )
    assert leaked.mode_byte_for_ha_mode("away") == FULL_ARM_AWAY_MODE_BYTE
    assert leaked.ha_mode_for_part_arm_slot(2) is None


def test_unused_slot_not_offered_as_arm_target() -> None:
    settings = load_settings(
        _valid_options(part_arm_1="night", part_arm_2="unused", part_arm_3="unused")
    )
    assert settings.mode_byte_for_ha_mode("night") == 1
    assert settings.mode_byte_for_ha_mode("home") is None
    features = settings.supported_arm_features()
    assert features == ["arm_night", "arm_away"]
    assert "arm_home" not in features


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
            "TEXECOM_PART_ARM_1": "unused",
            "TEXECOM_PART_ARM_2": "night",
            "TEXECOM_PART_ARM_3": "home",
        },
        options_path="/nonexistent/options.json",
    )
    assert settings.panel_host == "panel.env"
    assert settings.mqtt_host == "broker.env"
    assert settings.part_arm_1 == "unused"
    assert settings.part_arm_2 == "night"
    assert settings.part_arm_3 == "home"
    assert settings.mode_byte_for_ha_mode("away") == FULL_ARM_AWAY_MODE_BYTE
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
