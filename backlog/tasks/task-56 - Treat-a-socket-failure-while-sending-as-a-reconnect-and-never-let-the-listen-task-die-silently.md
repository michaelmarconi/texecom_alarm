---
id: TASK-56
title: >-
  Treat a socket failure while sending as a reconnect, and never let the listen
  task die silently
status: done
assignee: []
created_date: '2026-08-29 11:01'
updated_date: '2026-08-29 11:26'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:high'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-004'
  - 'adr:ADR-011'
  - 'adr:ADR-019'
  - 'adr:ADR-020'
dependencies: []
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** The panel client turns a dropped socket into a clean end-of-session everywhere it *reads* (protocol/client.py:534), but not where it *writes* (protocol/client.py:403-404). If the connection dies while the add-on is sending - a scheduled check-in, an arm, a disarm - a raw connection-reset error escapes instead. Nothing converts it, the listen loop only catches the clean end-of-session, and the outer loop re-raises it. Because run() parks on an idle wait (app.py:282) and never awaits the listen task, that task dies unobserved while the process stays alive: the MQTT last-will never fires, so Home Assistant keeps showing every zone and the alarm as available with frozen values, indefinitely, and no reconnect is ever attempted. This is the same shape as the stuck process seen during the keepalive investigation, reached by a different route.

A related gap: the arm/disarm command path classifies only protocol errors, timeouts and clean end-of-session, so a raw socket error from a disarm falls through to a generic handler that logs but never records a command failure - leaving the connection signal reading healthy on a disarm that failed because the socket was dead.

**Goal:** A socket failure while sending is treated exactly like one while receiving - the session ends and the add-on reconnects. Separately, no unexpected failure in the listen task can ever again be silent: the add-on must either recover or exit so the last-will marks it unavailable, rather than sitting alive behind frozen entities.

**Why now:** Two independent reviews of the ADR-020 wave flagged this as the one item blocking an overnight live run on a real alarm panel. The trigger is narrow - the receive path normally notices the fault first, winning 8 of 8 realistic reset trials - but the failure is silent, permanent, and leaves a household believing an unmonitored alarm is being monitored.

**Constraint:** zone and alarm entities must still never be marked unavailable for a panel-link reason; only the add-on process being down may do that (ADR-004).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A network failure while sending a command to the panel ends the session and reconnects, exactly as one while receiving does
- [x] #2 An arm or disarm that fails because the socket died is recorded as a command failure and turns Alarm Panel Connection off, rather than being swallowed as an unexpected error
- [x] #3 An unexpected failure in the panel listen task can never leave the add-on alive-but-idle behind stale entities: it either recovers or the add-on exits so Home Assistant marks it unavailable
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: done
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 Zone and alarm entities are still never marked unavailable for a panel-link reason (ADR-004)
- [x] #2 Reconnection still retries indefinitely on the single configured interval (ADR-018/ADR-019)
<!-- DOD:END -->
