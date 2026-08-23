---
id: TASK-32
title: 'Checkpoint: texecom-alarm-app ready-to-arm wave'
status: ready
assignee: []
created_date: '2026-08-23 18:37'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-30
  - TASK-31
ordinal: 26000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Ready-to-arm suites pass (cd texecom-alarm-app && python -m pytest tests/test_mqtt_discovery.py tests/test_arm_commands.py tests/test_app_mqtt.py tests/test_e2e_fake_panel.py -q exits 0)
- [ ] #2 FakePanel: matching switch off means no arm command, unchanged alarm MQTT state, and a blocked-arm event naming the mode; disarm still reaches the panel
- [ ] #3 Build/import clean for texecom_alarm package (python -c 'import texecom_alarm' from app env / pytest collection succeeds)
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Three ready-to-arm switches start on; refuse does not encode household rules (ADR-015, ADR-003)
- [ ] #2 Disarm is never gated; turning a switch off while already armed does not disarm (ADR-015)
- [ ] #3 Away remains full arm; Home/Night remain install-time Part-Arm mapping (ADR-008)
<!-- DOD:END -->
