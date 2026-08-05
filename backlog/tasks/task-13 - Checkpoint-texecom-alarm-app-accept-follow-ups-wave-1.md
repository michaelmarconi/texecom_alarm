---
id: TASK-13
title: 'Checkpoint: texecom-alarm-app accept follow-ups wave 1'
status: in-progress
assignee: []
created_date: '2026-08-05 11:53'
updated_date: '2026-08-05 15:00'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-10
  - TASK-11
  - TASK-12
ordinal: 8000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (pytest in texecom-alarm-app exits 0 with coverage gate)
- [ ] #2 Build/lint clean (ruff check + format --check exit 0)
- [ ] #3 E2E FakePanel path still asserts panel-link discovery/state and discovery object_id/device contracts from this wave
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 ADR-004 connectivity sensor is published retained and never drives zone/alarm availability
- [ ] #2 ADR-005 mapping remains install-time configuration (slot-oriented surface, no GETAREADETAILS auto-detect)
- [ ] #3 Naming open questions closed as match today’s texecom_alarm_* IDs
<!-- DOD:END -->
