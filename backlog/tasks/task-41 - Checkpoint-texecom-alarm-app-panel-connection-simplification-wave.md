---
id: TASK-41
title: 'Checkpoint: texecom-alarm-app panel-connection-simplification wave'
status: ready
assignee: []
created_date: '2026-08-25 15:27'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-39
  - TASK-40
ordinal: 35000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (pytest exits 0)
- [ ] #2 Build/lint clean
- [ ] #3 FakePanel end-to-end suite (test_e2e_fake_panel.py, test_panel_trust.py) still green
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Neither task marks the alarm or any zone entity unavailable due to a panel-link issue (ADR-004)
- [ ] #2 The ADR-011 mid-run heal path (TASK-27/TASK-28) is unchanged in behavior
- [ ] #3 docs/architecture.md's ADR-016/017 description matches the shipped behavior
<!-- DOD:END -->
