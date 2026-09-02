---
id: TASK-66
title: 'Checkpoint: texecom-alarm-app busy command-wait session wave'
status: in-progress
assignee: []
created_date: '2026-09-02 10:51'
updated_date: '2026-09-02 12:19'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-64
  - TASK-65
ordinal: 60000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (cd texecom_alarm && python -m pytest -q exits 0)
- [ ] #2 Coverage and lint bars still hold (pytest --cov=texecom_alarm --cov-fail-under=90; ruff check + ruff format --check)
- [ ] #3 FakePanel e2e: timeout-with-events then new-request ACK keeps Connection on; silent timeout and NAK still turn Connection off immediately
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Session health in docs/architecture.md matches ADR-022: busy Arm/Disarm wait retries as a new request; Connection off on refuse, silent timeout, or exhausted retries
- [ ] #2 ADR-022 live-only walks (real trigger-then-Disarm flood) are not claimed by CI
- [ ] #3 No skip-and-resync path was reintroduced
<!-- DOD:END -->
