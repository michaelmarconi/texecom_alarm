---
id: TASK-48
title: 'Checkpoint: texecom-alarm-app keepalive-retry-budget wave'
status: ready
assignee: []
created_date: '2026-08-27 19:36'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-47
ordinal: 42000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (cd texecom_alarm && python -m pytest -q exits 0)
- [ ] #2 Build/lint clean (ruff check / ruff format --check, as configured, exit 0)
- [ ] #3 Reconnect end-to-end suite covers the existing keepalive-timeout/NAK-immediate zombie case and the new bounded-retry transient-burst case, both green
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Bounded keepalive retry matches docs/architecture.md's tightened Idle keepalive / Panel-connection detection / Mid-run session heal wording, and docs/protocol-reference.md's documented behavioural constraint
- [ ] #2 TASK-45's zombie-session fix (sustained bad keepalive still degrades Connection and reconnects) has no regression
<!-- DOD:END -->
