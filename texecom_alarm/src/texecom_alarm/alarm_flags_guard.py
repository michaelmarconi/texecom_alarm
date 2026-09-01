"""Helpers for when GetAreaFlags may safely update live alarm MQTT."""

from __future__ import annotations

# Exit/entry states come from live AREA pushes — flag snapshots never encode them.
_TRANSIENT_ALARM_STATES = frozenset({"arming", "pending"})


def coerce_flags_payload_after_disarm(decoded_payload: str) -> str:
    """After a disarm ACK, lagging armed_* flags are treated as unset."""
    if decoded_payload.startswith("armed_"):
        return "disarmed"
    return decoded_payload


def flags_round_trip_needed_after_command(
    current_payload: str | None,
    *,
    after_arm: bool = False,
    after_disarm: bool = False,
) -> bool:
    """Return whether to send GetAreaFlags after a successful arm/disarm ACK.

    Live AREA/LOG already carrying the new alarm state is the answer; do not
    ask the panel again. After a successful arm ACK, never send a flags read:
    MQTT is often still unset until the exit AREA push, and asking during that
    burst collides with interleaved events. Home disarm that omits an AREA
    update still needs the read because MQTT is still on the previous armed,
    triggered, or exit payload.
    """
    if after_arm:
        return False
    if after_disarm:
        return current_payload != "disarmed"
    return True


def flags_snapshot_may_replace_live(
    current_payload: str | None,
    decoded_payload: str,
    *,
    after_arm: bool = False,
    after_disarm: bool = False,
) -> bool:
    """Return whether a flags-derived payload should overwrite live MQTT/HA state.

    Area-flags decode only yields settled states (disarmed / armed_* / triggered).
    During exit/entry the flag block often still reads disarmed, so trust polls must
    not publish ``disarmed`` over ``arming``/``pending``. After a successful disarm
    ACK, ``disarmed`` (including coerced lagging ``armed_*``) may replace a
    transient or a still-``triggered`` state. After a successful arm ACK, a
    still-disarmed flag read is lag, not truth. ``triggered`` may always replace
    a transient. Callers must run ``coerce_flags_payload_after_disarm`` before
    this check on the post-disarm path.
    """
    if current_payload is not None and decoded_payload == current_payload:
        return False
    if after_arm and decoded_payload == "disarmed":
        return False
    # Never publish armed_* after a disarm ACK (coercion should have removed these).
    if after_disarm and decoded_payload.startswith("armed_"):
        return False
    # Alarm-in-progress: only triggered/disarmed corrections — not lagging armed_*.
    if current_payload == "triggered" and decoded_payload.startswith("armed_"):
        return False
    if current_payload in _TRANSIENT_ALARM_STATES and decoded_payload != "triggered":
        return bool(after_disarm and decoded_payload == "disarmed")
    return True
