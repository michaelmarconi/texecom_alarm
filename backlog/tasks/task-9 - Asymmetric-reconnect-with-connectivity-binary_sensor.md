---
id: TASK-9
title: Asymmetric reconnect with connectivity binary_sensor
status: in-progress
assignee: []
created_date: '2026-08-04 12:52'
updated_date: '2026-08-04 17:21'
labels:
  - 'container:texecom-alarm-app'
  - 'size:L'
  - 'risk:high'
  - 'parallel:needs-coordination'
  - 'mode:tdd'
  - 'adr:ADR-002'
  - 'adr:ADR-004'
  - 'adr:ADR-006'
  - 'adr:ADR-007'
  - 'adr:ADR-003'
  - 'ac:AC-3'
  - 'ac:AC-6'
dependencies:
  - TASK-8
documentation:
  - >-
    docs/adrs/adr-002-use-frame-resync-and-asymmetric-reconnect-for-panel-protocol-collisions.md
  - >-
    docs/adrs/adr-004-use-app-liveness-unavailability-and-trigger-snapshots-for-panel-link-outages.md
  - docs/adrs/adr-006-use-panel-zone-state-snapshot-for-startup-re-sync.md
  - docs/adrs/adr-007-use-panel-area-flags-snapshot-for-alarm-startup-re-sync.md
  - >-
    docs/adrs/adr-003-use-mqtt-discovery-not-native-integration-for-entity-surfacing.md
  - docs/specs/spec-alarm-control.md
  - docs/definition-of-done.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** The app already survives garbage on the wire and detects a forced panel disconnect, but once the TCP link drops it does not reconnect — and there is no separate Home Assistant signal for panel-link health, so the household cannot tell live alarm/zone state from stale state during an outage.
**Goal:** After a panel disconnect, the app reconnects with a longer tunable budget when the drop followed a real trigger than after an ordinary arm/disarm, publishes degraded panel-link health on a dedicated connectivity sensor, and never marks alarm or zone entities unavailable because of the panel link.
**Why now:** Wave 1 (protocol, discovery, zone/alarm state, arm/disarm) is done; this is the next ADR-002/ADR-004 reliability slice after the last-trigger snapshot task.

Note: Reconnect timing defaults (~10s normal / ~90s trigger) rest on a single SPIKE-002 data point; CI proves behaviour against FakePanel with shortened settings, not live panel recovery timing. File overlap with TASK-8 (`app.py`, `mqtt/discovery.py`, discovery/E2E tests) → needs-coordination; build or merge TASK-8 before dispatching this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After FakePanel forces a disconnect while last alarm state is not `triggered`, the app reconnects using the normal budget settings, publishes connectivity OFF then ON, and re-runs LOGIN + zone + area snapshots + SETEVENTMESSAGES without changing alarm/zone availability topics.
- [ ] #2 After a disconnect that follows a `triggered` alarm decode, the app uses the longer trigger budget settings (verifiable via injected short intervals / attempt counts in tests).
- [ ] #3 Connectivity discovery is a separate `binary_sensor` (`texecom_alarm_panel_link`); zone and alarm discovery continue to use only the app LWT availability topic (not panel-link state).
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

### Implementation steps

1. Add install-time reconnect settings on `Settings` / `config.yaml`: `reconnect_normal_attempts` (default 4), `reconnect_normal_interval_seconds` (default 2.5 → ~10s), `reconnect_trigger_attempts` (default 18), `reconnect_trigger_interval_seconds` (default 5 → ~90s). Tunable — not final hardcodes (ADR-002 / AGENTS.md). Wire through `config.py` env/options parsing with the same patterns as existing optional ints (interval may be float — use a float optional helper or store as float seconds).
2. Create `texecom-alarm-app/src/texecom_alarm/reconnect.py`: on `ForcedDisconnect` (or peer close), publish connectivity OFF; choose the **trigger** profile if the last decoded HOUSE alarm MQTT payload was `triggered`, else the **normal** profile; then loop: close panel → sleep interval → `connect` → `login` → `publish_zone_state_snapshot` → `publish_area_state_snapshot` → `set_event_messages` → publish connectivity ON and return. After exhausting the profile's attempt count, keep retrying at that profile's interval indefinitely (never exit the process — exiting would fire MQTT LWT and blank alarm/zone entities, violating ADR-004). Reuse the already-enumerated in-use zone list (do **not** re-enumerate on reconnect — architecture Resume is LOGIN + snapshots + SETEVENTMESSAGES only).
3. Extend `texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py`: add connectivity helpers — object_id `texecom_alarm_panel_link`, discovery topic `homeassistant/binary_sensor/texecom_alarm_panel_link/config`, state topic `{prefix}/panel_link/state`, `device_class` `connectivity`, `payload_on` `ON` / `payload_off` `OFF` (live / degraded), shared `availability_topic` (app LWT) identical to zones/alarm. Publish retained discovery alongside existing discovery; publish initial connectivity ON after successful startup snapshots (panel link live).
4. Wire `texecom-alarm-app/src/texecom_alarm/app.py`: track last published HOUSE alarm payload (from area snapshot + live AREA handler path) for budget selection; catch `ForcedDisconnect` from the panel listen loop and invoke the reconnect helper; after successful resume, continue listening. Do **not** publish offline on zone/alarm availability topics during panel-link recovery — only flip the connectivity sensor. Coordinate with TASK-8's listen-loop / discovery edits on the same files.
5. Tests: extend FakePanel as needed for mid-session drop that allows a second TCP accept; unit-test reconnect profile selection + MQTT connectivity OFF→ON + post-reconnect command sequence (LOGIN, GetZoneState, GetAreaFlags, SETEVENTMESSAGES); update discovery/config/E2E tests. Use shortened reconnect settings in tests for speed.

### Files likely affected

- `texecom-alarm-app/src/texecom_alarm/reconnect.py` (create)
- `texecom-alarm-app/src/texecom_alarm/config.py` (modify)
- `config.yaml` (modify)
- `texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/app.py` (modify)
- `texecom-alarm-app/tests/fake_panel.py` (modify)
- `texecom-alarm-app/tests/test_reconnect.py` (create)
- `texecom-alarm-app/tests/test_config.py` (modify)
- `texecom-alarm-app/tests/test_mqtt_discovery.py` (modify)
- `texecom-alarm-app/tests/test_e2e_fake_panel.py` (modify)
- `DOCS.md` (modify)

### Test strategy

`cd texecom-alarm-app && python -m pytest tests/test_reconnect.py tests/test_config.py tests/test_mqtt_discovery.py tests/test_e2e_fake_panel.py -q` — FakePanel forced drop with/without prior `triggered`; connectivity OFF then ON; post-reconnect LOGIN + zone/area snapshots + SETEVENTMESSAGES; shortened budgets for speed; zone/alarm discovery still use app LWT only.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 docs/definition-of-done.md
<!-- DOD:END -->
