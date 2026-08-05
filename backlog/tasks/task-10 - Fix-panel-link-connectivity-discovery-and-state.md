---
id: TASK-10
title: Fix panel-link connectivity discovery and state
status: awaiting-review
assignee: []
created_date: '2026-08-05 11:53'
updated_date: '2026-08-05 12:48'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-004'
  - 'adr:ADR-002'
  - 'adr:ADR-003'
  - 'ac:AC-3'
  - 'ac:AC-6'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-004-use-app-liveness-unavailability-and-trigger-snapshots-for-panel-link-outages.md
  - docs/acceptance.md
  - docs/definition-of-done.md
priority: high
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** The app was meant to publish a dedicated panel-link connectivity sensor so the household can tell live data from stale data during reconnects, but live accept found no discovery or retained state for it on the broker — the sensor never appeared in Home Assistant.
**Goal:** Panel-link discovery and live/degraded state are retained on MQTT and visible in HA whenever the app is running.
**Why now:** Corrective follow-on to the reconnect work (TASK-9); accept blocked further trust in outage behaviour until this signal exists.

Corrective for TASK-9 — architecture and ADR-004 already require this sensor.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Retained MQTT discovery for binary_sensor object_id texecom_alarm_panel_link is published on successful startup
- [ ] #2 Panel-link state topic publishes retained ON after link-up and OFF while reconnecting, without changing zone/alarm availability topics
- [ ] #3 E2E FakePanel suite asserts connectivity discovery + state are present on the recording publisher
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py (modify), texecom-alarm-app/src/texecom_alarm/mqtt/publisher.py (modify), texecom-alarm-app/src/texecom_alarm/app.py (modify), texecom-alarm-app/src/texecom_alarm/reconnect.py (modify), texecom-alarm-app/tests/test_mqtt_discovery.py (modify), texecom-alarm-app/tests/test_reconnect.py (modify), texecom-alarm-app/tests/test_e2e_fake_panel.py (modify), texecom-alarm-app/tests/recording_mqtt.py (modify).
1. Trace why connectivity discovery/state from TASK-9 is not retained on a real broker (publish order, retain flags, topic prefix, discovery not called on startup path, or publisher drop).
2. Ensure startup publishes retained discovery for texecom_alarm_panel_link and initial ON state after a successful panel link; reconnect path continues OFF→ON as already designed.
3. Confirm zone/alarm availability still uses only app LWT (never panel-link).
Test strategy: how we'll know = unit + E2E (stand-in: FakePanel + RecordingMqttPublisher); pytest tests that assert retained discovery config + panel_link state topics appear; manual acceptance re-check on live broker after merge.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Locked retained panel-link discovery/state in E2E (source already published correctly; live accept gap was a stale pre-TASK-9 add-on image).
Changed files: texecom-alarm-app/tests/test_e2e_fake_panel.py, texecom-alarm-app/tests/test_app_mqtt.py, texecom-alarm-app/tests/test_reconnect.py
Verification: how we'll know = unit + E2E (FakePanel + RecordingMqttPublisher + Mosquitto late-subscriber retain); `cd texecom-alarm-app && .venv/bin/pytest -q --cov=texecom_alarm --cov-fail-under=90` → 160 passed, coverage 93%; `ruff check` + `ruff format --check` clean
Notes/assumptions: Production path in `app.py` / `discovery.py` / `reconnect.py` already publishes retained `texecom_alarm_panel_link` discovery and `texecom/panel_link/state` ON/OFF without touching zone/alarm availability. Running container `app_local_texecom_alarm` still lacks `reconnect.py`/`trigger_snapshot.py` and the publish calls — rebuild/restart the local add-on after merge for HA/broker to see the sensor. `test_reconnect.py` change is ruff format only.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->
