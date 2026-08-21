"""Root logging configuration from add-on ``log_level`` settings."""

from __future__ import annotations

import logging

# Below DEBUG (10) so TRACE includes DEBUG and all more severe levels.
TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")

_LEVEL_BY_NAME = {
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "TRACE": TRACE_LEVEL,
}

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(log_level: str) -> None:
    """Apply the selected add-on log level to the root logger at startup."""
    level = _LEVEL_BY_NAME[log_level]
    # force=True so a second apply (tests / reload) actually replaces handlers.
    logging.basicConfig(level=level, format=_LOG_FORMAT, force=True)
    logging.getLogger().setLevel(level)
