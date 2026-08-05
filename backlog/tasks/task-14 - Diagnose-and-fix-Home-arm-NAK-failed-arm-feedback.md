---
id: TASK-14
title: Diagnose and fix Home arm NAK + failed-arm feedback
status: awaiting-review
assignee: []
created_date: '2026-08-05 11:54'
updated_date: '2026-08-05 19:36'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-005'
  - 'adr:ADR-003'
  - 'adr:ADR-004'
  - 'ac:AC-1'
  - 'ac:AC-2'
dependencies:
  - TASK-13
documentation:
  - >-
    docs/adrs/adr-005-use-confirmed-shared-arm-disarm-commands-with-configurable-part-arm-mapping.md
  - docs/acceptance.md
  - docs/protocol-reference.md
  - docs/definition-of-done.md
priority: high
ordinal: 9000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Live accept showed Home arm reaching the panel and getting NAK — HA stayed Disarmed but the card left Home selected, so the household cannot tell command failure from success.
**Goal:** Home arm either arms successfully on a clean panel, or HA remains Disarmed with honest feedback after a panel rejection (no stuck optimistic Home).
**Why now:** Corrective follow-on to arm/disarm work (TASK-7); accept scored Home arm as fail and blocked daytime re-walk until the root cause is understood.

Corrective for TASK-7. Do not assume open windows are the cause without corroboration.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 When FakePanel NAKs an arm command, the app republishes the current alarm state so HA does not remain on a stuck armed_* selection
- [ ] #2 Successful ARM_HOME still sends the configured Home Part-Arm mode byte and FakePanel ACK path remains green
- [ ] #3 Root cause of the live Home NAK is documented in the task final summary (app bug vs panel reject vs mapping) with any code fix applied
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom-alarm-app/src/texecom_alarm/arm_commands.py (modify), texecom-alarm-app/src/texecom_alarm/protocol/client.py (modify), texecom-alarm-app/src/texecom_alarm/app.py (modify), texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py (modify), texecom-alarm-app/tests/fake_panel.py (modify), texecom-alarm-app/tests/test_arm_commands.py (modify), texecom-alarm-app/tests/test_e2e_fake_panel.py (modify).
1. Reproduce NAK handling in FakePanel (reject cmd=6) and capture whether the app ignores NAK today.
2. On panel NAK/NACK for arm, ensure alarm MQTT state is republished as the last known disarmed/armed value so HA does not leave a stuck mode selection; log a clear failure reason.
3. Investigate live Home arm with slot-oriented mapping from TASK-11 (mode byte for Home vs open zones) — document finding; fix mapping/command path if the app is at fault.
4. Keep successful arm path reliant on AREA/snapshot updates (no optimistic armed_* without panel evidence).
Test strategy: how we'll know = unit/E2E FakePanel NAK → retained disarmed republish; pytest test_arm_commands + E2E; manual acceptance test for live Home arm on a daytime clean panel (not CI).
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: On arm NAK, republish live last-known alarm MQTT state (getter); ARM_HOME ACK path unchanged.
Changed files: texecom-alarm-app/src/texecom_alarm/arm_commands.py, texecom-alarm-app/src/texecom_alarm/app.py, texecom-alarm-app/tests/fake_panel.py, texecom-alarm-app/tests/test_arm_commands.py, texecom-alarm-app/tests/test_e2e_fake_panel.py, texecom-alarm-app/tests/test_app_mqtt.py, texecom-alarm-app/tests/test_reconnect.py
Verification: pytest → 173 passed; ruff clean. Bugbot stale-snapshot finding fixed via get_current_alarm_state callable.
Notes/assumptions: AC#3 root cause = panel reject (not app framing/mapping). Feedback gap fixed. Mid-flight state race on NAK republish fixed after Bugbot.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->
