"""Panel zone enumeration (ADR-001): query count + details, drop unused slots."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from texecom_alarm.log_labels import zone_type_label
from texecom_alarm.logging_setup import TRACE_LEVEL
from texecom_alarm.protocol.client import PanelClient, ProtocolError
from texecom_alarm.protocol.frame import AREA_MAP, CMD_GETPANELIDENTIFICATION, CMD_GETZONEDETAILS

logger = logging.getLogger(__name__)

_ZONE_NAME_SLUG_RE = re.compile(r"[^a-z0-9]+")
_MAX_ZONE_COUNT = max(AREA_MAP)


@dataclass(frozen=True, slots=True)
class Zone:
    """An in-use panel zone (zoneType != 0)."""

    number: int
    zone_type: int
    name: str


def parse_zone_count(identification: bytes | str) -> int:
    """Extract zone count from a GETPANELIDENTIFICATION 32-byte payload."""
    text = (
        identification.decode("ascii", errors="replace")
        if isinstance(identification, bytes)
        else identification
    )
    display = text if len(text) <= 80 else f"{text[:80]}…"
    parts = text.split()
    if len(parts) < 2:
        raise ProtocolError(
            f"Cannot read zone count from the panel identification string {display!r}. "
            "The panel reply did not look like a Premier Elite identification."
        )
    try:
        count = int(parts[1])
    except ValueError as exc:
        raise ProtocolError(
            f"Cannot read zone count from the panel identification string {display!r}."
        ) from exc
    if count <= 0:
        raise ProtocolError(
            f"Panel reported a non-positive zone count ({count}) — cannot enumerate zones."
        )
    if count > _MAX_ZONE_COUNT:
        raise ProtocolError(
            f"Panel reported unsupported zone count {count} "
            f"(maximum {_MAX_ZONE_COUNT}). Identification: {display!r}."
        )
    return count


def parse_zone_details(payload: bytes, *, zone_number: int) -> Zone:
    """Decode a GETZONEDETAILS response body (34 / 35 / 41 bytes)."""
    n = len(payload)
    if n == 34:
        zone_type, text = payload[0], payload[2:]
    elif n == 35:
        zone_type, text = payload[0], payload[3:]
    elif n == 41:
        zone_type, text = payload[0], payload[9:]
    else:
        raise ProtocolError(
            f"Panel returned an unexpected zone-details reply for zone {zone_number} "
            f"(length {n} bytes)."
        )
    name = text.replace(b"\x00", b" ").decode("ascii", errors="replace").strip()
    return Zone(number=zone_number, zone_type=zone_type, name=name)


def zone_slug(name: str, *, zone_number: int) -> str:
    """Slugify a panel zone name; always includes zone number to avoid collisions."""
    base = _ZONE_NAME_SLUG_RE.sub("_", name.lower()).strip("_")
    if not base:
        base = "zone"
    return f"{base}_{zone_number}"


def zone_display_name(name: str, *, zone_number: int) -> str:
    """Title-Case friendly name for MQTT discovery (panel names are often ALL CAPS)."""
    cleaned = name.strip()
    if not cleaned:
        return f"Zone {zone_number}"
    return cleaned.title()


def _ident_display(ident: bytes) -> str:
    """Compact ASCII panel identification for log lines (strip padding)."""
    return ident.decode("ascii", errors="replace").strip()


async def enumerate_zones(client: PanelClient) -> tuple[list[Zone], int]:
    """LOGIN must already have succeeded. Ask the panel for in-use zones only.

    Returns ``(in_use_zones, panel_zone_count)`` so callers can run a GetZoneState
    snapshot over the full slot range (ADR-006) without a second identification query.
    """
    logger.debug("zone_enumerate_start")
    ident = await client.send_command(CMD_GETPANELIDENTIFICATION)
    zone_count = parse_zone_count(ident)
    ident_text = _ident_display(ident)
    logger.debug("zone_count %s (identification=%s)", zone_count, ident_text)

    in_use: list[Zone] = []
    for number in range(1, zone_count + 1):
        payload = await client.send_command(CMD_GETZONEDETAILS, bytes([number]))
        zone = parse_zone_details(payload, zone_number=number)
        if zone.zone_type == 0:
            logger.log(TRACE_LEVEL, "zone_unused_skipped zone=%s", number)
            continue
        in_use.append(zone)
        logger.debug(
            "zone_in_use zone=%s name=%r type=%s (%s)",
            number,
            zone.name,
            zone.zone_type,
            zone_type_label(zone.zone_type),
        )

    logger.info(
        "enumerated_zones %s in-use of %s slots (%s)",
        len(in_use),
        zone_count,
        ident_text,
    )
    logger.debug(
        "zone_enumerate_done in_use=%s unused=%s of %s",
        len(in_use),
        zone_count - len(in_use),
        zone_count,
    )
    return in_use, zone_count
