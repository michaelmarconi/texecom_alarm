"""Texecom Alarm App — panel ↔ MQTT bridge (implementation pending /plan)."""

__version__ = "0.3.0"


def healthcheck() -> str:
    """Return a stable identity string for smoke tests and ops tracing."""
    return f"texecom-alarm/{__version__}"
