"""Panel-link trust detection: command rejects + house-state poll (ADR-010)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Protocol

from texecom_alarm.area_state import area_size_for_zones
from texecom_alarm.mqtt.discovery import PANEL_LINK_OFF, PANEL_LINK_ON
from texecom_alarm.protocol.client import PanelClient, ProtocolError
from texecom_alarm.protocol.frame import AREA_FLAGS_COUNT
from texecom_alarm.reconnect import publish_panel_link_state

logger = logging.getLogger(__name__)

TRUST_POLL_INTERVAL_SECONDS = 30.0
RECOVER_WINDOW_SECONDS = 30.0

REASON_ARM_NAK = "arm_nak"
REASON_DISARM_NAK = "disarm_nak"
REASON_ARM_TIMEOUT = "arm_timeout"
REASON_DISARM_TIMEOUT = "disarm_timeout"
REASON_TRUST_POLL_NAK = "trust_poll_nak"
REASON_TRUST_POLL_TIMEOUT = "trust_poll_timeout"
REASON_TRUST_POLL_OK = "trust_poll_ok"


class MqttPublisher(Protocol):
    async def publish(
        self,
        topic: str,
        payload: str | bytes,
        *,
        retain: bool = False,
        qos: int = 0,
    ) -> None: ...


class PanelTrust:
    """Tracks command-path + trust-poll health for Alarm Panel Connected.

    Never marks zone/alarm entities unavailable (ADR-004). Never degrades solely
    because zones are quiet. Does not tear down the session or auto-retry commands.
    """

    def __init__(
        self,
        mqtt: MqttPublisher,
        *,
        topic_prefix: str,
        zone_count: int,
        poll_interval: float = TRUST_POLL_INTERVAL_SECONDS,
        recover_window: float = RECOVER_WINDOW_SECONDS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._mqtt = mqtt
        self._topic_prefix = topic_prefix
        self._zone_count = zone_count
        self._poll_interval = poll_interval
        self._recover_window = recover_window
        self._clock = clock if clock is not None else time.monotonic
        self._live = True
        self._last_keepalive_ok: bool | None = None
        self._last_command_fail_at: float | None = None
        self._last_successful_trust_poll_at: float | None = None
        self._last_poll_attempt_at: float | None = None
        self._last_failure_reason: str | None = None
        self._last_failure_ha_mode: str | None = None

    @property
    def live(self) -> bool:
        return self._live

    def note_keepalive_ok(self) -> None:
        self._last_keepalive_ok = True

    def note_keepalive_failed(self) -> None:
        self._last_keepalive_ok = False

    async def reset_after_reconnect(self) -> None:
        """Clear degrade memory and republish panel-link ON after recovery.

        Must publish ON even when ``_live`` is already True: a command failure can
        publish OFF after reconnect's ON and before this reset runs; setting
        ``_live`` alone would leave MQTT OFF while ``_maybe_recover`` skips
        republish because it thinks the link is already live.
        """
        now = self._clock()
        self._live = True
        self._last_command_fail_at = None
        self._last_successful_trust_poll_at = now
        self._last_poll_attempt_at = now
        self._last_failure_reason = None
        self._last_failure_ha_mode = None
        await publish_panel_link_state(
            self._mqtt,
            topic_prefix=self._topic_prefix,
            live=True,
        )

    def _seconds_since(self, when: float | None) -> float | None:
        if when is None:
            return None
        return max(0.0, self._clock() - when)

    def _log_extra(
        self,
        *,
        reason: str,
        ha_mode: str | None,
        panel_link_payload: str,
    ) -> dict[str, object]:
        return {
            "reason": reason,
            "ha_mode": ha_mode,
            "keepalive_still_ok": self._last_keepalive_ok,
            "seconds_since_last_successful_trust_poll": self._seconds_since(
                self._last_successful_trust_poll_at
            ),
            "seconds_since_last_command_failure": self._seconds_since(self._last_command_fail_at),
            "panel_link_payload": panel_link_payload,
        }

    async def record_command_failure(
        self,
        reason: str,
        *,
        ha_mode: str | None = None,
    ) -> None:
        """Immediate degrade on arm/disarm NAK or timeout (even if keepalive OK)."""
        now = self._clock()
        self._last_command_fail_at = now
        self._last_failure_reason = reason
        self._last_failure_ha_mode = ha_mode
        self._live = False
        await publish_panel_link_state(
            self._mqtt,
            topic_prefix=self._topic_prefix,
            live=False,
        )
        logger.warning(
            "Alarm Panel Connected degraded (%s); keepalive_still_ok=%s; "
            "publishing panel-link OFF. Zone/alarm entities keep last-known state.",
            reason,
            self._last_keepalive_ok,
            extra=self._log_extra(
                reason=reason,
                ha_mode=ha_mode,
                panel_link_payload=PANEL_LINK_OFF,
            ),
        )

    def poll_due(self) -> bool:
        if self._last_poll_attempt_at is None:
            return True
        return (self._clock() - self._last_poll_attempt_at) >= self._poll_interval

    def seconds_until_poll(self) -> float:
        if self._last_poll_attempt_at is None:
            return 0.0
        remaining = self._poll_interval - (self._clock() - self._last_poll_attempt_at)
        return max(0.0, remaining)

    async def maybe_poll(self, panel: PanelClient) -> None:
        """Run a get_area_flags trust poll when the interval has elapsed."""
        if not self.poll_due():
            return
        await self.poll(panel)

    async def poll(self, panel: PanelClient) -> None:
        """Ask the panel for area flags as a trust corroboration (not keepalive)."""
        now = self._clock()
        self._last_poll_attempt_at = now
        area_size = area_size_for_zones(self._zone_count)
        try:
            await panel.get_area_flags(0, AREA_FLAGS_COUNT, area_size=area_size)
        except ProtocolError:
            await self._on_poll_failure(REASON_TRUST_POLL_NAK)
            return
        except TimeoutError:
            await self._on_poll_failure(REASON_TRUST_POLL_TIMEOUT)
            return

        self._last_successful_trust_poll_at = self._clock()
        await self._maybe_recover()

    async def _on_poll_failure(self, reason: str) -> None:
        self._live = False
        self._last_failure_reason = reason
        await publish_panel_link_state(
            self._mqtt,
            topic_prefix=self._topic_prefix,
            live=False,
        )
        logger.warning(
            "Alarm Panel Connected degraded (%s); keepalive_still_ok=%s; "
            "publishing panel-link OFF. Zone/alarm entities keep last-known state.",
            reason,
            self._last_keepalive_ok,
            extra=self._log_extra(
                reason=reason,
                ha_mode=self._last_failure_ha_mode,
                panel_link_payload=PANEL_LINK_OFF,
            ),
        )

    def _command_failure_cleared(self) -> bool:
        if self._last_command_fail_at is None:
            return True
        return (self._clock() - self._last_command_fail_at) >= self._recover_window

    async def _maybe_recover(self) -> None:
        if not self._command_failure_cleared():
            return
        if self._live:
            return
        self._live = True
        await publish_panel_link_state(
            self._mqtt,
            topic_prefix=self._topic_prefix,
            live=True,
        )
        logger.info(
            "Alarm Panel Connected recovered to live after successful trust poll; "
            "publishing panel-link ON.",
            extra=self._log_extra(
                reason=REASON_TRUST_POLL_OK,
                ha_mode=self._last_failure_ha_mode,
                panel_link_payload=PANEL_LINK_ON,
            ),
        )
