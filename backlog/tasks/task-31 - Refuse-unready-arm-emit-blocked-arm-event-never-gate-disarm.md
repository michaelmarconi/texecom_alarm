---
id: TASK-31
title: 'Refuse unready arm, emit blocked-arm event, never gate disarm'
status: awaiting-review
assignee: []
created_date: '2026-08-23 18:34'
updated_date: '2026-08-24 08:38'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-015'
  - 'adr:ADR-003'
  - 'adr:ADR-008'
  - 'ac:AC2'
  - 'ac:AC3'
  - 'ac:AC4'
  - 'ac:AC5'
  - 'ac:AC6'
  - 'ac:AC7'
  - 'ac:AC8'
dependencies:
  - TASK-30
documentation:
  - >-
    docs/adrs/adr-015-use-ready-to-arm-switches-and-mqtt-blocked-arm-event-for-unready-arm-refusal.md
  - docs/specs/spec-ready-to-arm.md
priority: high
ordinal: 25000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** MQTT arm commands still go to the panel even when a ready-to-arm switch is off, so an open door can set the alarm. TASK-7 shipped that always-forward path.
**Goal:** If the matching switch is off, that arm does not reach the panel, the alarm stays as it was, and Home Assistant gets an MQTT event naming the mode — not why. Disarm always works. Turning a switch off while already armed does not disarm.
**Why now:** Corrects TASK-7 against ADR-015 once the switches exist (TASK-30). Parent: ready-to-arm refuse wave.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Matching switch off: FakePanel receives no arm command and alarm MQTT state stays unchanged, including when the payload arrives on Home Assistant's alarm command topic
- [ ] #2 That refuse publishes an MQTT event that names the blocked mode and does not include a household reason
- [ ] #3 Disarm still reaches the panel with every switch off, and turning a switch off while armed does not disarm
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom-alarm-app/src/texecom_alarm/arm_commands.py (modify), texecom-alarm-app/src/texecom_alarm/app.py (modify), texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py (modify), texecom-alarm-app/tests/test_arm_commands.py (modify), texecom-alarm-app/tests/test_e2e_fake_panel.py (modify), texecom-alarm-app/tests/test_app_mqtt.py (modify), texecom-alarm-app/tests/fake_panel.py (modify if assertions on commands sent). 1. Before ARM_AWAY/HOME/NIGHT, if matching switch is off: do not send panel arm; do not change alarm MQTT state; publish MQTT event entity with mode only. 2. Same refuse when the request is the alarm command topic Home Assistant uses. 3. DISARM never consults switches. 4. Switch off while armed does not send disarm. Test strategy: how we'll know = unit + FakePanel integration; `cd texecom-alarm-app && python -m pytest tests/test_arm_commands.py tests/test_e2e_fake_panel.py tests/test_app_mqtt.py -q` — off switch: no arm command, state unchanged, event with mode; disarm still sent; switch-off while armed sends no disarm.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Unready arm is refused (no panel command, alarm MQTT unchanged), a blocked-arm MQTT event names the mode only, and disarm is never gated.
Changed files: README.md, DOCS.md, docs/reference/mqtt.md, texecom_alarm/CHANGELOG.md, texecom_alarm/DOCS.md, texecom_alarm/README.md, texecom_alarm/src/texecom_alarm/app.py, texecom_alarm/src/texecom_alarm/arm_commands.py, texecom_alarm/src/texecom_alarm/mqtt/discovery.py, texecom_alarm/tests/test_app_mqtt.py, texecom_alarm/tests/test_arm_commands.py, texecom_alarm/tests/test_e2e_fake_panel.py, texecom_alarm/tests/test_mqtt_discovery.py
Verification: python -m pytest tests/test_arm_commands.py tests/test_e2e_fake_panel.py tests/test_app_mqtt.py -q → 64 passed; ruff check . and ruff format --check . → clean; pytest --cov=texecom_alarm --cov-fail-under=90 → 332 passed, 92.55% coverage.
Notes/assumptions: Existing tests that mention older TASK/AC labels were left as-is; new product code and TASK-31 tests do not cite pipeline IDs. config.yaml version was not bumped. Ready-to-arm switches were not re-implemented. After commit, main was merged into task-31 so TASK-33 zone MQTT identity is preserved.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->
