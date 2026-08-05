---
id: TASK-11
title: Slot-oriented Part-Arm config and UDL clarity
status: awaiting-review
assignee: []
created_date: '2026-08-05 11:53'
updated_date: '2026-08-05 14:22'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:mechanical'
  - 'adr:ADR-005'
  - 'adr:ADR-003'
dependencies:
  - TASK-10
documentation:
  - >-
    docs/adrs/adr-005-use-confirmed-shared-arm-disarm-commands-with-configurable-part-arm-mapping.md
  - docs/architecture.md
  - docs/acceptance.md
  - docs/definition-of-done.md
priority: high
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Installers today set opaque Away/Night/Home mode bytes, and the UDL field is unexplained — easy to mis-map Part-Arm slots and unclear what password to use.
**Goal:** Config is slot-oriented (label which HA mode each Part-Arm slot carries, mark unused) with a clear UDL label and factory-default password default.
**Why now:** Architecture left the option shape open; accept confirmed mode bytes are the wrong UX for this house (slot 1 Night, slot 2 Home, slot 3 unused).

Coverage gap for the ADR-005 option-shape follow-on. Does not auto-detect slots from the panel.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Supervisor options express Part-Arm slots with HA mode or unused rather than raw Away/Night/Home mode-byte fields alone
- [ ] #2 UDL option documents what it is and defaults to the factory password 1234 (overridable)
- [ ] #3 Changing slot→mode mapping changes which MQTT arm mode sends which panel mode byte without code changes; unused slots are not offered as HA arm targets
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: config.yaml (modify), translations/en.yaml (modify), DOCS.md (modify), rootfs/etc/services.d/texecom_alarm/run (modify), texecom-alarm-app/src/texecom_alarm/config.py (modify), texecom-alarm-app/src/texecom_alarm/arm_commands.py (modify), texecom-alarm-app/tests/test_config.py (modify), texecom-alarm-app/tests/test_arm_commands.py (modify).
1. Replace three mode-byte fields with a slot-oriented surface (e.g. part_arm_1/2/3 → home|night|away|unused, or equivalent ordered mapping) while preserving the confirmed shared cmd=6 mode bytes under the hood.
2. Default this household’s layout in schema docs/examples: slot1=night, slot2=home, slot3=unused — still overridable per install; never hardcode only in Python constants.
3. Clarify UDL option label/description; default udl_password to 1234 in schema (overridable).
4. Keep arm_commands reading Settings so remapping slots changes which HA mode sends which mode byte without code edits.
Test strategy: how we'll know = unit tests for Settings parse + arm command byte mapping for remapped/unused slots; pytest ./texecom-alarm-app/tests/test_config.py test_arm_commands.py — no live panel.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Replaced opaque Away/Night/Home mode-byte options with slot-oriented Part-Arm mapping (plus UDL clarity/default 1234); remapping changes cmd=6 bytes without code edits.
Changed files: config.yaml, translations/en.yaml, DOCS.md, rootfs/etc/services.d/texecom_alarm/run, texecom-alarm-app/src/texecom_alarm/config.py, texecom-alarm-app/src/texecom_alarm/arm_commands.py, texecom-alarm-app/src/texecom_alarm/area_state.py, texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py, texecom-alarm-app/src/texecom_alarm/app.py, texecom-alarm-app/tests/test_config.py, texecom-alarm-app/tests/test_arm_commands.py, texecom-alarm-app/tests/test_area_state.py, texecom-alarm-app/tests/test_app_mqtt.py, texecom-alarm-app/tests/test_reconnect.py, texecom-alarm-app/tests/test_e2e_fake_panel.py
Verification: how we'll know = Settings parse + arm byte mapping for remapped/unused slots; pytest test_config + test_arm_commands green; full pytest --cov-fail-under=90 → 163 passed, 93.7% cov; ruff 0.8.4 check+format clean
Notes/assumptions: Slot N → mode byte N (SPIKE-005). Away not on any Part-Arm slot still uses full-arm mode byte 0 and remains in supported_features. Duplicate HA modes across slots raise ConfigError. Also updated area_state + discovery (needed for AC#3 / decode invert) beyond the task's likely file list.

## Build phase
phase: merging
<!-- SECTION:FINAL_SUMMARY:END -->
