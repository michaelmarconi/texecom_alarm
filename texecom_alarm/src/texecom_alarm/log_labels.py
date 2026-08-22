"""Human-readable labels for panel bytes that appear in add-on logs.

Names follow ``docs/protocol-reference.md`` (confirmed / listed only). Unknown
codes fall back to ``type=N`` / ``unknown(N)`` rather than inventing prior-art
tables.
"""

from __future__ import annotations

_ZONE_STATUS: dict[int, str] = {
    0: "Secure",
    1: "Active",
    2: "Tamper",
    3: "Short",
}

_ZONE_TYPE: dict[int, str] = {
    0: "Unused",
    1: "Entry/Exit 1",
    2: "Entry/Exit 2",
    3: "Interior",
    4: "Perimeter",
    8: "Silent PA",
}

_AREA_STATE: dict[int, str] = {
    0: "disarmed",
    1: "in exit",
    2: "in entry",
    3: "full armed",
    4: "part armed",
    5: "in alarm",
    6: "Part-Arm slot 1",
    7: "Part-Arm slot 2",
}

_LOG_EVENT: dict[int, str] = {
    27: "Alarm Active",
    28: "Bell Active",
    32: "Exit Started",
    33: "Exit Error",
    34: "Entry Started",
    42: "Mode/action marker",
    45: "Reset After Alarm",
    53: "Remote-session marker",
    78: "Part Arm 1",
    79: "Part Arm 2",
    80: "Part Arm 3",
    113: "Remote Command",
    204: "Quick Part Arm 1",
    205: "Quick Part Arm 2",
    206: "Quick Part Arm 3",
    207: "Remote Part Arm 1",
    208: "Remote Part Arm 2",
    209: "Remote Part Arm 3",
}


def zone_status_label(status: int) -> str:
    """Low 2 bits of a zone status byte → Secure / Active / Tamper / Short."""
    return _ZONE_STATUS[status & 0x03]


def zone_type_label(zone_type: int) -> str:
    """Confirmed zone-type codes from protocol-reference; else ``type=N``."""
    return _ZONE_TYPE.get(zone_type, f"type={zone_type}")


def area_state_label(state: int) -> str:
    """Live AREA state byte → label; unknown as ``unknown(N)``."""
    return _AREA_STATE.get(state, f"unknown({state})")


def log_event_label(event_type: int) -> str:
    """LOG event type → name from protocol-reference; else ``type=N``."""
    return _LOG_EVENT.get(event_type, f"type={event_type}")
