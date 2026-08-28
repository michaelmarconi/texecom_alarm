---
id: TASK-50
title: >-
  Send check-ins on a fixed elapsed-time schedule, never starved by inbound
  traffic
status: awaiting-review
assignee: []
created_date: '2026-08-28 16:13'
updated_date: '2026-08-28 19:33'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-020'
  - 'adr:ADR-017'
dependencies:
  - TASK-49
documentation:
  - >-
    docs/adrs/adr-020-use-scheduled-check-ins-and-a-patience-window-for-panel-session-recovery.md
priority: medium
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Today the app only checks in with the panel when the connection has been idle for a while — a panel sending lots of unprompted activity can go a long time without ever being checked in on, because every incoming message resets the idle clock.
**Goal:** Check-ins fire on a fixed schedule measured in elapsed time, regardless of how much other traffic the panel is sending, so a busy connection can never silently skip its check-in.
**Why now:** Unblocked by the new settings; this is the mechanism the patience window (next task) depends on.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A check-in fires at the configured interval even under continuous simulated inbound panel traffic
- [ ] #2 The check-in schedule is unaffected by changing the reconciliation poll interval (ADR-017), and vice versa
- [ ] #3 No regression: a genuinely idle connection still gets a check-in at least as promptly as today
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom_alarm/src/texecom_alarm/app.py (modify — in `_listen_panel_messages`, add a check-in-due clock independent of `idle_timeout`/`recv_message`'s wait, mirroring the existing `trust.poll_due()`/`seconds_until_poll()` pattern so the recv wait is capped by whichever of {idle_timeout, trust poll, check-in} is soonest), texecom_alarm/tests/test_app_listen.py or equivalent (modify/create — simulate sustained inbound traffic and assert a check-in still fires on schedule). Test strategy: how we'll know = unit/integration against FakePanel; a test that feeds continuous unsolicited frames for longer than several check-in intervals and asserts keepalive was still called on schedule (not starved). `pytest tests/ -k checkin -q` (or the actual file name chosen). Novel decisions: how the check-in clock composes with the existing idle-timeout and trust-poll wait-capping in the same loop; whether the idle-timeout keepalive path is replaced entirely by this scheduled one or kept as a secondary trigger (recommend: replaced, since the schedule is a superset of what idle-timeout achieves).
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Check-ins now fire on a fixed elapsed-time schedule (checkin_interval_seconds), tracked independently of both inbound panel traffic and the reconciliation poll interval, so a busy connection can no longer starve or delay a check-in.
Changed files: texecom_alarm/src/texecom_alarm/app.py, texecom_alarm/tests/test_app_mqtt.py, texecom_alarm/tests/test_panel_trust.py, texecom_alarm/tests/test_session_heal.py, texecom_alarm/tests/test_e2e_fake_panel.py
Verification: pytest -q -> 360 passed; ruff check/format clean; coverage 92.54% (>=90% gate).
Notes/assumptions: Kept the idle_timeout parameter name in _listen_panel_messages/run() for backward compatibility with the existing test seam, even though it now means check-in interval rather than idle timeout - documented inline in app.py. The check-in-due check now runs both on recv_message timeout and after every received frame (previously only on timeout) - this is the mechanism that satisfies AC1. Several pre-existing tests implicitly relied on the old behavior where a fast reconciliation-poll interval caused near-immediate keepalives; these now pass an explicit fast idle_timeout to keep their timing intent, decoupled from production default of 15s - intended consequence of AC2.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->
