---
id: TASK-29
title: 'Checkpoint: texecom-alarm-app session-heal wave'
status: awaiting-review
assignee: []
created_date: '2026-08-09 23:51'
updated_date: '2026-08-10 12:09'
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

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- #1 Rename + heal suites pass: pass — `pytest … -q` → 60 passed in 5.43s, exit 0
- #2 FakePanel health-check death → keep-trying reconnect and stuck-trust → bounded re-login: pass — covered green in `test_session_heal.py` / `test_e2e_fake_panel.py` (e.g. `test_health_check_death_heals_without_restart`, `test_trust_stuck_past_fail_window_tears_down_and_relogins`, `test_e2e_stuck_trust_fail_window_relogins_without_arm_retry`)
- #3 Build/import clean: pass — `.venv/bin/python -c 'import texecom_alarm'` exit 0; collection 60 tests OK
Notes: DoD OK — discovery name "Alarm Panel Connection"; heal keeps availability online; ADR-011 heal with no arm auto-retry; 90s fail window documented tunable in config.py/panel_trust.py.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Discovery friendly name is Alarm Panel Connection; heal paths never blank zone/alarm availability solely for panel recovery (ADR-004)
- [ ] #2 ADR-011 satisfied: health-check death reconnects; stuck trust corroborates then bounded re-login; no arm/disarm auto-retry
- [ ] #3 Fail window default 90s remains documented as tunable, not final
<!-- DOD:END -->
