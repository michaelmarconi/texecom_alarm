---
id: TASK-33
title: Publish zone MQTT identity as slug_zone_N with a zone-number unique_id
status: in-progress
assignee: []
created_date: '2026-08-23 18:42'
updated_date: '2026-08-23 19:12'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:low'
  - 'parallel:needs-coordination'
  - 'mode:tdd'
  - 'adr:ADR-003'
  - 'ac:AC6'
  - 'ac:AC7'
  - 'ac:AC8'
  - 'ac:AC9'
dependencies: []
documentation:
  - docs/specs/spec-zone-monitoring.md
  - docs/architecture.md
priority: high
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Zone entities still advertise as texecom_alarm_front_door_1. The trailing number looks like Home Assistant's collision suffix, and unique_id is tied to the name slug so a panel rename forks identity. TASK-12 shipped that shape; the architecture now forbids it.
**Goal:** Each in-use zone discovers as binary_sensor.texecom_alarm_{slug}_zone_{N} with unique_id texecom_alarm_zone_{N}. The on-screen name stays Title Case panel text without that marker. Old ids are not kept.
**Why now:** Independent of ready-to-arm. Both touch MQTT discovery, so merge with care; do not wait for the ready-to-arm checkpoint.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Discovery default_entity_id is binary_sensor.texecom_alarm_{slug}_zone_{N} (e.g. front_door zone 1 → binary_sensor.texecom_alarm_front_door_zone_1), not trailing _{N} and not slug-only
- [ ] #2 unique_id is zone-stable texecom_alarm_zone_{N} with no slug, so a later panel rename does not fork identity
- [ ] #3 Discovery name is Title Case panel text without _zone_N (empty name → Zone {N}); FakePanel e2e asserts both default_entity_id and unique_id
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom_alarm/src/texecom_alarm/mqtt/discovery.py (modify), texecom_alarm/src/texecom_alarm/zones.py (modify), texecom_alarm/tests/test_mqtt_discovery.py (modify), texecom_alarm/tests/test_zone_parse.py (modify), texecom_alarm/tests/test_e2e_fake_panel.py (modify). 1. object_id / default_entity_id = texecom_alarm_{slug}_zone_{N} (slug from panel name; empty name → zone). 2. unique_id = texecom_alarm_zone_{N} (slug not in unique_id). 3. discovery name stays Title Case panel text without _zone_N (empty → Zone {N}). 4. Reject texecom_alarm_{slug}_{N} and slug-only ids. 5. Do not change zone state topics or alarm identity. Keep zone_object_id / unique_id changes local so they can merge next to TASK-30's new switch helpers. Test strategy: how we'll know = unit + FakePanel; `cd texecom_alarm && python -m pytest tests/test_mqtt_discovery.py tests/test_zone_parse.py tests/test_e2e_fake_panel.py -q` — Front Door zone 1 is binary_sensor.texecom_alarm_front_door_zone_1 / unique_id texecom_alarm_zone_1; colliding names stay distinct; name has no _zone_N.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->
