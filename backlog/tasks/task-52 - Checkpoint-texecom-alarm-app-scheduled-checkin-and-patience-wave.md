---
id: TASK-52
title: 'Checkpoint: texecom-alarm-app scheduled-checkin-and-patience wave'
status: ready
assignee: []
created_date: '2026-08-28 16:14'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-49
  - TASK-50
  - TASK-51
ordinal: 46000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (pytest exits 0)
- [ ] #2 Lint/format clean (ruff check and ruff format --check exit 0)
- [ ] #3 A refused check-in that clears inside the patience window shows no connection drop; continuous refusal past the window declares dead, reconnects, and re-reads panel state; an outright disconnect still ends the session immediately
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 checkin_interval_seconds and checkin_patience_seconds are install-time settings, not hardcoded (ADR-020)
- [ ] #2 The command-rejection watchdog (ADR-011) is unmerged with and independent of the new check-in patience timer
- [ ] #3 TASK-27, TASK-45, and TASK-47's immediate-death-on-single-failure behaviour is fully superseded, not left dormant alongside the new path
<!-- DOD:END -->
