---
id: TASK-51
title: >-
  Declare the session dead only after check-in failure persists past the
  patience window
status: ready
assignee: []
created_date: '2026-08-28 16:14'
labels:
  - 'container:texecom-alarm-app'
  - 'size:L'
  - 'risk:high'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-020'
  - 'adr:ADR-011'
  - 'adr:ADR-016'
dependencies:
  - TASK-50
documentation:
  - >-
    docs/adrs/adr-020-use-scheduled-check-ins-and-a-patience-window-for-panel-session-recovery.md
priority: medium
ordinal: 45000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Today a single refused or unanswered check-in is treated as proof the session is dead, and the app reconnects immediately — but live capture showed the panel sometimes refuses a check-in during a busy moment and recovers on its own shortly after, so this overreacts on a connection that was never actually dead. This corrects TASK-27, TASK-45, and TASK-47, which all shipped that immediate-death behaviour.
**Goal:** A single failed check-in no longer ends the session. Only continuous failure for longer than the configured patience period declares the session dead, and the household never sees a connectivity dropout for a failure that clears inside that window. An outright disconnect, an end-of-session signal, or non-conforming data still ends the session immediately — patience applies only to a refused or unanswered check-in.
**Why now:** Directly unblocked by scheduled check-ins; this is the behavioural heart of ADR-020 and the reason TASK-27/45/47 need correcting.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A refused or unanswered check-in that clears within the patience period never shows as a connection drop
- [ ] #2 Continuous check-in failure past the patience period declares the session dead, reconnects, and re-reads panel state — while an outright disconnect, end-of-session signal, or bad data still ends the session immediately with no patience delay
- [ ] #3 The command-rejection watchdog's own fail window (ADR-011) is demonstrated independent of the check-in patience window — refusing every command while answering check-ins still escalates on its own timer
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom_alarm/src/texecom_alarm/app.py (modify — replace the immediate ForcedDisconnect on keepalive TimeoutError/ProtocolError with a consecutive-failure tracker measured against checkin_patience_seconds; only raise once the patience window is exceeded), texecom_alarm/src/texecom_alarm/panel_trust.py (modify — add a checkin-failure tracker analogous to the existing command-failure degrade tracking, kept as a fully separate timer per ADR-020's stop condition; the connection signal must stay ON through the patience window), texecom_alarm/src/texecom_alarm/protocol/client.py (modify — decouple login's retry budget from keepalive's same-call retry count: patience now covers cross-call retries, so keepalive() no longer needs its own retry loop, but login() must keep its existing retry budget under a name of its own rather than losing it when keepalive's retries shrink), tests/test_app_listen.py, tests/test_panel_trust.py, tests/test_protocol_client.py (modify), FakePanel test double (modify — add a way to simulate N consecutive check-in refusals then a clean answer, and a separate outright-disconnect case that must NOT wait for patience). Test strategy: how we'll know = unit/integration against FakePanel; scenarios: (1) a refusal inside the patience window changes neither session nor connection signal, (2) continuous refusal past the window declares dead → reconnect → state re-read, (3) an outright disconnect/end-of-session/bad data ends the session immediately regardless of patience, (4) the command-rejection watchdog (ADR-011, panel_trust.record_command_failure) still degrades immediately and escalates on its own unchanged timer, proven independent of this new timer. `pytest tests/ -k checkin_patience -q` (or equivalent).
<!-- SECTION:PLAN:END -->
