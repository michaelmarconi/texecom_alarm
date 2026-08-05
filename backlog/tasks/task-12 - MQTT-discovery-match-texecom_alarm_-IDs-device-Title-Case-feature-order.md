---
id: TASK-12
title: 'MQTT discovery: match texecom_alarm_* IDs, device, Title Case, feature order'
status: awaiting-review
assignee: []
created_date: '2026-08-05 11:53'
updated_date: '2026-08-05 14:47'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-003'
dependencies:
  - TASK-11
documentation:
  - docs/specs/spec-zone-monitoring.md
  - docs/specs/spec-alarm-control.md
  - docs/architecture.md
  - docs/acceptance.md
  - docs/definition-of-done.md
priority: medium
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Specs left entity naming open; live accept showed short entity IDs like front_door, ALL-CAPS friendly names, no Device grouping, and an awkward Arm Status label / button order.
**Goal:** Discovery matches today’s texecom_alarm_* entity ID scheme, groups entities under one device, Title-Cases zone names, names the alarm Texecom Alarm, and orders arm features Home→Night→Away when the platform allows.
**Why now:** Closes the easy open questions from accept and RISK-005 without a migration path — match, don’t rename.

Closes architecture/spec naming open questions as: match existing texecom_alarm_* IDs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Discovery payloads use texecom_alarm_* object_id/unique_id for zones and texecom_alarm_arm_status for the alarm panel
- [ ] #2 Zone, alarm, and panel-link discovery share one MQTT device block; zone names are Title Case; alarm name is Texecom Alarm
- [ ] #3 supported_features lists arm_home, arm_night, arm_away in that order; specs/architecture naming open questions are marked answered as match today’s IDs
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py (modify), texecom-alarm-app/src/texecom_alarm/zones.py (modify), texecom-alarm-app/tests/test_mqtt_discovery.py (modify), texecom-alarm-app/tests/test_e2e_fake_panel.py (modify), docs/specs/spec-zone-monitoring.md (modify), docs/specs/spec-alarm-control.md (modify), docs/architecture.md (modify).
1. Ensure MQTT discovery object_id/unique_id produce HA entity_ids binary_sensor.texecom_alarm_* and alarm_control_panel.texecom_alarm_arm_status (fix any path where friendly name wins over object_id).
2. Add a shared MQTT device block (identifiers/name/manufacturer/model) on zone, alarm, and panel-link discovery payloads.
3. Publish zone friendly names in Title Case derived from panel names; alarm discovery name Texecom Alarm (entity_id unchanged).
4. Set supported_features order to arm_home, arm_night, arm_away (best-effort for HA card order).
5. Close the naming Open Questions in both specs and the architecture open-question bullet to record match-today’s-IDs (no migration).
Test strategy: how we'll know = unit tests on discovery payloads (object_id, device, name casing, feature order); pytest test_mqtt_discovery.py — no live HA required for CI; manual accept re-check entity_ids in HA.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: MQTT discovery now matches texecom_alarm_* IDs (via default_entity_id), shares one device block, Title-Cases zones, names the alarm Texecom Alarm, and orders arm features Home→Night→Away.
Changed files: texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py, texecom-alarm-app/src/texecom_alarm/zones.py, texecom-alarm-app/src/texecom_alarm/config.py, texecom-alarm-app/tests/test_mqtt_discovery.py, texecom-alarm-app/tests/test_config.py, texecom-alarm-app/tests/test_zone_parse.py, texecom-alarm-app/tests/test_e2e_fake_panel.py, docs/specs/spec-zone-monitoring.md, docs/specs/spec-alarm-control.md, docs/architecture.md
Verification: unit tests on discovery payloads + FakePanel e2e; pytest -q --cov=texecom_alarm --cov-fail-under=90 → 167 passed, 93.72% coverage; ruff 0.8.4 format/check clean on changed files
Notes/assumptions: Added default_entity_id because modern HA ignores object_id for entity_id; kept _{zone_number} suffix for uniqueness. Naming open questions answered as match-today's-IDs (practitioner confirmed keep docs).

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->
