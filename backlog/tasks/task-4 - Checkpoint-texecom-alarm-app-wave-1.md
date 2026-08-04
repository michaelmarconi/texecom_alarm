---
id: TASK-4
title: 'Checkpoint: texecom-alarm-app wave 1'
status: in-progress
assignee: []
created_date: '2026-08-04 12:52'
updated_date: '2026-08-04 15:18'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-1
  - TASK-2
  - TASK-3
ordinal: 4000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (pytest in texecom-alarm-app/ exits 0), including FakePanel + Mosquitto (Docker) E2E — never live panel or household broker
- [ ] #2 Build and lint clean (pip install -e ".[dev]", ruff check, ruff format --check)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Unused zones are not published; discovery is MQTT-only (ADR-001, ADR-003)
- [ ] #2 Frame resync does not fatal on garbage bytes (ADR-002); entity availability uses app LWT not panel-link (ADR-004)
- [ ] #3 Part-Arm mapping remains install-time config fields, not hardcoded household layout (ADR-005)
<!-- DOD:END -->
