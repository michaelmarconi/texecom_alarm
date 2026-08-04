---
id: TASK-5
title: Publish live zone state from panel push events
status: in-progress
assignee: []
created_date: '2026-08-04 12:52'
updated_date: '2026-08-04 16:00'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-006'
  - 'adr:ADR-003'
  - 'adr:ADR-004'
  - 'adr:ADR-002'
  - 'ac:AC-2'
dependencies:
  - TASK-3
documentation:
  - docs/adrs/adr-006-use-panel-zone-state-snapshot-for-startup-re-sync.md
  - docs/specs/spec-zone-monitoring.md
  - docs/definition-of-done.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Zone entities are discovered over MQTT, but the app stops after discovery and never publishes open/closed state — so Home Assistant would show wrong defaults until something changes, and live panel pushes are ignored.
**Goal:** After discovery, publish correct current zone state from a panel snapshot, then keep updating from live zone pushes within the monitoring latency budget.
**Why now:** Unblocked and next — enumeration and discovery (TASK-3) are done, and ADR-006 settled the startup snapshot command.

Note: Physical open/close flip was not run in SPIKE-006; CI proves snapshot and push against FakePanel only. Full reconnect/resume is deferred — this task ships startup plus a reusable snapshot helper.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After login + enumeration against FakePanel, GetZoneState drives retained MQTT state for every in-use zone matching the panel status bytes (Secure→"0", Active→"1"); unused slots get no state publish.
- [ ] #2 An injected ZONE push updates that zone's MQTT state topic to the matching "0"/"1" payload.
- [ ] #3 During the snapshot exchange, the client sends only GetZoneState (cmd 2) for zone status — not omit/arm/disarm command bytes 4/5/6/8/9.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

### Implementation steps

1. Add protocol constants in `texecom-alarm-app/src/texecom_alarm/protocol/frame.py`: `CMD_GET_ZONE_STATE = 2`, `CMD_SETEVENTMESSAGES = 37`, `MSG_ZONE = 1` (plus related message subtypes as needed for ignore-path clarity).
2. Extend `PanelClient` in `texecom-alarm-app/src/texecom_alarm/protocol/client.py`:
   - `get_zone_state(start, count)` — send cmd 2 with body `[startZone][zoneCount]` using 1-byte `startZone` when panel zone count ≤ 256; batch at most 168 zones per request; return exactly `count` status bytes (raise on length/NAK mismatch).
   - `set_event_messages()` — send cmd 37 with little-endian two-byte bitmask `DEBUG|ZONE|AREA|OUTPUT|USER|LOG` using flags `1 | (1<<1) | (1<<2) | (1<<3) | (1<<4) | (1<<5)` (same construction as SPIKE-002).
   - Queue interleaved `'M'` (TYPE_MESSAGE) frames during `send_command` waits instead of discarding them; expose `recv_message()` for the listen loop.
3. Create `texecom-alarm-app/src/texecom_alarm/zone_state.py` with shared bitmap decode and MQTT publish helpers:
   - Low 2 bits: Secure(0) → MQTT `"0"`, Active(1) → `"1"`, Tamper(2)/Short(3) → `"1"` (binary_sensor on).
   - After `enumerate_zones`, call GetZoneState for the panel zone count, publish **retained** state only for in-use zones to `{prefix}/zone/{n}/state` via existing `zone_state_topic` / discovery `payload_on`/`payload_off` (`"1"`/`"0"`).
   - Never send omit/arm/disarm command bytes 4/5/6/8/9 during the snapshot.
4. Wire `texecom-alarm-app/src/texecom_alarm/app.py`: after discovery, run the snapshot publish, then `SETEVENTMESSAGES`, then replace idle-only with a listen loop that on ZONE messages (`body[0]==1`, zone number + state byte) publishes the same state-topic encoding; ignore other message subtypes (no alarm handling in this task).
5. Extend `texecom-alarm-app/tests/fake_panel.py` / `FakeZone` with per-zone status bytes, GetZoneState + SETEVENTMESSAGES handlers, and a way to inject ZONE `'M'` frames.
6. Add/extend tests: unit coverage for decode + snapshot publish; protocol client GetZoneState / message queue; E2E FakePanel path asserting MQTT state after snapshot and after an injected ZONE push.

### Files likely affected

- `texecom-alarm-app/src/texecom_alarm/protocol/frame.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/protocol/client.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/zone_state.py` (create)
- `texecom-alarm-app/src/texecom_alarm/app.py` (modify)
- `texecom-alarm-app/tests/fake_panel.py` (modify)
- `texecom-alarm-app/tests/test_zone_state.py` (create)
- `texecom-alarm-app/tests/test_protocol_client.py` (modify)
- `texecom-alarm-app/tests/test_e2e_fake_panel.py` (modify)

### Test strategy

`cd texecom-alarm-app && python -m pytest tests/test_zone_state.py tests/test_protocol_client.py tests/test_e2e_fake_panel.py -q` — FakePanel GetZoneState → MQTT `"0"`/`"1"` for in-use zones only; injected ZONE push updates state; no arm/omit cmds during snapshot.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->
