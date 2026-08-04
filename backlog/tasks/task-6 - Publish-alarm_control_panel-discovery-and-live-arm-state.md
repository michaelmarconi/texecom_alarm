---
id: TASK-6
title: Publish alarm_control_panel discovery and live arm state
status: awaiting-review
assignee: []
created_date: '2026-08-04 12:52'
updated_date: '2026-08-04 16:37'
labels:
  - 'container:texecom-alarm-app'
  - 'size:L'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-007'
  - 'adr:ADR-003'
  - 'adr:ADR-004'
  - 'adr:ADR-005'
  - 'adr:ADR-006'
dependencies:
  - TASK-5
documentation:
  - docs/adrs/adr-007-use-panel-area-flags-snapshot-for-alarm-startup-re-sync.md
  - >-
    docs/adrs/adr-005-use-confirmed-shared-arm-disarm-commands-with-configurable-part-arm-mapping.md
  - >-
    docs/adrs/adr-003-use-mqtt-discovery-not-native-integration-for-entity-surfacing.md
  - >-
    docs/adrs/adr-004-use-app-liveness-unavailability-and-trigger-snapshots-for-panel-link-outages.md
  - docs/specs/spec-alarm-control.md
  - docs/definition-of-done.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Zone entities are discovered and kept current via snapshot plus live pushes, but Home Assistant still has no MQTT alarm panel entity — so arm state is invisible and a restart would leave any future entity guessing disarmed.
**Goal:** Home Assistant gets one MQTT-discovered alarm entity whose state matches the panel after startup (area-flags snapshot) and then tracks live area events for armed/disarmed/triggered and exit/entry.
**Why now:** Unblocked and next — zone live path (TASK-5) and the area-flags startup decision (ADR-007) are both done.

Note: Exit/entry (arming/pending) come from live AREA pushes only; the area-flags snapshot covers settled Disarmed/Armed/PartArmed/InAlarm (ADR-007 follow-on — flags were only proven Disarmed live). Live AREA bytes 6/7 → armed_night/armed_home follow the protocol working hypothesis; CI proves FakePanel flag decode + injected AREA pushes for 0/3/5 (and PartArmed via flags), not a live Night/Home arm cycle. Discovery includes a command_topic for a later arm/disarm task; this task does not subscribe or send arm/disarm.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After FakePanel login + enumeration, GetAreaFlags drives a retained MQTT alarm state matching the decoded flags for area 1 (quiet panel → disarmed); unused areas get no entity.
- [ ] #2 An injected AREA push updates {prefix}/alarm/state to the matching HA payload (0→disarmed, 3→armed_away, 5→triggered at minimum).
- [ ] #3 Retained MQTT discovery creates alarm_control_panel with unique_id/object_id texecom_alarm_arm_status, shared availability topic, and arm_home/away/night features — without marking the entity unavailable due to panel-link health.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

### Implementation steps

1. Add `CMD_GET_AREA_FLAGS = 11` in `texecom-alarm-app/src/texecom_alarm/protocol/frame.py`. Extend `PanelClient` in `texecom-alarm-app/src/texecom_alarm/protocol/client.py` with `get_area_flags(start, count)` that returns exactly `count * area_size` bytes. For Elite 88: `area_size=1` from the zone-count map `{88: 8}` → `ceil(8/8)=1`, request `start=0 count=72` (same construction as SPIKE-007 / ADR-007).
2. Create `texecom-alarm-app/src/texecom_alarm/area_state.py` (mirror `zone_state.py`):
   - Shared flag-bit decode priority: Alarm → `triggered`; Armed/FullArmed/ForceArmed → `armed_away`; PartArmed + slot → `armed_night` / `armed_home` / `armed_away` via inverted `Settings.part_arm_*` (ADR-005); else `disarmed`.
   - `publish_area_state_snapshot` after the zone snapshot; publish retained MQTT for **area 1 only** (HOUSE on this Elite 88).
   - Live AREA handler (`body[0]==MSG_AREA`): map state bytes `0→disarmed`, `1→arming`, `2→pending`, `3→armed_away`, `4→arming`, `5→triggered`, `6→armed_night`, `7→armed_home`.
   - Never send arm/disarm/omit command bytes during the area-flags snapshot.
3. Extend `texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py`:
   - `object_id` / `unique_id` = `texecom_alarm_arm_status`.
   - Discovery topic `homeassistant/alarm_control_panel/{id}/config`.
   - State topic `{prefix}/alarm/state`; shared availability topic (same LWT pattern as zones — ADR-004).
   - `supported_features` include arm_home / arm_away / arm_night.
   - `command_topic` `{prefix}/alarm/command` (no subscriber in this task — DRAFT-3).
   - `code_arm_required` / `code_disarm_required` = false.
4. Wire `texecom-alarm-app/src/texecom_alarm/app.py`: after zone discovery + zone snapshot, publish alarm discovery + area-flags snapshot (area 1), then SETEVENTMESSAGES; extend the listen loop to handle `MSG_AREA` as well as `MSG_ZONE` (pass `Settings` for Part-Arm mapping).
5. Extend `texecom-alarm-app/tests/fake_panel.py` with GetAreaFlags + injectable AREA frames; add/extend unit and E2E tests for flag decode, snapshot publish, live AREA push, and discovery payload shape.

### Files likely affected

- `texecom-alarm-app/src/texecom_alarm/protocol/frame.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/protocol/client.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/area_state.py` (create)
- `texecom-alarm-app/src/texecom_alarm/app.py` (modify)
- `texecom-alarm-app/tests/fake_panel.py` (modify)
- `texecom-alarm-app/tests/test_area_state.py` (create)
- `texecom-alarm-app/tests/test_mqtt_discovery.py` (modify)
- `texecom-alarm-app/tests/test_protocol_client.py` (modify)
- `texecom-alarm-app/tests/test_e2e_fake_panel.py` (modify)

### Test strategy

`cd texecom-alarm-app && python -m pytest tests/test_area_state.py tests/test_mqtt_discovery.py tests/test_protocol_client.py tests/test_e2e_fake_panel.py -q` — FakePanel GetAreaFlags → retained alarm state; injected AREA push updates state; discovery payload shape; no arm/omit cmds during snapshot.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: MQTT alarm_control_panel discovery plus GetAreaFlags startup snapshot and live AREA state updates for area 1.
Changed files: texecom-alarm-app/src/texecom_alarm/protocol/frame.py, texecom-alarm-app/src/texecom_alarm/protocol/client.py, texecom-alarm-app/src/texecom_alarm/area_state.py, texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py, texecom-alarm-app/src/texecom_alarm/app.py, texecom-alarm-app/tests/fake_panel.py, texecom-alarm-app/tests/test_area_state.py, texecom-alarm-app/tests/test_mqtt_discovery.py, texecom-alarm-app/tests/test_protocol_client.py, texecom-alarm-app/tests/test_e2e_fake_panel.py, texecom-alarm-app/tests/test_app_mqtt.py
Verification: pytest --cov=texecom_alarm --cov-fail-under=90 — 115 passing, 93% coverage; ruff check/format clean; bandit -r src -ll clean
Notes/assumptions: FakePanel app-path fixtures use zone_count=12 (smallest AREA_MAP entry) so area_size derivation works in CI without inventing map keys; Elite 88 path (start=0, count=72, area_size=1) is implemented; area_size==8 dual-request raises ProtocolError (ADR-007 follow-on); PartArm slot → HA mode via inverted Settings.part_arm_*; command_topic published with no subscriber (DRAFT-3).

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->
