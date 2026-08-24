---
id: TASK-37
title: Bounce alarm card via Arming then current state on refuse
status: in-progress
assignee: []
created_date: '2026-08-24 16:10'
updated_date: '2026-08-24 16:21'
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
  - >-
    docs/adrs/adr-015-use-ready-to-arm-switches-and-mqtt-blocked-arm-event-for-unready-arm-refusal.md
priority: medium
ordinal: 31000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** A refused arm already leaves the panel unchanged and re-sends the same alarm state. Home Assistant ignores that duplicate, so the card can stay on the tapped mode.
**Goal:** A refused arm briefly shows Arming, then the state the panel still has, without sending an arm to the panel.
**Why now:** Corrects TASK-35: same-state republish is not enough for the card to snap back.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Matching switch off: FakePanel receives no arm; MQTT alarm state is arming then the pre-command payload
- [ ] #2 The same Arming-then-current sequence happens when the arm arrives on Home Assistant's alarm command topic
- [ ] #3 Disarm is still not gated; refuse while already armed bounces to that current armed state and does not disarm
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom_alarm/src/texecom_alarm/arm_commands.py (modify), texecom_alarm/tests/test_arm_commands.py (modify), texecom_alarm/tests/test_app_mqtt.py (modify), texecom_alarm/tests/test_e2e_fake_panel.py (modify). 1. On refuse, after the blocked-arm event, publish retained MQTT alarm state arming, then publish the pre-command current payload (same retained helper as panel NAK). 2. Do not send arm or disarm to the panel. 3. If a short pause is needed so Home Assistant applies Arming first, keep it MQTT-only: do not leave the app's live alarm state as arming, and do not let a flags/trust poll replace the bounce with a lagging disarmed except after a real disarm. 4. Refuse while already armed must bounce back to that armed payload, not disarmed. 5. Same sequence on Home Assistant's alarm command topic. Test strategy: how we'll know = unit + FakePanel integration; `cd texecom_alarm && python -m pytest tests/test_arm_commands.py tests/test_app_mqtt.py tests/test_e2e_fake_panel.py -q` — matching switch off: no panel arm; MQTT sequence is arming then the pre-command payload (including the Home Assistant command path); already-armed refuse ends on the armed payload.
<!-- SECTION:PLAN:END -->
