---
id: TASK-54
title: 'Checkpoint: texecom-alarm-app bounded-socket-release wave'
status: ready
assignee: []
created_date: '2026-08-28 16:14'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-53
ordinal: 48000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (pytest exits 0)
- [ ] #2 Lint/format clean (ruff check and ruff format --check exit 0)
- [ ] #3 A transport that never completes wait_closed() is still released within the bounded time and the app successfully reconnects afterward
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 The bound is short relative to the reconnect interval, not itself a new install-time setting unless the practitioner asked for one
- [ ] #2 No path exists where reconnect is attempted before the previous socket's release (bounded or forced) has completed
<!-- DOD:END -->
