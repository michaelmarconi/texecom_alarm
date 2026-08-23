---
id: TASK-34
title: 'Checkpoint: texecom-alarm-app zone MQTT identity wave'
status: awaiting-review
assignee: []
created_date: '2026-08-23 18:42'
updated_date: '2026-08-23 19:49'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-33
ordinal: 28000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Zone identity suites pass (cd texecom-alarm-app && python -m pytest tests/test_mqtt_discovery.py tests/test_zone_parse.py tests/test_e2e_fake_panel.py -q exits 0)
- [ ] #2 FakePanel: in-use zone default_entity_id is binary_sensor.texecom_alarm_{slug}_zone_{N} and unique_id is texecom_alarm_zone_{N}; no texecom_alarm_{slug}_{N} leftovers in discovery
- [ ] #3 Build/import clean for texecom_alarm package (python -c 'import texecom_alarm' from app env / pytest collection succeeds)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- Zone identity suites pass: pass — `cd texecom_alarm && .venv/bin/python -m pytest tests/test_mqtt_discovery.py tests/test_zone_parse.py tests/test_e2e_fake_panel.py -q` exited 0 (47 passed).
- FakePanel default_entity_id / unique_id / no leftovers: pass — FakePanel e2e asserts `binary_sensor.texecom_alarm_front_door_zone_1` and `texecom_alarm_zone_1`; src has no `texecom_alarm_{slug}_{N}` identity leftovers (old IDs appear only as negative assertions).
- Build/import clean: pass — `.venv/bin/python -c "import texecom_alarm"` succeeded; pytest collected and ran the identity suites.
Notes: DoD 1–3 also hold (explicit `_zone_{N}`, Title Case / `Zone {N}` names, alarm id and `{prefix}/zone/{N}/state` unchanged, no keep-old-id path).

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Zone Entity IDs use explicit _zone_{N}; unique_id is zone-number stable with no slug (spec-zone-monitoring ACs 6–9, ADR-003)
- [ ] #2 Friendly name stays Title Case panel text without _zone_N; empty name is Zone {N}
- [ ] #3 Alarm identity and zone state topics are unchanged; there is no silent keep-the-old-id path
<!-- DOD:END -->
