---
id: TASK-8
title: Persist and publish last-trigger snapshot
status: ready
assignee: []
created_date: '2026-08-04 12:52'
updated_date: '2026-08-04 17:02'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-004'
  - 'adr:ADR-003'
  - 'ac:AC-6'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-004-use-app-liveness-unavailability-and-trigger-snapshots-for-panel-link-outages.md
  - >-
    docs/adrs/adr-003-use-mqtt-discovery-not-native-integration-for-entity-surfacing.md
  - docs/specs/spec-alarm-control.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** The alarm entity already reports `triggered` from live area updates, but when the panel force-drops the link at trigger time the household has no retained "what set it off" context on that entity.
**Goal:** On enter-alarm, publish a last-trigger snapshot (initiating zone + timestamp) as retained attributes on the alarm entity, fed by a short rolling buffer of recent zone and log activity.
**Why now:** Unblocked and next — zone and alarm live paths are done; this is the ADR-004 snapshot half before reconnect work.

Note: Initiating-zone selection is a heuristic (most recent Active zone in the buffer) grounded in one SPIKE-002 trigger capture; CI covers FakePanel-injected sequences only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Injected ZONE Active then AREA in-alarm (state 5) publishes retained {prefix}/alarm/attributes with the initiating zone number and a timestamp
- [ ] #2 Alarm discovery includes json_attributes_topic pointing at that attributes topic
- [ ] #3 A later disarm updates alarm state but does not clear the retained last-trigger attributes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Create `texecom-alarm-app/src/texecom_alarm/trigger_snapshot.py` with:
   - `TriggerActivityBuffer` backed by `collections.deque(maxlen=32)` recording ZONE events (zone number, status byte, wall time) and LOG events (type, group, wall time).
   - `record_zone(zone_number, status)` / `record_log(event_type, group)` helpers.
   - `initiating_zone()` → most recent buffered ZONE whose low 2 bits ≠ Secure (status & 0x03 != 0), else None.
   - `maybe_publish_trigger_snapshot(mqtt, *, previous_payload, new_payload, topic_prefix, buffer, clock=...)` — on edge into HA payload `"triggered"` only, publish retained JSON to `{prefix}/alarm/attributes` with keys `last_trigger_zone` (int or null) and `last_trigger_time` (UTC ISO-8601). No invent on cold-start already-in-alarm. Do not clear attributes on disarm; next trigger overwrites.
   - `alarm_attributes_topic(topic_prefix)` helper (or live next to discovery helpers).
2. Modify `texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py`:
   - Add `alarm_attributes_topic(topic_prefix)` → `{prefix}/alarm/attributes`.
   - Include `json_attributes_topic` in `alarm_discovery_payload` pointing at that topic (HA MQTT alarm_control_panel).
3. Modify `texecom-alarm-app/src/texecom_alarm/area_state.py` so `handle_area_message` returns the published HA payload string (or None if ignored) for edge detection in the listen loop.
4. Wire `texecom-alarm-app/src/texecom_alarm/app.py` `_listen_panel_messages`:
   - Own a `TriggerActivityBuffer` and `last_alarm_payload` tracker.
   - On MSG_ZONE: record into buffer then existing `handle_zone_message`.
   - On MSG_LOG (body[0]==5): record type/group when body length allows; still no MQTT state publish.
   - On MSG_AREA: call `handle_area_message`, then `maybe_publish_trigger_snapshot` with previous/new payloads; update tracker.
5. Tests:
   - Unit: buffer initiating-zone heuristic; edge publish; no publish when already triggered; null zone when buffer empty; attributes retained across a later disarm publish of alarm state.
   - Discovery: payload includes `json_attributes_topic`.
   - E2E FakePanel: inject ZONE Active then AREA state 5 → retained attributes with that zone + timestamp; disarm does not clear attributes.

Files likely affected:
- `texecom-alarm-app/src/texecom_alarm/trigger_snapshot.py` (create)
- `texecom-alarm-app/src/texecom_alarm/mqtt/discovery.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/app.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/area_state.py` (modify)
- `texecom-alarm-app/tests/test_trigger_snapshot.py` (create)
- `texecom-alarm-app/tests/test_mqtt_discovery.py` (modify)
- `texecom-alarm-app/tests/test_area_state.py` (modify)
- `texecom-alarm-app/tests/test_e2e_fake_panel.py` (modify)

Test strategy: `cd texecom-alarm-app && python -m pytest tests/test_trigger_snapshot.py tests/test_mqtt_discovery.py tests/test_area_state.py tests/test_e2e_fake_panel.py -q`
<!-- SECTION:PLAN:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 docs/definition-of-done.md
<!-- DOD:END -->
