---
id: TASK-46
title: 'Checkpoint: texecom-alarm-app keepalive-nak-detection wave'
status: ready
assignee: []
created_date: '2026-08-27 08:59'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-45
ordinal: 40000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (cd texecom_alarm && python -m pytest -q exits 0)
- [ ] #2 Build/lint clean (pre-commit / ruff / mypy as configured exit 0)
- [ ] #3 Reconnect end-to-end suite covers both the existing keepalive-timeout case and the new keepalive-NAK case, both green
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Rejected-keepalive handling matches docs/architecture.md § Idle keepalive and § Panel-connection detection (ADR-016)
- [ ] #2 ADR-011 mid-run session heal path for the existing timeout case is unchanged
<!-- DOD:END -->
