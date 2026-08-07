---
id: TASK-19
title: Instrument DEBUG handling and TRACE panel traffic
status: in-progress
assignee: []
created_date: '2026-08-07 17:22'
updated_date: '2026-08-07 17:34'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-002'
  - 'ac:AC4'
  - 'ac:AC5'
  - 'ac:AC6'
dependencies:
  - TASK-18
documentation:
  - docs/specs/spec-diagnostics-logging.md
priority: high
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Even with a log-level knob, DEBUG/TRACE are empty of the zone/command and wire detail operators need to hunt stuck sensors or silent sessions.
**Goal:** At DEBUG, logs show app-meaningful zone/area/command outcomes; at TRACE, panel session transmit/receive appears; modem/non-frame piping stays out of WARNING–DEBUG and only compact skip notices at TRACE.
**Why now:** Depends on selectable log_level (TASK-18); completes the Accepted diagnostics-logging behaviour for automated ACs.

Open calls accepted at plan time: live TRACE hunt (AC7) is checkpoint manual DoD, not CI.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 At DEBUG, a FakePanel zone change or arm/disarm produces handling/outcome log lines without requiring raw frame dumps
- [ ] #2 At TRACE, FakePanel unsolicited or command traffic produces panel tx/rx (or equivalent session) log lines
- [ ] #3 Non-frame/modem-style skips do not dump raw piping at INFO/DEBUG; TRACE shows at most a compact skip notice
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom-alarm-app/src/texecom_alarm/protocol/client.py (modify), texecom-alarm-app/src/texecom_alarm/zone_state.py (modify), texecom-alarm-app/src/texecom_alarm/area_state.py (modify), texecom-alarm-app/src/texecom_alarm/arm_commands.py (modify), texecom-alarm-app/src/texecom_alarm/reconnect.py (modify), texecom-alarm-app/src/texecom_alarm/app.py (modify), texecom-alarm-app/tests/test_diagnostics_logging.py (create), texecom-alarm-app/tests/fake_panel.py (modify if needed). 1. DEBUG: ensure zone/area handle→MQTT and arm/disarm outcomes log at DEBUG (AC4). 2. TRACE: log panel tx/rx (command and unsolicited frames) at TRACE (AC5). 3. Resync path: no raw modem dumps at WARNING–DEBUG; TRACE emits compact skipped-N-bytes style notice only (AC6). 4. Integration tests with FakePanel + captured log handler asserting DEBUG vs TRACE content and modem-skip behaviour. Test strategy: how we'll know = integration test (stand-in: FakePanel + log capture); pytest texecom-alarm-app/tests/test_diagnostics_logging.py.
<!-- SECTION:PLAN:END -->
