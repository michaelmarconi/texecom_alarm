"""Unit tests for zone parsing edge cases."""

from __future__ import annotations

import pytest

from texecom_alarm.protocol.client import ProtocolError
from texecom_alarm.zones import parse_zone_count, parse_zone_details, zone_display_name, zone_slug


def test_parse_zone_count_from_bytes() -> None:
    raw = b"Elite 88     ENG->SW V6.02.02LS1"
    assert parse_zone_count(raw) == 88


def test_parse_zone_count_rejects_short_and_bad() -> None:
    with pytest.raises(ProtocolError, match="cannot parse|Cannot read zone count"):
        parse_zone_count("Elite")
    with pytest.raises(ProtocolError, match="cannot parse|Cannot read zone count"):
        parse_zone_count("Elite xyz ENG")
    with pytest.raises(ProtocolError, match="non-positive"):
        parse_zone_count("Elite 0 ENG")


def test_parse_zone_details_length_variants() -> None:
    name = b"FRONT DOOR".ljust(32, b"\x00")
    z34 = parse_zone_details(bytes([1, 0x01]) + name, zone_number=1)
    assert z34.zone_type == 1 and z34.name == "FRONT DOOR"

    z35 = parse_zone_details(bytes([3, 0x00, 0x01]) + name, zone_number=2)
    assert z35.zone_type == 3 and z35.number == 2

    z41 = parse_zone_details(bytes([4]) + bytes(8) + name, zone_number=3)
    assert z41.zone_type == 4 and z41.name == "FRONT DOOR"

    with pytest.raises(ProtocolError, match="unexpected response length|unexpected zone-details"):
        parse_zone_details(b"\x01\x02", zone_number=1)


def test_zone_slug_empty_falls_back_to_number() -> None:
    assert zone_slug("", zone_number=7) == "zone_7"
    assert zone_slug("!!!", zone_number=9) == "zone_9"


def test_zone_slug_always_includes_zone_number() -> None:
    assert zone_slug("FRONT DOOR", zone_number=1) == "front_door_1"
    assert zone_slug("FRONT DOOR", zone_number=12) == "front_door_12"
    assert zone_slug("FRONT DOOR", zone_number=1) != zone_slug("FRONT DOOR", zone_number=12)


def test_zone_display_name_title_cases_panel_names() -> None:
    assert zone_display_name("FRONT DOOR", zone_number=1) == "Front Door"
    assert zone_display_name("  kitchen pir  ", zone_number=3) == "Kitchen Pir"
    assert zone_display_name("", zone_number=9) == "Zone 9"
