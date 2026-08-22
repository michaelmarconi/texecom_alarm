"""Pure panel-metadata label helpers for operator-readable logs."""

from __future__ import annotations

import pytest

from texecom_alarm.log_labels import (
    area_state_label,
    log_event_label,
    zone_status_label,
    zone_type_label,
)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (0x00, "Secure"),
        (0x01, "Active"),
        (0x02, "Tamper"),
        (0x03, "Short"),
        (0x11, "Active"),  # higher bits ignored; low 2 bits Active
        (0x10, "Secure"),
    ],
)
def test_zone_status_label(status: int, expected: str) -> None:
    assert zone_status_label(status) == expected


@pytest.mark.parametrize(
    ("zone_type", "expected"),
    [
        (0, "Unused"),
        (1, "Entry/Exit 1"),
        (2, "Entry/Exit 2"),
        (3, "Interior"),
        (4, "Perimeter"),
        (8, "Silent PA"),
        (9, "type=9"),
        (21, "type=21"),
    ],
)
def test_zone_type_label(zone_type: int, expected: str) -> None:
    assert zone_type_label(zone_type) == expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (0, "disarmed"),
        (1, "in exit"),
        (2, "in entry"),
        (3, "full armed"),
        (4, "part armed"),
        (5, "in alarm"),
        (6, "Part-Arm slot 1"),
        (7, "Part-Arm slot 2"),
        (99, "unknown(99)"),
    ],
)
def test_area_state_label(state: int, expected: str) -> None:
    assert area_state_label(state) == expected


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        (27, "Alarm Active"),
        (28, "Bell Active"),
        (32, "Exit Started"),
        (33, "Exit Error"),
        (34, "Entry Started"),
        (42, "Mode/action marker"),
        (45, "Reset After Alarm"),
        (53, "Remote-session marker"),
        (78, "Part Arm 1"),
        (79, "Part Arm 2"),
        (80, "Part Arm 3"),
        (113, "Remote Command"),
        (204, "Quick Part Arm 1"),
        (205, "Quick Part Arm 2"),
        (206, "Quick Part Arm 3"),
        (207, "Remote Part Arm 1"),
        (208, "Remote Part Arm 2"),
        (209, "Remote Part Arm 3"),
        (41, "type=41"),
    ],
)
def test_log_event_label(event_type: int, expected: str) -> None:
    assert log_event_label(event_type) == expected
