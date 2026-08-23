---
id: TASK-30
title: Publish three ready-to-arm MQTT switches that start on
status: in-progress
assignee: []
created_date: '2026-08-23 18:33'
updated_date: '2026-08-23 18:55'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-015'
  - 'adr:ADR-003'
  - 'ac:AC1'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-015-use-ready-to-arm-switches-and-mqtt-blocked-arm-event-for-unready-arm-refusal.md
  - docs/specs/spec-ready-to-arm.md
priority: high
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** People can still arm from Home Assistant when the house is not ready, and the app does not yet give ordinary users knobs they can find.
**Goal:** Home Assistant has three ready-to-arm switches — Away, Home, Night — that appear when the app starts and each starts on.
**Why now:** Unblocked coverage gap from ADR-015; the refuse path cannot honour knobs that do not exist yet.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After discovery, Home Assistant (fake MQTT client) sees three ready-to-arm switches for Away, Home, and Night
- [ ] #2 Each switch starts on so a new install arms as it does today
- [ ] #3 Switch command/state round-trip is retained so a later arm command can read the current on/off
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py (modify), texecom-alarm-app/src/texecom_alarm/app.py (modify), texecom-alarm-app/tests/test_mqtt_discovery.py (modify), texecom-alarm-app/tests/test_e2e_fake_panel.py (modify), texecom-alarm-app/tests/recording_mqtt.py (modify if needed). 1. MQTT-discover three switch entities for Away, Home, Night ready-to-arm; retained state starts on. 2. Subscribe to their command topics and keep in-memory state. 3. Do not encode household rules. Test strategy: how we'll know = integration against FakePanel + fake MQTT client; `cd texecom-alarm-app && python -m pytest tests/test_mqtt_discovery.py tests/test_e2e_fake_panel.py -q` — discovery payloads exist, each switch starts on.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: claimed
<!-- SECTION:FINAL_SUMMARY:END -->
