"""Typed settings loader for Supervisor options / local test stand-ins."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Overridable schema defaults (installers must set values that match their panel).
DEFAULT_PANEL_PORT = 10001
DEFAULT_MQTT_PORT = 1883
DEFAULT_MQTT_TOPIC_PREFIX = "texecom"
DEFAULT_PART_ARM_AWAY = 0
DEFAULT_PART_ARM_NIGHT = 1
DEFAULT_PART_ARM_HOME = 2
# Tunable reconnect budgets (ADR-002) — not final hardcodes; SPIKE-002 one data point.
DEFAULT_RECONNECT_NORMAL_ATTEMPTS = 4
DEFAULT_RECONNECT_NORMAL_INTERVAL_SECONDS = 2.5
DEFAULT_RECONNECT_TRIGGER_ATTEMPTS = 18
DEFAULT_RECONNECT_TRIGGER_INTERVAL_SECONDS = 5.0

_ENV_KEYS = {
    "panel_host": "TEXECOM_PANEL_HOST",
    "panel_port": "TEXECOM_PANEL_PORT",
    "udl_password": "TEXECOM_UDL_PASSWORD",
    "mqtt_host": "TEXECOM_MQTT_HOST",
    "mqtt_port": "TEXECOM_MQTT_PORT",
    "mqtt_username": "TEXECOM_MQTT_USERNAME",
    "mqtt_password": "TEXECOM_MQTT_PASSWORD",
    "mqtt_topic_prefix": "TEXECOM_MQTT_TOPIC_PREFIX",
    "part_arm_away": "TEXECOM_PART_ARM_AWAY",
    "part_arm_night": "TEXECOM_PART_ARM_NIGHT",
    "part_arm_home": "TEXECOM_PART_ARM_HOME",
    "reconnect_normal_attempts": "TEXECOM_RECONNECT_NORMAL_ATTEMPTS",
    "reconnect_normal_interval_seconds": "TEXECOM_RECONNECT_NORMAL_INTERVAL_SECONDS",
    "reconnect_trigger_attempts": "TEXECOM_RECONNECT_TRIGGER_ATTEMPTS",
    "reconnect_trigger_interval_seconds": "TEXECOM_RECONNECT_TRIGGER_INTERVAL_SECONDS",
}


class ConfigError(ValueError):
    """Raised when required options are missing or values cannot be parsed."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Install-time bridge settings (panel, MQTT, Part-Arm mode bytes)."""

    panel_host: str
    panel_port: int
    udl_password: str
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    mqtt_topic_prefix: str
    part_arm_away: int
    part_arm_night: int
    part_arm_home: int
    reconnect_normal_attempts: int = DEFAULT_RECONNECT_NORMAL_ATTEMPTS
    reconnect_normal_interval_seconds: float = DEFAULT_RECONNECT_NORMAL_INTERVAL_SECONDS
    reconnect_trigger_attempts: int = DEFAULT_RECONNECT_TRIGGER_ATTEMPTS
    reconnect_trigger_interval_seconds: float = DEFAULT_RECONNECT_TRIGGER_INTERVAL_SECONDS


def load_settings(
    source: Mapping[str, Any] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    options_path: str | Path | None = None,
) -> Settings:
    """Load typed settings from a mapping, options JSON file, or environment.

    Resolution order when ``source`` is omitted:
    1. ``options_path`` if given and the file exists
    2. ``$TEXECOM_OPTIONS_FILE`` or ``/data/options.json`` if that file exists
    3. Environment variables (``TEXECOM_*``), suitable for the s6 run script

    Safe to call from asyncio startup (sync I/O only; no event-loop coupling).
    """
    if source is not None:
        raw = dict(source)
    else:
        raw = _load_raw(environ=environ, options_path=options_path)
    return _parse(raw)


def _load_raw(
    *,
    environ: Mapping[str, str] | None,
    options_path: str | Path | None,
) -> dict[str, Any]:
    env = environ if environ is not None else os.environ
    path = Path(options_path) if options_path is not None else _default_options_path(env)
    if path is not None and path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"failed to read options file {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"options file {path} must contain a JSON object")
        return data
    return _from_environ(env)


def _default_options_path(environ: Mapping[str, str]) -> Path:
    return Path(environ.get("TEXECOM_OPTIONS_FILE", "/data/options.json"))


def _from_environ(environ: Mapping[str, str]) -> dict[str, Any]:
    return {key: environ[env_key] for key, env_key in _ENV_KEYS.items() if env_key in environ}


def _parse(raw: Mapping[str, Any]) -> Settings:
    panel_host = _require_str(raw, "panel_host")
    udl_password = _require_str(raw, "udl_password")
    mqtt_host = _require_str(raw, "mqtt_host")
    mqtt_topic_prefix = _optional_str(raw, "mqtt_topic_prefix", DEFAULT_MQTT_TOPIC_PREFIX)
    if not mqtt_topic_prefix:
        raise ConfigError("mqtt_topic_prefix must not be empty")

    return Settings(
        panel_host=panel_host,
        panel_port=_optional_int(raw, "panel_port", DEFAULT_PANEL_PORT, minimum=1, maximum=65535),
        udl_password=udl_password,
        mqtt_host=mqtt_host,
        mqtt_port=_optional_int(raw, "mqtt_port", DEFAULT_MQTT_PORT, minimum=1, maximum=65535),
        mqtt_username=_optional_str(raw, "mqtt_username", ""),
        mqtt_password=_optional_str(raw, "mqtt_password", ""),
        mqtt_topic_prefix=mqtt_topic_prefix,
        part_arm_away=_optional_int(
            raw, "part_arm_away", DEFAULT_PART_ARM_AWAY, minimum=0, maximum=255
        ),
        part_arm_night=_optional_int(
            raw, "part_arm_night", DEFAULT_PART_ARM_NIGHT, minimum=0, maximum=255
        ),
        part_arm_home=_optional_int(
            raw, "part_arm_home", DEFAULT_PART_ARM_HOME, minimum=0, maximum=255
        ),
        reconnect_normal_attempts=_optional_int(
            raw,
            "reconnect_normal_attempts",
            DEFAULT_RECONNECT_NORMAL_ATTEMPTS,
            minimum=1,
            maximum=10_000,
        ),
        reconnect_normal_interval_seconds=_optional_float(
            raw,
            "reconnect_normal_interval_seconds",
            DEFAULT_RECONNECT_NORMAL_INTERVAL_SECONDS,
            minimum=0.0,
        ),
        reconnect_trigger_attempts=_optional_int(
            raw,
            "reconnect_trigger_attempts",
            DEFAULT_RECONNECT_TRIGGER_ATTEMPTS,
            minimum=1,
            maximum=10_000,
        ),
        reconnect_trigger_interval_seconds=_optional_float(
            raw,
            "reconnect_trigger_interval_seconds",
            DEFAULT_RECONNECT_TRIGGER_INTERVAL_SECONDS,
            minimum=0.0,
        ),
    )


def _require_str(raw: Mapping[str, Any], key: str) -> str:
    if key not in raw or raw[key] is None:
        raise ConfigError(f"missing required option: {key}")
    value = raw[key]
    if not isinstance(value, str):
        raise ConfigError(f"option {key} must be a string")
    value = value.strip()
    if not value:
        raise ConfigError(f"missing required option: {key}")
    return value


def _optional_str(raw: Mapping[str, Any], key: str, default: str) -> str:
    if key not in raw or raw[key] is None:
        return default
    value = raw[key]
    if not isinstance(value, str):
        raise ConfigError(f"option {key} must be a string")
    return value.strip()


def _optional_int(
    raw: Mapping[str, Any],
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if key not in raw or raw[key] is None or raw[key] == "":
        return default
    value = raw[key]
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"option {key} must be an integer") from exc
    if number < minimum or number > maximum:
        raise ConfigError(f"option {key} must be between {minimum} and {maximum}")
    return number


def _optional_float(
    raw: Mapping[str, Any],
    key: str,
    default: float,
    *,
    minimum: float,
) -> float:
    if key not in raw or raw[key] is None or raw[key] == "":
        return default
    value = raw[key]
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"option {key} must be a number") from exc
    if number < minimum:
        raise ConfigError(f"option {key} must be >= {minimum}")
    return number
