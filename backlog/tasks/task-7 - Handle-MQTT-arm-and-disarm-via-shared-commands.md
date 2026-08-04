---
id: TASK-7
title: Handle MQTT arm and disarm via shared commands
status: in-progress
assignee: []
created_date: '2026-08-04 12:52'
updated_date: '2026-08-04 16:48'
labels:
  - 'container:texecom-alarm-app'
  - 'size:L'
  - 'risk:medium'
  - 'parallel:needs-coordination'
  - 'mode:tdd'
  - 'adr:ADR-005'
  - 'adr:ADR-003'
  - 'adr:ADR-004'
  - 'ac:AC-1'
  - 'ac:AC-2'
dependencies:
  - TASK-6
documentation:
  - >-
    docs/adrs/adr-005-use-confirmed-shared-arm-disarm-commands-with-configurable-part-arm-mapping.md
  - >-
    docs/adrs/adr-003-use-mqtt-discovery-not-native-integration-for-entity-surfacing.md
  - docs/specs/spec-alarm-control.md
  - docs/protocol-reference.md
  - docs/definition-of-done.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Config already carries Away/Night/Home Part-Arm mode bytes, and the panel commands are confirmed, but nothing yet listens on the alarm command topic or sends arm/disarm to the panel — so Home Assistant cannot control the alarm through this app.
**Goal:** Home Assistant arm away/night/home and disarm on the MQTT command topic reliably drive the confirmed shared panel commands, using the install-time mode-byte mapping (including Home).
**Why now:** Next in the alarm-control slice after TASK-6 defines the entity and `{prefix}/alarm/command` topic — blocked on TASK-6 until that ships.

Note: Depends on TASK-6 (ready, not built): command topic, discovery, and live AREA state updates after a successful arm are those surfaces — this task only subscribes and sends panel commands; it does not invent optimistic MQTT state. File overlap with TASK-6 (`app.py`, `client.py`, `frame.py`, `fake_panel.py`, E2E) → needs-coordination; build or merge TASK-6 before dispatching this task. CI proves FakePanel ACK + exact command bytes (and config remapping); live Away/Night/Home/Disarm was already confirmed in SPIKE-005, not re-run here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 MQTT payloads ARM_AWAY, ARM_NIGHT, and ARM_HOME on {prefix}/alarm/command cause FakePanel to receive cmd=6 with body [settings.part_arm_*, 0x01] for the matching Settings field.
- [ ] #2 MQTT payload DISARM causes FakePanel to receive cmd=8 with body [0x01] (including when used as cancel-during-exit — same bytes).
- [ ] #3 Changing Settings.part_arm_away/night/home changes the mode byte sent without a code change; unknown command payloads are ignored (no panel command).
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

### Implementation steps

1. Add `CMD_SET_AREA_ARM = 6` and `CMD_SET_AREA_DISARM = 8` in `texecom-alarm-app/src/texecom_alarm/protocol/frame.py`. Extend `PanelClient` in `texecom-alarm-app/src/texecom_alarm/protocol/client.py` with `set_area_arm(mode: int)` → body `bytes([mode & 0xFF, 0x01])` and `set_area_disarm()` → body `bytes([0x01])` (SPIKE-005 / `docs/protocol-reference.md`).
2. Create `texecom-alarm-app/src/texecom_alarm/arm_commands.py`:
   - Map HA MQTT default payloads `ARM_AWAY` / `ARM_NIGHT` / `ARM_HOME` / `DISARM` → panel calls using `Settings.part_arm_away` / `part_arm_night` / `part_arm_home` (never hardcode 0/1/2 except as those Settings defaults already shipped in TASK-1).
   - Ignore unknown payloads (log + no panel send).
   - Do not publish alarm state from the command path — rely on TASK-6 AREA/snapshot updates for MQTT state.
3. Extend `AiomqttPublisher` in `texecom-alarm-app/src/texecom_alarm/mqtt/publisher.py` (and `RecordingMqttPublisher` in `tests/recording_mqtt.py`) with `subscribe(topic)` plus a way to consume inbound messages (e.g. async iterate `messages` after connect) so the app can listen on `{prefix}/alarm/command` (helper from TASK-6 discovery, or the same string TASK-6 publishes as `command_topic`).
4. Wire `texecom-alarm-app/src/texecom_alarm/app.py`: after MQTT connect / alarm discovery (TASK-6), subscribe to the command topic and run an inbound handler concurrent with the panel listen loop; on each valid payload call the arm/disarm client methods.
5. Extend `texecom-alarm-app/tests/fake_panel.py` to ACK cmd 6/8 and record last arm mode / disarm calls; add unit + E2E tests covering all three arm modes, disarm, remapped Settings bytes, and ignored junk payloads.

### Files likely affected

- `texecom-alarm-app/src/texecom_alarm/protocol/frame.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/protocol/client.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/mqtt/publisher.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/arm_commands.py` (create)
- `texecom-alarm-app/src/texecom_alarm/app.py` (modify)
- `texecom-alarm-app/tests/fake_panel.py` (modify)
- `texecom-alarm-app/tests/recording_mqtt.py` (modify)
- `texecom-alarm-app/tests/test_arm_commands.py` (create)
- `texecom-alarm-app/tests/test_protocol_client.py` (modify)
- `texecom-alarm-app/tests/test_e2e_fake_panel.py` (modify)

### Test strategy

`cd texecom-alarm-app && python -m pytest tests/test_arm_commands.py tests/test_protocol_client.py tests/test_e2e_fake_panel.py -q` — MQTT ARM_* / DISARM → FakePanel cmd 6/8 bodies; remapped `part_arm_*` changes mode byte; unknown payload sends nothing.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: provisioned
<!-- SECTION:FINAL_SUMMARY:END -->
