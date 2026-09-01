---
id: TASK-60
title: >-
  Treat a parse miss after a successful arm or disarm as a collision, not a
  failed tap
status: done
assignee: []
created_date: '2026-08-31 21:19'
updated_date: '2026-09-01 05:51'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:low'
  - 'parallel:needs-coordination'
  - 'mode:tdd'
  - 'adr:ADR-021'
  - 'adr:ADR-004'
  - 'ac:AC1'
  - 'ac:AC4'
dependencies:
  - TASK-59
documentation:
  - >-
    docs/adrs/adr-021-use-one-busy-versus-dead-session-model-for-panel-connection-health.md
  - docs/specs/spec-panel-session-heal.md
priority: medium
ordinal: 54000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** If a later housekeeping read fails to parse after the panel already accepted an arm or disarm, the add-on records that as the tap failing and turns Alarm Panel Connection off. That is the garage-return flicker: the disarm worked; the follow-up read did not.
**Goal:** A parse miss after a successful tap is a collision: close the session, log in again, re-read zone and alarm state. Do not record it as a failed arm or disarm. Connection stays on if that first re-login succeeds. A refused or timed-out tap still turns Connection off immediately.
**Why now:** Corrective for TASK-7 — ADR-021 separates a busy-line parse miss from a tap the household already saw fail.

Corrective for TASK-7 (left done; this task is the rework). FakePanel is not proof that a real Premier Elite torn-frame stays quiet on Connection — that remains live `/accept`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 After a successful arm or disarm ACK, a housekeeping parse miss is not recorded as arm/disarm command failure
- [x] #2 Connection stays on when the first re-login after that miss succeeds; zone and alarm state are re-read from the panel
- [x] #3 A refused or timed-out arm or disarm still turns Connection off immediately and is not re-issued by heal
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

In `arm_commands.py`, a `ForcedDisconnect` (or decode miss) *after* the panel ACK must not call `record_command_failure` with disarm_disconnect/arm_disconnect. Propagate as session collision so reconnect runs: bounded release, re-login, snapshots. If reconnect attempt 1 succeeds, do not publish Connection off. NAK/timeout of the arm/disarm command itself still uses `record_command_failure` and Connection off immediately. Do not auto-retry the tap. Do not skip unexpected bytes.

### Files likely affected

- `texecom_alarm/src/texecom_alarm/arm_commands.py` (modify)
- `texecom_alarm/src/texecom_alarm/panel_trust.py` (modify if command-failure vs collision reasons split here)
- `texecom_alarm/src/texecom_alarm/reconnect.py` (modify if attempt-1 Connection-on is decided here)
- `texecom_alarm/src/texecom_alarm/app.py` (modify if listen/heal path records the reason)
- `texecom_alarm/tests/test_arm_commands.py` (modify — drop the test that ForcedDisconnect during post-ACK flags refresh must degrade Connection)
- `texecom_alarm/tests/test_e2e_fake_panel.py` (modify)
- `texecom_alarm/tests/test_panel_trust.py` (modify)

### Test strategy

How we'll know: unit + end-to-end against FakePanel. Command: `cd texecom_alarm && python -m pytest tests/test_arm_commands.py tests/test_panel_trust.py tests/test_e2e_fake_panel.py -q`. FakePanel: ACK arm/disarm then unparseable housekeeping → not command-failure; Connection stays on if re-login succeeds on attempt 1. NAK/timeout of the command still turns Connection off immediately. Never-skip-bytes and patience paths stay green. Do not claim CI proves a real torn-frame.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Post-ACK housekeeping parse miss is a collision (resync, Connection stays on if attempt 1 succeeds), not a failed arm/disarm.
Changed files: texecom_alarm/src/texecom_alarm/arm_commands.py, texecom_alarm/src/texecom_alarm/panel_trust.py, texecom_alarm/src/texecom_alarm/reconnect.py, texecom_alarm/src/texecom_alarm/app.py, texecom_alarm/src/texecom_alarm/protocol/client.py, texecom_alarm/tests/test_arm_commands.py, texecom_alarm/tests/test_panel_trust.py, texecom_alarm/tests/test_e2e_fake_panel.py, texecom_alarm/tests/fake_panel.py
Verification: How we'll know `python -m pytest tests/test_arm_commands.py tests/test_panel_trust.py tests/test_e2e_fake_panel.py -q` → 90 passed. DoD: `pytest --cov=texecom_alarm --cov-fail-under=90 -q` → 392 passed, 92% coverage; `ruff check` and `ruff format --check` clean.
Notes/assumptions: FakePanel does not prove a real Premier Elite torn-frame stays quiet on Connection. GetAreaFlags NAK/timeout after ACK still records as command failure (existing behaviour; only ForcedDisconnect/decode miss is collision). `recv_message` now raises ForcedDisconnect after a torn-down session (same as send_command) so closing from the command path wakes listen into reconnect instead of aborting the app.

## Build phase
phase: done
<!-- SECTION:FINAL_SUMMARY:END -->
