---
id: TASK-38
title: 'Checkpoint: texecom-alarm-app refuse-arming-bounce wave'
status: ready
assignee: []
created_date: '2026-08-24 16:10'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-37
documentation:
  - docs/specs/spec-ready-to-arm.md
  - docs/architecture.md
ordinal: 32000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (pytest in texecom_alarm/ exits 0)
- [ ] #2 Build clean (ruff check and ruff format --check in texecom_alarm/ exit 0)
- [ ] #3 Wave end-to-end FakePanel refuse path: no panel arm; MQTT arming then pre-command payload; blocked-arm event names mode only
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 ADR-015: refuse does not send the arm to the panel; disarm is not gated; switch-off while armed does not disarm
- [ ] #2 Architecture: refuse publishes MQTT arming then current alarm state (not a duplicate-only republish)
<!-- DOD:END -->
