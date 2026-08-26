---
id: TASK-44
title: 'Checkpoint: texecom-alarm-app line-defense-retirement wave'
status: ready
assignee: []
created_date: '2026-08-26 17:19'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-42
  - TASK-43
ordinal: 38000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (cd texecom_alarm && python -m pytest -q exits 0)
- [ ] #2 Build/lint clean (no lint errors in texecom_alarm/src or texecom_alarm/tests)
- [ ] #3 No trace of the retired behaviour remains: grep across texecom_alarm/src and DOCS.md finds no resync/skip path, no ReconnectProfile, and no reconnect_normal_*/reconnect_trigger_* settings
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 config.yaml, config.py, and translations/en.yaml agree on exactly one reconnect-wait setting (reconnect_delay_seconds)
- [ ] #2 ADR-018 and ADR-019 constraints are not violated by either task in this wave
- [ ] #3 DOCS.md's Reconnect behaviour section matches the single-interval, no-resync behaviour
<!-- DOD:END -->
