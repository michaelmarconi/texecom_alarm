---
id: TASK-35
title: Republish current alarm state on ready-to-arm refuse
status: in-progress
assignee: []
created_date: '2026-08-24 13:32'
updated_date: '2026-08-24 14:01'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-015'
  - 'adr:ADR-003'
  - 'ac:AC2'
  - 'ac:AC3'
dependencies: []
documentation:
  - docs/specs/spec-ready-to-arm.md
  - docs/architecture.md
priority: medium
ordinal: 29000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** When an arm is refused because a ready-to-arm switch is off, the panel is not armed and the alarm stays in the same state, but Home Assistant's alarm card can keep highlighting the tapped mode until it sees a new state message.
**Goal:** A refused arm immediately re-sends the current alarm state so the card can snap back, without changing that state or sending the arm to the panel.
**Why now:** Corrects TASK-31 against the amended ready-to-arm spec: unchanged state must still be published again.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Matching switch off: FakePanel receives no arm command; MQTT alarm state payload equals the pre-command value; a new publish of that payload is observed after the refuse
- [ ] #2 The same re-publish happens when the arm arrives on Home Assistant's alarm command topic
- [ ] #3 Disarm is still not gated; refuse while already armed re-publishes that current armed state and does not disarm
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom_alarm/src/texecom_alarm/arm_commands.py (modify), texecom_alarm/tests/test_arm_commands.py (modify), texecom_alarm/tests/test_app_mqtt.py (modify), texecom_alarm/tests/test_e2e_fake_panel.py (modify). 1. On refuse (matching ready switch off), after the blocked-arm event, publish the current alarm MQTT state using the same retained publish used when the panel NAKs an arm (current live state; same payload is fine). 2. Do not send an arm to the panel. 3. Do not change the payload from the pre-command value. 4. Same behaviour when the request arrived on Home Assistant's alarm command topic. Test strategy: how we'll know = unit + FakePanel integration; `cd texecom_alarm && python -m pytest tests/test_arm_commands.py tests/test_app_mqtt.py tests/test_e2e_fake_panel.py -q` — off switch: no arm command; payload equals pre-command value; a new publish of that payload after refuse, including the Home Assistant command path.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->
