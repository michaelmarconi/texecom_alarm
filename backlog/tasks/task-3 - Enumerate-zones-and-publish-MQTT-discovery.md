---
id: TASK-3
title: Enumerate zones and publish MQTT discovery
status: ready
assignee: []
created_date: '2026-08-04 12:51'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-001'
  - 'adr:ADR-003'
  - 'adr:ADR-004'
  - 'ac:AC-1'
dependencies:
  - TASK-1
  - TASK-2
documentation:
  - docs/specs/spec-zone-monitoring.md
  - docs/adrs/adr-001-use-dynamic-panel-enumeration-for-zone-discovery.md
  - >-
    docs/adrs/adr-003-use-mqtt-discovery-not-native-integration-for-entity-surfacing.md
  - >-
    docs/adrs/adr-004-use-app-liveness-unavailability-and-trigger-snapshots-for-panel-link-outages.md
priority: medium
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Even with a working panel session, Home Assistant still has no entities from this app — zones are not enumerated or published.
**Goal:** After login, the app asks the panel for its zone list, drops unused slots, and publishes MQTT discovery for in-use zones with availability governed by app-process Last-Will; a thin asyncio main loop is runnable under s6.
**Why now:** Unblocked once config and protocol client exist — first user-visible HA outcome for this slice.

Entity IDs provisionally match today's texecom_alarm_* naming pending household RISK-005 confirm. CI never uses the household broker or live panel.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Unused panel zone slots produce no discovery configs; in-use zones each get a binary_sensor discovery payload
- [ ] #2 Unit tests assert discovery topics/payloads via a recording MQTT stub without a broker
- [ ] #3 E2E against FakePanel and an in-process lightweight broker shows discovery retained and availability via Last-Will when the app process stops
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom-alarm-app/src/texecom_alarm/zones.py (create), texecom-alarm-app/src/texecom_alarm/mqtt/__init__.py (create), texecom-alarm-app/src/texecom_alarm/mqtt/publisher.py (create), texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py (create), texecom-alarm-app/src/texecom_alarm/app.py (create), texecom-alarm-app/src/texecom_alarm/__main__.py (create), rootfs/usr/bin/texecom_alarm (modify), texecom-alarm-app/pyproject.toml (modify — aiomqtt runtime; amqtt + pytest-asyncio in dev), texecom-alarm-app/tests/test_zones.py (create), texecom-alarm-app/tests/test_mqtt_discovery.py (create), texecom-alarm-app/tests/test_e2e_fake_panel.py (modify), texecom-alarm-app/tests/recording_mqtt.py (create).
1. After LOGIN: GETPANELIDENTIFICATION for zone count; loop GETZONEDETAILS; discard zoneType=0 (ADR-001).
2. Build HA MQTT discovery payloads for binary_sensor zones; provisional object_ids/names matching texecom_alarm_* ; shared availability topic with Last-Will on app disconnect (ADR-004) — do not tie availability to panel-link health.
3. Injectable MQTT publisher: unit tests use a recording stub; E2E spins an in-process amqtt (or equivalent) broker — never the household broker.
4. Thin asyncio entrypoint (app.py / __main__) loads config, connects protocol client, enumerates, publishes discovery, then idles cleanly for s6.
Test strategy: TDD for enum skip-unused and discovery JSON shape via recording stub; E2E FakePanel + in-process broker asserts retained discovery and LWT availability semantics.
<!-- SECTION:PLAN:END -->
