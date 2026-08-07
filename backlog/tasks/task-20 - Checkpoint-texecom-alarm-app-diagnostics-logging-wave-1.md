---
id: TASK-20
title: 'Checkpoint: texecom-alarm-app diagnostics-logging wave 1'
status: ready
assignee: []
created_date: '2026-08-07 17:22'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-18
  - TASK-19
documentation:
  - docs/specs/spec-diagnostics-logging.md
ordinal: 15000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 texecom-alarm-app tests pass (pytest exits 0)
- [ ] #2 log_level schema tokens are WARNING|INFO|DEBUG|TRACE and default INFO is covered by tests
- [ ] #3 DEBUG/TRACE/modem-skip integration coverage from TASK-19 is green
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 spec-diagnostics-logging AC1–AC6 satisfied by TASK-18/19
- [ ] #2 AC7 (live TRACE hunt correlating a real zone event to add-on logs) remains manual acceptance — exercise when convenient after merge
- [ ] #3 docs/plan.md scope map notes diagnostics-logging wave
<!-- DOD:END -->
