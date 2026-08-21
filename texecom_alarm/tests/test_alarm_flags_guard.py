"""Unit tests for flags-snapshot vs live AREA transient guard."""

from __future__ import annotations

from texecom_alarm.alarm_flags_guard import (
    coerce_flags_payload_after_disarm,
    flags_snapshot_may_replace_live,
)


def test_coerce_after_disarm_maps_armed_to_disarmed() -> None:
    assert coerce_flags_payload_after_disarm("armed_away") == "disarmed"
    assert coerce_flags_payload_after_disarm("armed_home") == "disarmed"
    assert coerce_flags_payload_after_disarm("disarmed") == "disarmed"
    assert coerce_flags_payload_after_disarm("triggered") == "triggered"


def test_flags_guard_blocks_settled_overwrite_of_transient_on_poll() -> None:
    """Trust poll must not clear exit with lagging disarmed flags."""
    assert flags_snapshot_may_replace_live("arming", "armed_away") is False
    assert flags_snapshot_may_replace_live("pending", "armed_home") is False
    assert flags_snapshot_may_replace_live("arming", "disarmed") is False
    assert flags_snapshot_may_replace_live("pending", "disarmed") is False
    assert flags_snapshot_may_replace_live("arming", "triggered") is True


def test_flags_guard_after_disarm_settles_transient() -> None:
    assert flags_snapshot_may_replace_live("arming", "disarmed", after_disarm=True) is True
    assert flags_snapshot_may_replace_live("pending", "disarmed", after_disarm=True) is True
    # Callers coerce armed_* → disarmed before this check on the disarm path.
    assert flags_snapshot_may_replace_live("arming", "armed_away", after_disarm=True) is False


def test_flags_guard_after_disarm_clears_triggered_not_rearms() -> None:
    assert flags_snapshot_may_replace_live("triggered", "disarmed", after_disarm=True) is True
    assert flags_snapshot_may_replace_live("triggered", "armed_away", after_disarm=True) is False
    # Trust poll must not overwrite triggered with lagging armed_*.
    assert flags_snapshot_may_replace_live("triggered", "armed_home") is False
    assert flags_snapshot_may_replace_live("triggered", "disarmed") is True


def test_flags_guard_blocks_stale_disarmed_after_arm() -> None:
    assert flags_snapshot_may_replace_live("disarmed", "disarmed", after_arm=True) is False
    assert flags_snapshot_may_replace_live(None, "disarmed", after_arm=True) is False
    assert flags_snapshot_may_replace_live("disarmed", "armed_home", after_arm=True) is True
    assert flags_snapshot_may_replace_live("arming", "disarmed", after_arm=True) is False


def test_flags_guard_allows_settled_corrections() -> None:
    assert flags_snapshot_may_replace_live("armed_home", "disarmed") is True
    assert flags_snapshot_may_replace_live("disarmed", "armed_night") is True
