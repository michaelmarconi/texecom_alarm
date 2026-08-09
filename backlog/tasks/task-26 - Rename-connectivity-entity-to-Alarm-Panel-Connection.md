---
id: TASK-26
title: Rename connectivity entity to Alarm Panel Connection
status: ready
assignee: []
created_date: '2026-08-09 23:50'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-004'
  - 'adr:ADR-003'
  - 'adr:ADR-011'
  - 'ac:AC5'
dependencies: []
documentation:
  - docs/specs/spec-panel-session-heal.md
  - docs/architecture.md
priority: medium
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** The freshness binary sensor still publishes as Alarm Panel Connected after an earlier rename from Panel Link, but the accepted session-heal spec and architecture now call for Alarm Panel Connection so the name matches “is the connection trustworthy?” rather than a one-shot connected reading.
**Goal:** New and rediscovered installs show Alarm Panel Connection as the connectivity entity friendly name, with discovery ids cleaned up so Home Assistant does not keep the old Connected identity.
**Why now:** Corrective follow-on to TASK-22 — architecture and session-heal AC5 require this before heal work lands under the wrong household label.

Note: Corrective for done TASK-22 (Connected → Connection).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Connectivity discovery payload friendly name is Alarm Panel Connection (not Connected)
- [ ] #2 Unit/discovery tests assert the new name and updated unique_id/object_id scheme
- [ ] #3 DOCS.md and operator log strings describe the entity as Alarm Panel Connection
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

### Files likely affected

- `texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/app.py` (modify — log strings)
- `texecom-alarm-app/src/texecom_alarm/panel_trust.py` (modify — log strings)
- `texecom-alarm-app/tests/test_mqtt_discovery.py` (modify)
- `texecom-alarm-app/tests/test_e2e_fake_panel.py` (modify)
- `DOCS.md` (modify)

### Implementation steps

1. Change MQTT discovery `name` for the connectivity sensor from "Alarm Panel Connected" to "Alarm Panel Connection".
2. Clean-refactor `unique_id` / `object_id` / state topic scheme as needed so existing HA installs do not keep the old Connected / panel_link identity (no backwards-compat soft path — architecture + session-heal spike answer). Update tests to match the chosen scheme.
3. Update operator-facing log strings and DOCS.md that still say Connected for the household-facing label.
4. Keep ADR-004 behaviour unchanged: connectivity remains separate from alarm/zone availability.

### Test strategy

How we'll know = unit/discovery assertion that payload name is Alarm Panel Connection (and unique_id/object_id match the chosen scheme). Command: `cd texecom-alarm-app && python -m pytest tests/test_mqtt_discovery.py tests/test_e2e_fake_panel.py -q`. Live HA rename/rediscovery is accept/smoke — not CI.
<!-- SECTION:PLAN:END -->
