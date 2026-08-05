---
id: TASK-12
title: 'MQTT discovery: match texecom_alarm_* IDs, device, Title Case, feature order'
status: done
assignee: []
created_date: '2026-08-05 11:53'
updated_date: '2026-08-05 14:59'
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
- [x] #1 Discovery payloads use texecom_alarm_* object_id/unique_id for zones and texecom_alarm_arm_status for the alarm panel
- [x] #2 Zone, alarm, and panel-link discovery share one MQTT device block; zone names are Title Case; alarm name is Texecom Alarm
- [x] #3 supported_features lists arm_home, arm_night, arm_away in that order; specs/architecture naming open questions are marked answered as match today’s IDs
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Attention
## Attention
Category: 2 ambiguity
Attempted: Required code review of TASK-12 (discovery IDs, device, Title Case, feature order, naming open questions answered as match-today's-IDs). Bugbot clean.
Failed: Docs/AC claim “match today’s texecom_alarm_* IDs / no migration” while zone object_ids remain texecom_alarm_{slug}_{zone_number} (e.g. texecom_alarm_front_door_1). Household inventory in docs/ha-alarm-usage-spec.md is texecom_alarm_{slug} with no number (e.g. binary_sensor.texecom_alarm_front_door). Exact match vs intentional _N divergence (collision trade-off) is unresolved.
Decision needed: (A) Drop _{zone_number} so HA entity_ids exactly match today’s texecom_alarm_<slug> inventory (accept duplicate-name collision risk), or (B) Keep _{zone_number} and amend the “match / no migration” wording to “texecom_alarm_* scheme with unique _N suffix” (documented divergence, not bit-identical IDs).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: MQTT discovery matches texecom_alarm_* scheme (default_entity_id, shared device, Title Case, Home→Night→Away); zone IDs keep _{zone_number}; docs clarified as scheme not bit-identical legacy (practitioner decision after attention).
Changed files: texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py, texecom-alarm-app/src/texecom_alarm/zones.py, texecom-alarm-app/src/texecom_alarm/config.py, texecom-alarm-app/tests/test_mqtt_discovery.py, texecom-alarm-app/tests/test_config.py, texecom-alarm-app/tests/test_zone_parse.py, texecom-alarm-app/tests/test_e2e_fake_panel.py, docs/specs/spec-zone-monitoring.md, docs/specs/spec-alarm-control.md, docs/architecture.md
Verification: pytest -q --cov=texecom_alarm --cov-fail-under=90 → 167 passed, 93.72% coverage; ruff 0.8.4 clean on changed files
Notes/assumptions: Practitioner chose keep _N + amend “match / no migration” wording. Alarm entity_id stays texecom_alarm_arm_status. Cutover automation updates deferred.

## Build phase
phase: done

## Attention
Resolved: Category 2 — keep _{zone_number}; docs amended to scheme-not-exact-match (2026-08-05).
<!-- SECTION:FINAL_SUMMARY:END -->
