---
id: TASK-22
title: Rename Panel Link to Alarm Panel Connected
status: awaiting-review
assignee: []
created_date: '2026-08-08 09:52'
updated_date: '2026-08-08 10:06'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-004'
  - 'adr:ADR-003'
  - 'ac:AC4'
dependencies: []
documentation:
  - docs/specs/spec-panel-link-liveness.md
priority: medium
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** The connectivity binary sensor still publishes the friendly name Panel Link, while the accepted panel-link-liveness spec and household automations expect Alarm Panel Connected. Existing installs may keep a stuck old label depending on how Home Assistant binds discovery names.
**Goal:** New and rediscovered installs show Alarm Panel Connected as the connectivity entity friendly name, with discovery tests asserting that name (and documenting any unique_id / entity-id choice needed so live installs do not stay stuck on Panel Link).
**Why now:** Architecture and RISK-013 call this ordinary plan/build work, independent of SPIKE-008 silent-death detection.

Coverage gap for panel-link-liveness AC4 / RISK-013.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Connectivity discovery payload friendly name is Alarm Panel Connected (not Panel Link)
- [ ] #2 Unit/discovery tests assert the new name (and any updated unique_id/object_id scheme)
- [ ] #3 DOCS.md describes the connectivity entity using Alarm Panel Connected
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

Files likely affected: texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py (modify), texecom-alarm-app/tests/test_mqtt_discovery.py (modify), texecom-alarm-app/tests/test_e2e_fake_panel.py (modify if it asserts Panel Link), DOCS.md (modify), docs/acceptance.md or docs/run.md only if rename/rediscovery steps are documented there.

1. Change MQTT discovery `name` for the connectivity sensor from "Panel Link" to "Alarm Panel Connected".
2. Decide whether `unique_id` / `object_id` / `default_entity_id` must change so existing HA installs pick up the new friendly name (RISK-013); if changed, update tests and document the rediscovery/wipe note for local installs.
3. Update DOCS.md wording that still says Panel Link for the household-facing label.
4. Keep ADR-004 behaviour unchanged: connectivity is separate from alarm/zone availability.

Test strategy: how we'll know = unit/discovery assertions that payload name is Alarm Panel Connected (and unique_id/object_id match the chosen scheme); command: cd texecom-alarm-app && python -m pytest tests/test_mqtt_discovery.py tests/test_e2e_fake_panel.py -q. Live HA rename outcome is accept/smoke after rediscovery — not CI.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Connectivity discovery friendly name is now Alarm Panel Connected; unique_id/object_id kept stable with a DOCS rediscovery note.
Changed files: texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py, texecom-alarm-app/tests/test_mqtt_discovery.py, texecom-alarm-app/tests/test_e2e_fake_panel.py, DOCS.md
Verification: how we'll know = unit/discovery assertions that payload name is Alarm Panel Connected; command: cd texecom-alarm-app && python -m pytest tests/test_mqtt_discovery.py tests/test_e2e_fake_panel.py -q → 28 passed; full suite pytest -q --cov=texecom_alarm --cov-fail-under=90 → 196 passed, 92.80% coverage; ruff clean on changed files.
Notes/assumptions: Kept unique_id/object_id/default_entity_id as texecom_alarm_panel_link (no migration) — no code evidence that HA requires an ID change; DOCS.md notes rebuild/rediscovery may be needed for live installs to refresh the label. Pre-existing ruff format drift in untouched app.py/client.py/test_reconnect.py left alone.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->
