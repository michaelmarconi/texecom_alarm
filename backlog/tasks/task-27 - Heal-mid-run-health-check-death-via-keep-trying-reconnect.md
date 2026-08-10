---
id: TASK-27
title: Heal mid-run health-check death via keep-trying reconnect
status: in-progress
assignee: []
created_date: '2026-08-09 23:50'
updated_date: '2026-08-10 00:32'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-011'
  - 'adr:ADR-002'
  - 'adr:ADR-004'
  - 'adr:ADR-006'
  - 'adr:ADR-009'
  - 'ac:AC1'
  - 'ac:AC3'
  - 'ac:AC4'
dependencies:
  - TASK-26
documentation:
  - docs/specs/spec-panel-session-heal.md
  - >-
    docs/adrs/adr-011-use-automatic-session-recovery-for-mid-run-panel-path-failures.md
  - docs/architecture.md
priority: medium
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Once monitoring is live, if the usual health check goes unanswered the app can mark freshness off and then stop the listen cycle — so the process stays up but monitoring never comes back until someone restarts the add-on.
**Goal:** An unanswered mid-run health check enters the same keep-trying reconnect path as a clean panel drop: Alarm Panel Connection stays off while recovering, then returns live with zone and alarm state re-synced from the panel, without a manual restart and without blanking zone/alarm entities.
**Why now:** Detection already ships; architecture ADR-011 and session-heal AC1 require heal on health-check death next.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 FakePanel unanswered mid-run health check keeps the process running, Connection OFF while recovering, then ON with zone/alarm re-synced without add-on restart
- [ ] #2 Zone and alarm entities stay available with last-known state during recovery (not unavailable solely for panel recovery)
- [ ] #3 While recovery is still failing, Connection stays OFF and recovery attempts/failures appear at normal log levels (not TRACE-only)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

### Files likely affected

- `texecom-alarm-app/src/texecom_alarm/app.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/protocol/client.py` (modify — if keepalive timeout must surface as reconnectable)
- `texecom-alarm-app/src/texecom_alarm/reconnect.py` (modify)
- `texecom-alarm-app/tests/fake_panel.py` (modify)
- `texecom-alarm-app/tests/test_reconnect.py` (modify or extend)
- `texecom-alarm-app/tests/test_session_heal.py` (create)
- `texecom-alarm-app/tests/test_e2e_fake_panel.py` (modify)

### Implementation steps

1. Today keepalive failure in `_listen_panel_messages` re-raises into `_listen_with_reconnect`'s broad `except Exception`, which publishes Connection OFF and **aborts** the listen cycle. Change that path so an unanswered mid-run health check (keepalive timeout / equivalent dead health-check) enters the same keep-trying reconnect path used for `ForcedDisconnect` — do not exit the listen loop permanently.
2. While recovering: publish Alarm Panel Connection OFF; never mark zone/alarm unavailable solely for recovery (ADR-004). On success: re-LOGIN + ADR-006 zone snapshot + ADR-009 area snapshot + SETEVENTMESSAGES, then Connection ON.
3. Reuse existing asymmetric reconnect budgets/settings (normal vs trigger profiles); do not hardcode new final timings — ADR-011 does not newly finalise them.
4. Everyday logs (not TRACE-only) must show recovery attempts/failures while Connection stays OFF until truly live (AC4).
5. Extend FakePanel for mid-session health-check death then accept-again; add focused heal tests plus e2e coverage.
6. Do **not** auto-retry a failed arm/disarm as part of heal.

### Test strategy

How we'll know = end-to-end against FakePanel stand-in + recording MQTT (session-heal AC1/AC3/AC4). Command: `cd texecom-alarm-app && python -m pytest tests/test_session_heal.py tests/test_reconnect.py tests/test_e2e_fake_panel.py -q`. Live ComIP contention remains `/accept`.
<!-- SECTION:PLAN:END -->
