"""Typed settings loader for Supervisor options / local test stand-ins."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

# Overridable schema defaults (installers must set values that match their panel).
DEFAULT_PANEL_PORT = 10001
DEFAULT_MQTT_PORT = 1883
DEFAULT_MQTT_TOPIC_PREFIX = "texecom"
DEFAULT_UDL_PASSWORD = "1234"  # noqa: S105 — panel factory default, overridable
# Slot-oriented Part-Arm defaults (Unused until the installer maps each slot).
DEFAULT_PART_ARM_1 = "unused"
DEFAULT_PART_ARM_2 = "unused"
DEFAULT_PART_ARM_3 = "unused"
# Confirmed SPIKE-005 full-arm Away mode byte (ADR-008: Away is never a Part-Arm slot).
FULL_ARM_AWAY_MODE_BYTE = 0
# One reconnect wait interval covers every disconnect cause (ADR-018 / ADR-019)
# — no attempts cap (the app always keeps retrying) and no normal/trigger split.
DEFAULT_RECONNECT_DELAY_SECONDS = 5.0
# Stuck-trust fail window before tear-down / re-login (ADR-011) — tunable, not final.
DEFAULT_TRUST_FAIL_WINDOW_SECONDS = 90.0
# Reconciliation poll no longer gates connectivity (ADR-016), so it can run this
# infrequently by default; households can tune it via add-on settings (ADR-017).
DEFAULT_RECONCILIATION_POLL_INTERVAL_SECONDS = 300.0
DEFAULT_LOG_LEVEL = "INFO"

PartArmLabel = Literal["home", "night", "unused"]
LogLevel = Literal["WARNING", "INFO", "DEBUG", "TRACE"]
_PART_ARM_LABELS = frozenset({"home", "night", "unused"})
_LOG_LEVELS = frozenset({"WARNING", "INFO", "DEBUG", "TRACE"})

logger = logging.getLogger(__name__)

_ENV_KEYS = {
    "panel_host": "TEXECOM_PANEL_HOST",
    "panel_port": "TEXECOM_PANEL_PORT",
    "udl_password": "TEXECOM_UDL_PASSWORD",
    "mqtt_host": "TEXECOM_MQTT_HOST",
    "mqtt_port": "TEXECOM_MQTT_PORT",
    "mqtt_username": "TEXECOM_MQTT_USERNAME",
    "mqtt_password": "TEXECOM_MQTT_PASSWORD",
    "mqtt_topic_prefix": "TEXECOM_MQTT_TOPIC_PREFIX",
    "part_arm_1": "TEXECOM_PART_ARM_1",
    "part_arm_2": "TEXECOM_PART_ARM_2",
    "part_arm_3": "TEXECOM_PART_ARM_3",
    "reconnect_delay_seconds": "TEXECOM_RECONNECT_DELAY_SECONDS",
    "trust_fail_window_seconds": "TEXECOM_TRUST_FAIL_WINDOW_SECONDS",
    "reconciliation_poll_interval_seconds": "TEXECOM_RECONCILIATION_POLL_INTERVAL_SECONDS",
    "log_level": "TEXECOM_LOG_LEVEL",
}


class ConfigError(ValueError):
    """Raised when required options are missing or values cannot be parsed."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Install-time bridge settings (panel, MQTT, Part-Arm slot → HA mode)."""

    panel_host: str
    panel_port: int
    udl_password: str = field(repr=False)
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str = field(repr=False)
    mqtt_topic_prefix: str
    part_arm_1: PartArmLabel
    part_arm_2: PartArmLabel
    part_arm_3: PartArmLabel
    reconnect_delay_seconds: float = DEFAULT_RECONNECT_DELAY_SECONDS
    trust_fail_window_seconds: float = DEFAULT_TRUST_FAIL_WINDOW_SECONDS
    reconciliation_poll_interval_seconds: float = DEFAULT_RECONCILIATION_POLL_INTERVAL_SECONDS
    log_level: LogLevel = DEFAULT_LOG_LEVEL

    def part_arm_labels(self) -> tuple[PartArmLabel, PartArmLabel, PartArmLabel]:
        return (self.part_arm_1, self.part_arm_2, self.part_arm_3)

    def mode_byte_for_ha_mode(self, ha_mode: str) -> int | None:
        """Return cmd=6 mode byte for an HA arm mode, or None if not available.

        Away always uses full-arm mode byte 0 (ADR-008 / SPIKE-005). Home and
        Night resolve only through configured Part-Arm slots (slot N → byte N).
        """
        if ha_mode == "away":
            return FULL_ARM_AWAY_MODE_BYTE
        for slot, label in enumerate(self.part_arm_labels(), start=1):
            if label == ha_mode:
                return slot
        return None

    def ha_mode_for_part_arm_slot(self, slot: int) -> str | None:
        """Return the HA mode label for Part-Arm slot 1/2/3, or None if unused.

        Away is never a Part-Arm label (ADR-008); legacy Away values are treated
        as unused.
        """
        labels = {1: self.part_arm_1, 2: self.part_arm_2, 3: self.part_arm_3}
        label = labels.get(slot)
        if label is None or label == "unused" or label == "away":
            return None
        return label

    def supported_arm_features(self) -> list[str]:
        """MQTT discovery ``supported_features`` for in-use Part-Arm modes.

        Order is always Home → Night → Away (HA card best-effort). Unused slots
        contribute no arm target. Away is always offered via the full-arm mode
        byte (ADR-008) — never via a Part-Arm slot assignment.
        """
        available: set[str] = {"away"}
        for label in self.part_arm_labels():
            if label in ("home", "night"):
                available.add(label)
        return [f"arm_{mode}" for mode in ("home", "night", "away") if mode in available]


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
    udl_password = _optional_str(raw, "udl_password", DEFAULT_UDL_PASSWORD)
    if not udl_password:
        udl_password = DEFAULT_UDL_PASSWORD
    mqtt_host = _require_str(raw, "mqtt_host")
    mqtt_topic_prefix = _optional_str(raw, "mqtt_topic_prefix", DEFAULT_MQTT_TOPIC_PREFIX)
    if not mqtt_topic_prefix:
        raise ConfigError("mqtt_topic_prefix must not be empty")

    part_arm_1 = _parse_part_arm_label(raw, "part_arm_1", DEFAULT_PART_ARM_1)
    part_arm_2 = _parse_part_arm_label(raw, "part_arm_2", DEFAULT_PART_ARM_2)
    part_arm_3 = _parse_part_arm_label(raw, "part_arm_3", DEFAULT_PART_ARM_3)
    _validate_unique_part_arm_modes(part_arm_1, part_arm_2, part_arm_3)

    return Settings(
        panel_host=panel_host,
        panel_port=_optional_int(raw, "panel_port", DEFAULT_PANEL_PORT, minimum=1, maximum=65535),
        udl_password=udl_password,
        mqtt_host=mqtt_host,
        mqtt_port=_optional_int(raw, "mqtt_port", DEFAULT_MQTT_PORT, minimum=1, maximum=65535),
        mqtt_username=_optional_str(raw, "mqtt_username", ""),
        mqtt_password=_optional_str(raw, "mqtt_password", ""),
        mqtt_topic_prefix=mqtt_topic_prefix,
        part_arm_1=part_arm_1,
        part_arm_2=part_arm_2,
        part_arm_3=part_arm_3,
        reconnect_delay_seconds=_optional_float(
            raw,
            "reconnect_delay_seconds",
            DEFAULT_RECONNECT_DELAY_SECONDS,
            minimum=0.0,
        ),
        trust_fail_window_seconds=_optional_float(
            raw,
            "trust_fail_window_seconds",
            DEFAULT_TRUST_FAIL_WINDOW_SECONDS,
            minimum=0.0,
        ),
        reconciliation_poll_interval_seconds=_optional_float(
            raw,
            "reconciliation_poll_interval_seconds",
            DEFAULT_RECONCILIATION_POLL_INTERVAL_SECONDS,
            minimum=0.0,
        ),
        log_level=_parse_log_level(raw),
    )


def _parse_log_level(raw: Mapping[str, Any]) -> LogLevel:
    if "log_level" not in raw or raw["log_level"] is None or raw["log_level"] == "":
        return DEFAULT_LOG_LEVEL  # type: ignore[return-value]
    value = raw["log_level"]
    if not isinstance(value, str):
        raise ConfigError("option log_level must be a string")
    level = value.strip().upper()
    if level not in _LOG_LEVELS:
        raise ConfigError(
            f"option log_level must be one of WARNING, INFO, DEBUG, TRACE (got {value!r})"
        )
    return level  # type: ignore[return-value]


def _parse_part_arm_label(raw: Mapping[str, Any], key: str, default: PartArmLabel) -> PartArmLabel:
    if key not in raw or raw[key] is None or raw[key] == "":
        return default
    value = raw[key]
    if not isinstance(value, str):
        raise ConfigError(f"option {key} must be a string")
    # Canonical schema values are lowercase (home|night|unused). Also accept
    # Title Case + emoji (e.g. "Home 🏠") if somehow present. First whitespace
    # token after lower() is enough. Legacy Away on a slot coerces to Unused
    # (ADR-008) — Away is always full arm, never a Part-Arm assignment.
    stripped = value.strip()
    if not stripped:
        return default
    label = stripped.lower().split(None, 1)[0]
    if label == "away":
        logger.warning(
            "Part-Arm option %s had legacy Away; coercing to Unused. "
            "Away always uses full arm (mode byte 0) and cannot occupy a Part-Arm slot.",
            key,
        )
        return "unused"
    if label not in _PART_ARM_LABELS:
        raise ConfigError(f"option {key} must be one of home, night, unused (got {value!r})")
    return label  # type: ignore[return-value]


def _validate_unique_part_arm_modes(
    part_arm_1: PartArmLabel,
    part_arm_2: PartArmLabel,
    part_arm_3: PartArmLabel,
) -> None:
    seen: dict[str, int] = {}
    for slot, label in enumerate((part_arm_1, part_arm_2, part_arm_3), start=1):
        if label == "unused":
            continue
        if label in seen:
            raise ConfigError(
                f"HA mode {label!r} is assigned to both Part-Arm slot {seen[label]} and slot {slot}"
            )
        seen[label] = slot


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


def warn_if_factory_udl(settings: Settings) -> None:
    """Log once when the configured UDL is still the panel factory default.

    Does not print the password. Leaving factory UDL means any LAN client that
    can reach the ComIP port can Connect-login with the well-known default.
    """
    if settings.udl_password != DEFAULT_UDL_PASSWORD:
        return
    logger.info(
        "Using factory-default UDL password — change it on the panel (and here) "
        "if the LAN is not fully trusted; any Connect client on that port can use "
        "the same well-known password."
    )
