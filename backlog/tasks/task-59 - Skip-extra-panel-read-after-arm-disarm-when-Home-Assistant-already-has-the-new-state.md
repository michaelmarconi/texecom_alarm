---
id: TASK-59
title: >-
  Skip extra panel read after arm/disarm when Home Assistant already has the new
  state
status: in-progress
assignee: []
created_date: '2026-08-31 21:19'
updated_date: '2026-08-31 21:35'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-021'
  - 'adr:ADR-009'
  - 'adr:ADR-004'
  - 'ac:AC4'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-021-use-one-busy-versus-dead-session-model-for-panel-connection-health.md
  - docs/specs/spec-panel-session-heal.md
priority: medium
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** After a successful arm or disarm, the add-on still immediately asks the panel for a full area-flags snapshot even when live events have already published the new alarm state. That extra question is how a busy line after a tap that already worked gets mistaken for a dead panel.
**Goal:** After a successful tap, do not send that extra snapshot read when Home Assistant already has the new alarm state. Still send it when live events did not publish the new state (Home-disarm that omits an area update is the known case), and still take snapshots after login and reconnect.
**Why now:** Corrective for TASK-7 — ADR-021 forbids piling that housekeeping read onto a burst whose answer already arrived.

Corrective for TASK-7 (left done; this task is the rework).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After a successful arm or disarm ACK, FakePanel does not receive GetAreaFlags when live AREA/LOG already published the new alarm state
- [ ] #2 After a successful Home disarm that omits an AREA update, GetAreaFlags still runs and the alarm entity is updated from that snapshot
- [ ] #3 Login and reconnect snapshots still run; the reconciliation poll is unchanged
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

Today `_refresh_alarm_from_flags` always calls `get_area_flags` after ACK, then may skip *publishing*. Skip the round-trip itself when `flags_snapshot_may_replace_live` would refuse the publish (live AREA/LOG already matches). Keep the round-trip when the guard would allow replace (Home-disarm omitting AREA; no live update yet).

### Files likely affected

- `texecom_alarm/src/texecom_alarm/arm_commands.py` (modify)
- `texecom_alarm/src/texecom_alarm/alarm_flags_guard.py` (modify if the skip-round-trip helper belongs here)
- `texecom_alarm/tests/test_arm_commands.py` (modify)
- `texecom_alarm/tests/test_alarm_flags_guard.py` (modify)
- `texecom_alarm/tests/test_e2e_fake_panel.py` (modify — must not require GetAreaFlags after every arm/disarm ACK)

### Test strategy

How we'll know: unit + end-to-end against FakePanel. Command: `cd texecom_alarm && python -m pytest tests/test_arm_commands.py tests/test_alarm_flags_guard.py tests/test_e2e_fake_panel.py -q`. FakePanel records whether `GetAreaFlags` ran after ACK. Assert: omitted when live AREA already published the new state; still runs when it has not (Home-disarm omit-AREA). Do not restore skip-and-resync. Live garage-return remains `/accept`.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: provisioned
<!-- SECTION:FINAL_SUMMARY:END -->
