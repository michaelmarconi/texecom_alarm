---
id: TASK-29
title: 'Checkpoint: texecom-alarm-app session-heal wave'
status: in-progress
assignee: []
created_date: '2026-08-09 23:51'
updated_date: '2026-08-10 12:08'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-26
  - TASK-27
  - TASK-28
ordinal: 23000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Rename + heal suites pass (cd texecom-alarm-app && python -m pytest tests/test_mqtt_discovery.py tests/test_session_heal.py tests/test_reconnect.py tests/test_panel_trust.py tests/test_e2e_fake_panel.py -q exits 0)
- [ ] #2 FakePanel health-check death → keep-trying reconnect and stuck-trust → bounded re-login paths stay green
- [ ] #3 Build/import clean for texecom_alarm package (python -c 'import texecom_alarm' from app env / pytest collection succeeds)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Discovery friendly name is Alarm Panel Connection; heal paths never blank zone/alarm availability solely for panel recovery (ADR-004)
- [ ] #2 ADR-011 satisfied: health-check death reconnects; stuck trust corroborates then bounded re-login; no arm/disarm auto-retry
- [ ] #3 Fail window default 90s remains documented as tunable, not final
<!-- DOD:END -->
