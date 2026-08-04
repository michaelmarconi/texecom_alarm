"""Smoke-import for ``python -m texecom_alarm`` entry."""

from __future__ import annotations

import runpy
from unittest.mock import patch


def test_main_module_invokes_app_main() -> None:
    with patch("texecom_alarm.app.main") as main_mock:
        runpy.run_module("texecom_alarm", run_name="__main__")
        main_mock.assert_called_once()
