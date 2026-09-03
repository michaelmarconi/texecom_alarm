"""Panel-link trust detection: keepalive failure + command rejects (ADR-016).

The periodic house/arm reconciliation poll no longer feeds Alarm Panel
Connection at all — it only corroborates the alarm entity against the panel's
last-known state. An isolated poll NAK/timeout, with keepalives and commands
otherwise healthy, must never flip Connection off.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Protocol

from texecom_alarm.alarm_flags_guard import flags_snapshot_may_replace_live
from texecom_alarm.area_state import (
    HOUSE_AREA_NUMBER,
    area_size_for_zones,
    decode_area_ha_state,
    publish_alarm_state,
)
from texecom_alarm.config import Settings
from texecom_alarm.mqtt.discovery import PANEL_LINK_OFF, PANEL_LINK_ON
from texecom_alarm.protocol.client import PanelClient, ProtocolError
from texecom_alarm.protocol.frame import AREA_FLAGS_COUNT
from texecom_alarm.reconnect import publish_panel_link_state

logger = logging.getLogger(__name__)

# Reconciliation poll no longer gates connectivity (ADR-016), so its default
# cadence is slow and household-tunable (ADR-017) rather than a fast health check.
TRUST_POLL_INTERVAL_SECONDS = 300.0
RECOVER_WINDOW_SECONDS = 30.0
# Plan default: 3× shipping trust-poll interval (ADR-011 — tunable, not final).
STUCK_TRUST_FAIL_WINDOW_SECONDS = 90.0
# Roughly three consecutive missed check-ins before a refusing session is
# declared dead (ADR-020) — matches config.DEFAULT_CHECKIN_PATIENCE_SECONDS.
CHECKIN_PATIENCE_SECONDS = 45.0

REASON_ARM_NAK = "arm_nak"
REASON_DISARM_NAK = "disarm_nak"
REASON_ARM_TIMEOUT = "arm_timeout"
REASON_DISARM_TIMEOUT = "disarm_timeout"
REASON_ARM_DISCONNECT = "arm_disconnect"
REASON_DISARM_DISCONNECT = "disarm_disconnect"
REASON_TRUST_POLL_NAK = "trust_poll_nak"
REASON_TRUST_POLL_TIMEOUT = "trust_poll_timeout"
REASON_KEEPALIVE_OK = "keepalive_ok"
REASON_PANEL_TRAFFIC = "panel_traffic"
REASON_STUCK_FAIL_WINDOW = "stuck_trust_fail_window"


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
    """Tracks keepalive + command-path health for Alarm Panel Connection.

    Connection goes down only on a missed keepalive/disconnect or a rejected/
    timed-out arm/disarm command; it recovers once keepalives resume and any
    command-failure recover window has cleared (ADR-016). The reconciliation
    poll (``poll``/``maybe_poll``) is not part of this signal at all — it only
    corroborates the alarm entity. Never marks zone/alarm entities unavailable
    (ADR-004). If Connection stays OFF past the stuck-trust fail window, signals
    session tear-down / re-login (ADR-011). Does not auto-retry arm/disarm
    commands.
    """

    def __init__(
        self,
        mqtt: MqttPublisher,
        *,
        topic_prefix: str,
        zone_count: int,
        poll_interval: float = TRUST_POLL_INTERVAL_SECONDS,
        recover_window: float = RECOVER_WINDOW_SECONDS,
        fail_window: float = STUCK_TRUST_FAIL_WINDOW_SECONDS,
        checkin_patience: float = CHECKIN_PATIENCE_SECONDS,
        clock: Callable[[], float] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._mqtt = mqtt
        self._topic_prefix = topic_prefix
        self._zone_count = zone_count
        self._poll_interval = poll_interval
        self._recover_window = recover_window
        self._fail_window = fail_window
        self._checkin_patience = checkin_patience
        self._clock = clock if clock is not None else time.monotonic
        self._settings = settings
        self._live = True
        self._last_keepalive_ok: bool | None = None
        self._last_command_fail_at: float | None = None
        self._last_successful_trust_poll_at: float | None = None
        self._last_poll_attempt_at: float | None = None
        self._degraded_since: float | None = None
        self._last_failure_reason: str | None = None
        self._last_failure_ha_mode: str | None = None
        # Set when a follow-up read after a successful arm/disarm could not be
        # parsed. Reconnect consumes this so a first-attempt re-login can keep
        # Connection on instead of treating the tap as failed.
        self._session_collision = False
        # Last arm HA mode the panel ACK'd; used to classify a later
        # ForcedDisconnect on a duplicate same-mode TX as a collision.
        self.last_acked_arm_ha_mode: str | None = None
        # Separate from _degraded_since/_mark_degraded on purpose (ADR-020): a
        # refused/unanswered check-in must never touch Connection/_live by
        # itself, only this streak-since timestamp, kept fully independent of
        # the command-rejection watchdog's own fail window (ADR-011/ADR-016).
        self._checkin_failure_since: float | None = None

    @property
    def live(self) -> bool:
        return self._live

    @property
    def fail_window(self) -> float:
        return self._fail_window

    @property
    def checkin_patience(self) -> float:
        return self._checkin_patience

    async def note_keepalive_ok(self) -> None:
        """Record a successful routine check-in and drive Connection recovery.

        Recovery from a command-failure degrade is driven from here, not from a
        successful reconciliation poll (ADR-016). Also clears any in-progress
        check-in failure streak (ADR-020) — a session that just answered is,
        by definition, no longer in an unbroken run of refusals.
        """
        self._last_keepalive_ok = True
        self._checkin_failure_since = None
        await self._maybe_recover(reason=REASON_KEEPALIVE_OK)

    async def note_panel_traffic(self) -> None:
        """Record that a well-formed frame arrived on the live socket.

        A frame the panel pushes unprompted (zone/area/log) is evidence the
        socket is alive, so it drives recovery from a command-failure degrade:
        without it, a busy panel sending frames faster than the idle-timeout
        window would starve the keepalive path (``note_keepalive_ok``) and
        stall that recovery for as long as the traffic kept arriving.

        It deliberately does *not* clear the check-in failure streak. Unprompted
        chatter is not proof the panel still answers when asked, and a session
        has been seen carrying traffic all day while refusing every request; if
        traffic reset the patience clock, such a session would hold the window
        open forever and never be recovered (ADR-020). Only a check-in that got
        a valid reply clears the streak.
        """
        await self._maybe_recover(reason=REASON_PANEL_TRAFFIC)

    def note_keepalive_failed(self) -> None:
        self._last_keepalive_ok = False

    def note_checkin_failed(self) -> None:
        """Record the start of an unbroken run of refused/unanswered check-ins.

        Only the *first* failure in a streak sets the clock — later failures
        in the same streak must not push the patience deadline back out
        (ADR-020: patience is measured from when the streak started). Never
        touches Connection/``_live``: a refusal inside the patience window
        must not degrade the signal (ADR-004/ADR-020) — that stays a job for
        the app to decide once ``checkin_patience_exceeded`` is true.
        """
        if self._checkin_failure_since is None:
            self._checkin_failure_since = self._clock()

    def checkin_patience_exceeded(self) -> bool:
        """True once the current check-in failure streak has run past patience."""
        if self._checkin_failure_since is None:
            return False
        return (self._clock() - self._checkin_failure_since) >= self._checkin_patience

    def note_arm_acked(self, ha_mode: str) -> None:
        """Remember that this arm mode was ACK'd by the panel."""
        self.last_acked_arm_ha_mode = ha_mode

    def clear_arm_ack(self) -> None:
        """Clear last arm ACK memory after a successful disarm."""
        self.last_acked_arm_ha_mode = None

    def note_session_collision(self) -> None:
        """Remember that a successful tap's follow-up read could not be parsed.

        Does not record a command failure and does not flip Connection off —
        reconnect decides that from whether the first re-login succeeds.
        """
        self._session_collision = True

    def consume_session_collision(self) -> bool:
        """Return and clear the pending post-ACK parse-miss flag."""
        flagged = self._session_collision
        self._session_collision = False
        return flagged

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
        self._degraded_since = None
        self._last_failure_reason = None
        self._last_failure_ha_mode = None
        self._checkin_failure_since = None
        self._session_collision = False
        self.last_acked_arm_ha_mode = None
        await publish_panel_link_state(
            self._mqtt,
            topic_prefix=self._topic_prefix,
            live=True,
        )

    def _seconds_since(self, when: float | None) -> float | None:
        if when is None:
            return None
        return max(0.0, self._clock() - when)

    def _mark_degraded(self) -> None:
        self._live = False
        if self._degraded_since is None:
            self._degraded_since = self._clock()

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
            "seconds_since_degraded": self._seconds_since(self._degraded_since),
            "panel_link_payload": panel_link_payload,
        }

    async def record_command_failure(
        self,
        reason: str,
        *,
        ha_mode: str | None = None,
    ) -> None:
        """Immediate degrade on arm/disarm NAK or timeout (even if keepalive OK).

        Chatty Arm/Disarm waits are retried before this is called. This path is
        a refuse, a silent wait, or a used-up retry budget — not an in-flight
        busy retry. The refused-command fail window starts here; it is not
        hello patience.
        """
        now = self._clock()
        self._last_command_fail_at = now
        self._last_failure_reason = reason
        self._last_failure_ha_mode = ha_mode
        self._mark_degraded()
        await publish_panel_link_state(
            self._mqtt,
            topic_prefix=self._topic_prefix,
            live=False,
        )
        poll_age = self._seconds_since(self._last_successful_trust_poll_at)
        poll_age_text = f"{poll_age:g}s ago" if poll_age is not None else "never"
        mode_text = f" ha_mode={ha_mode}" if ha_mode is not None else ""
        logger.warning(
            "Alarm Panel Connection degraded (%s)%s; keepalive_still_ok=%s; "
            "last successful trust poll %s; "
            "publishing Connection OFF. Zone/alarm entities keep last-known state.",
            reason,
            mode_text,
            self._last_keepalive_ok,
            poll_age_text,
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

    def needs_session_relogin(self) -> bool:
        """True when Connection has stayed OFF continuously past the fail window."""
        if self._live or self._degraded_since is None:
            return False
        return (self._clock() - self._degraded_since) >= self._fail_window

    def log_stuck_fail_window_expiry(self) -> None:
        """Everyday log when the stuck-trust fail window expires (before tear-down)."""
        logger.warning(
            "Alarm Panel Connection stayed off for %g seconds (stuck-trust fail window); "
            "tearing down the panel session and logging in again. "
            "Zone/alarm entities keep last-known state.",
            self._fail_window,
            extra=self._log_extra(
                reason=REASON_STUCK_FAIL_WINDOW,
                ha_mode=self._last_failure_ha_mode,
                panel_link_payload=PANEL_LINK_OFF,
            ),
        )

    async def maybe_poll(
        self,
        panel: PanelClient,
        *,
        current_alarm_payload: str | None = None,
    ) -> str | None:
        """Run a get_area_flags trust poll when the interval has elapsed."""
        if not self.poll_due():
            return None
        return await self.poll(panel, current_alarm_payload=current_alarm_payload)

    async def poll(
        self,
        panel: PanelClient,
        *,
        current_alarm_payload: str | None = None,
    ) -> str | None:
        """Ask the panel for area flags to reconcile the alarm entity only.

        This reconciliation poll does not feed Alarm Panel Connection (ADR-016):
        neither a failure nor a success here changes the connection signal —
        recovery from a degrade is driven by resumed keepalives instead (see
        ``note_keepalive_ok``). When ``settings`` is configured and the decoded
        HA payload differs from ``current_alarm_payload``, publish the snapshot
        (covers omitted AREA pushes). Returns the newly published payload, or
        None when unchanged / undecodable.
        """
        now = self._clock()
        self._last_poll_attempt_at = now
        area_size = area_size_for_zones(self._zone_count)
        try:
            flags = await panel.get_area_flags(0, AREA_FLAGS_COUNT, area_size=area_size)
        except ProtocolError:
            await self._on_poll_failure(REASON_TRUST_POLL_NAK)
            return None
        except TimeoutError:
            await self._on_poll_failure(REASON_TRUST_POLL_TIMEOUT)
            return None

        self._last_successful_trust_poll_at = self._clock()

        if self._settings is None or current_alarm_payload is None:
            return None
        decoded = decode_area_ha_state(
            flags,
            area_size=area_size,
            area_number=HOUSE_AREA_NUMBER,
            settings=self._settings,
        )
        if not flags_snapshot_may_replace_live(current_alarm_payload, decoded):
            return None
        await publish_alarm_state(
            self._mqtt,
            payload=decoded,
            topic_prefix=self._topic_prefix,
        )
        return decoded

    async def _on_poll_failure(self, reason: str) -> None:
        """Log a lone reconciliation-poll failure; never touches Connection.

        The poll no longer feeds Alarm Panel Connection (ADR-016) — an isolated
        NAK/timeout here, with keepalives/commands otherwise healthy, must not
        flip the signal OFF.
        """
        logger.debug(
            "Reconciliation poll failed (%s); keepalive_still_ok=%s. Alarm Panel "
            "Connection is unaffected — connectivity is governed only by "
            "keepalive and command-reject/timeout signals.",
            reason,
            self._last_keepalive_ok,
            extra=self._log_extra(
                reason=reason,
                ha_mode=None,
                panel_link_payload=PANEL_LINK_ON if self._live else PANEL_LINK_OFF,
            ),
        )

    def _command_failure_cleared(self) -> bool:
        if self._last_command_fail_at is None:
            return True
        return (self._clock() - self._last_command_fail_at) >= self._recover_window

    async def _maybe_recover(self, *, reason: str = REASON_KEEPALIVE_OK) -> None:
        if not self._command_failure_cleared():
            return
        if self._live:
            return
        self._live = True
        self._degraded_since = None
        await publish_panel_link_state(
            self._mqtt,
            topic_prefix=self._topic_prefix,
            live=True,
        )
        if reason == REASON_PANEL_TRAFFIC:
            cause = "receiving panel traffic"
        else:
            cause = "a successful keepalive"
        logger.info(
            "Alarm Panel Connection recovered to live after %s; publishing Connection ON.",
            cause,
            extra=self._log_extra(
                reason=reason,
                ha_mode=self._last_failure_ha_mode,
                panel_link_payload=PANEL_LINK_ON,
            ),
        )
