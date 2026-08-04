"""Panel zone enumeration (ADR-001): query count + details, drop unused slots."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from texecom_alarm.protocol.client import PanelClient, ProtocolError
from texecom_alarm.protocol.frame import CMD_GETPANELIDENTIFICATION, CMD_GETZONEDETAILS

logger = logging.getLogger(__name__)

_ZONE_NAME_SLUG_RE = re.compile(r"[^a-z0-9]+")


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
    parts = text.split()
    if len(parts) < 2:
        raise ProtocolError(f"GETPANELIDENTIFICATION: cannot parse zone count from {text!r}")
    try:
        count = int(parts[1])
    except ValueError as exc:
        raise ProtocolError(
            f"GETPANELIDENTIFICATION: cannot parse zone count from {text!r}"
        ) from exc
    if count <= 0:
        raise ProtocolError(f"GETPANELIDENTIFICATION: non-positive zone count {count}")
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
        raise ProtocolError(f"GETZONEDETAILS: unexpected response length {n}")
    name = text.replace(b"\x00", b" ").decode("ascii", errors="replace").strip()
    return Zone(number=zone_number, zone_type=zone_type, name=name)


def zone_slug(name: str, *, zone_number: int) -> str:
    """Slugify a panel zone name for provisional texecom_alarm_* object_ids."""
    base = _ZONE_NAME_SLUG_RE.sub("_", name.lower()).strip("_")
    if not base:
        base = f"zone_{zone_number}"
    return base


async def enumerate_zones(client: PanelClient) -> list[Zone]:
    """LOGIN must already have succeeded. Ask the panel for in-use zones only."""
    logger.debug("zone_enumerate_start")
    ident = await client.send_command(CMD_GETPANELIDENTIFICATION)
    zone_count = parse_zone_count(ident)
    logger.debug("zone_count", extra={"zone_count": zone_count})

    in_use: list[Zone] = []
    for number in range(1, zone_count + 1):
        payload = await client.send_command(CMD_GETZONEDETAILS, bytes([number]))
        zone = parse_zone_details(payload, zone_number=number)
        if zone.zone_type == 0:
            logger.debug("zone_unused_skipped", extra={"zone": number})
            continue
        in_use.append(zone)
        logger.debug(
            "zone_in_use",
            extra={"zone": number, "zone_type": zone.zone_type, "name": zone.name},
        )

    logger.debug("zone_enumerate_done", extra={"in_use": len(in_use)})
    return in_use
