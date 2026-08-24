---
id: TASK-36
title: 'Checkpoint: texecom-alarm-app refuse-state-republish wave'
status: ready
assignee: []
created_date: '2026-08-24 13:33'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-35
ordinal: 30000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (pytest in texecom_alarm/ exits 0)
- [ ] #2 Build clean (ruff check and ruff format --check in texecom_alarm/ exit 0)
- [ ] #3 Wave end-to-end path still green: FakePanel refuse cases skip the panel, re-publish current alarm state, and emit the blocked-arm event
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Refuse still does not send the arm to the panel and does not change the Home Assistant payload (ADR-015)
- [ ] #2 Re-publish on refuse matches architecture: same current state, new MQTT publish, same pattern as a panel NAK
<!-- DOD:END -->
