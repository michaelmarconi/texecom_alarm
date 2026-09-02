---
id: TASK-64
title: Retry a chatty Arm/Disarm timeout as a new request
status: awaiting-review
assignee: []
created_date: '2026-09-02 10:51'
updated_date: '2026-09-02 11:54'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-022'
  - 'adr:ADR-008'
  - 'ac:AC4'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-022-use-one-busy-versus-dead-session-model-including-late-command-replies-for-panel-connection-health.md
  - docs/specs/spec-panel-session-heal.md
priority: high
ordinal: 58000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** When Disarm (or Arm) gets no reply in time, the add-on retries the same request. Live: that second try still got no reply while the panel was sending ordinary updates; the next tap, as a fresh request on the same connection, was accepted almost immediately.
**Goal:** If Arm or Disarm times out while ordinary updates are still arriving, retry the same tap as a new request — not the timed-out one.
**Why now:** Corrective for TASK-7 — ADR-022. Connection behaviour is the following task.

Corrective for TASK-7 (left done; this task is the rework).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 If Arm or Disarm times out while well-formed event frames arrived during that wait, the next attempt uses a new sequence number
- [ ] #2 The existing command retry budget is unchanged (not an unbounded wait)
- [ ] #3 A completely silent timeout still fails without treating leftover events from a previous command as busy
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom_alarm/src/texecom_alarm/protocol/client.py (modify), texecom_alarm/tests/test_protocol_client.py (modify), texecom_alarm/tests/test_arm_commands.py (modify), texecom_alarm/tests/fake_panel.py (modify). 1. During the command wait, record whether at least one well-formed unsolicited event frame arrived. 2. On timeout: if that wait was silent, raise TimeoutError as today (same sequence is not retried as a 'busy' retry). 3. On timeout with events: do not reuse the timed-out sequence; allocate a new sequence and resend within the existing retry budget (retries=1 stays). 4. Keep NAK immediate; do not skip unexpected bytes. Test strategy: how we'll know = unit against the protocol client (stand-in: FakePanel / recorded frames); command: cd texecom_alarm && python -m pytest tests/test_protocol_client.py tests/test_arm_commands.py -q. Assert a Disarm (or Arm) whose first wait only sees event frames then retries with a different sequence; a silent timeout does not invent a new-sequence busy retry.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Chatty Arm/Disarm timeouts retry as a new request (new sequence) within retries=1; silent timeouts keep same-sequence retry and leftover events from an earlier command do not count as busy.
Changed files: texecom_alarm/src/texecom_alarm/protocol/client.py, texecom_alarm/tests/test_protocol_client.py, texecom_alarm/tests/fake_panel.py, texecom_alarm/CHANGELOG.md
Verification: cd texecom_alarm && python -m pytest tests/test_protocol_client.py tests/test_arm_commands.py -q → 86 passed; python -m pytest --cov=texecom_alarm --cov-fail-under=90 -q → 421 passed, 92.69% coverage; ruff check . && ruff format --check . → clean. Disarm/Arm whose first wait only sees event frames retry with a different sequence; a silent timeout (including leftover queued events) does not invent a new-sequence busy retry; budget stays two attempts.
Notes/assumptions: New-sequence busy retry applies only to SETAREAARM/SETAREADISARM (task/ADR scope); other commands keep same-sequence timeout retry. Alarm Panel Connection, hello patience, reconnect, and byte-skip were not changed. test_arm_commands.py unchanged because retries live in PanelClient.

## Build phase
phase: merging
<!-- SECTION:FINAL_SUMMARY:END -->
