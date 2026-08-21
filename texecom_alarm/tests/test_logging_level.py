"""Unit tests for selectable log_level applied at startup."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from texecom_alarm.config import DEFAULT_LOG_LEVEL, ConfigError, load_settings
from texecom_alarm.logging_setup import TRACE_LEVEL, configure_logging


def _minimal_options(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "panel_host": "10.0.0.2",
        "mqtt_host": "mqtt.local",
    }
    data.update(overrides)
    return data


@pytest.fixture
def restore_root_logging() -> None:
    """Keep configure_logging from leaving DEBUG/TRACE on for later tests."""
    root = logging.getLogger()
    before_level = root.level
    before_handlers = list(root.handlers)
    yield
    root.handlers.clear()
    for handler in before_handlers:
        root.addHandler(handler)
    root.setLevel(before_level)


def test_addon_config_schema_log_level_tokens() -> None:
    """Supervisor list(...) tokens are the Configuration radio labels (AC1)."""
    config_path = Path(__file__).resolve().parents[1] / "config.yaml"
    text = config_path.read_text(encoding="utf-8")
    assert "log_level: list(WARNING|INFO|DEBUG|TRACE)" in text
    assert "log_level: INFO" in text


def test_unset_log_level_defaults_to_info() -> None:
    settings = load_settings(_minimal_options())
    assert settings.log_level == DEFAULT_LOG_LEVEL
    assert settings.log_level == "INFO"


@pytest.mark.parametrize("level", ["WARNING", "INFO", "DEBUG", "TRACE"])
def test_log_level_option_parses(level: str) -> None:
    settings = load_settings(_minimal_options(log_level=level))
    assert settings.log_level == level


def test_invalid_log_level_raises() -> None:
    with pytest.raises(ConfigError, match="log_level"):
        load_settings(_minimal_options(log_level="VERBOSE"))


@pytest.mark.parametrize(
    ("configured", "debug_emitted", "trace_emitted"),
    [
        ("INFO", False, False),
        ("DEBUG", True, False),
        ("TRACE", True, True),
    ],
)
def test_configure_logging_filters_by_selected_level(
    configured: str,
    debug_emitted: bool,
    trace_emitted: bool,
    restore_root_logging: None,
) -> None:
    configure_logging(configured)
    probe = logging.getLogger("texecom_alarm.test_logging_level_probe")
    probe.propagate = True
    probe.setLevel(logging.NOTSET)

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    capture = _Capture(level=logging.NOTSET)
    root = logging.getLogger()
    root.addHandler(capture)
    try:
        probe.debug("debug-line")
        probe.log(TRACE_LEVEL, "trace-line")
    finally:
        root.removeHandler(capture)

    messages = [r.getMessage() for r in records]
    assert ("debug-line" in messages) is debug_emitted
    assert ("trace-line" in messages) is trace_emitted
    assert (
        root.level
        == {
            "INFO": logging.INFO,
            "DEBUG": logging.DEBUG,
            "TRACE": TRACE_LEVEL,
        }[configured]
    )
