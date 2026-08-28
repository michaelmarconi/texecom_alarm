---
id: TASK-53
title: 'Bounded, forcibly-abandoned socket release before reconnecting'
status: in-progress
assignee: []
created_date: '2026-08-28 16:14'
updated_date: '2026-08-28 16:19'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-020'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-020-use-scheduled-check-ins-and-a-patience-window-for-panel-session-recovery.md
priority: medium
ordinal: 47000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Closing the panel session today waits on the transport to close with no time limit — live testing showed a client that leaves its own socket open (because that wait never completes) can never reconnect, since the panel's single connection slot stays occupied by the client's own abandoned session.
**Goal:** Releasing a session before reconnecting always finishes within a bounded time, forcibly abandoning the socket at the OS level if it will not close cleanly, so the app can never lock itself out of the panel's one connection slot while waiting on a connection it has already given up on.
**Why now:** Unblocked and next — independent of the check-in/patience wave; this closes the other live-tested failure mode from the same investigation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 close() always returns within a short bounded time even when the underlying transport's wait_closed() never completes
- [ ] #2 A socket that would not close cleanly is forcibly abandoned at the OS level rather than left open
- [ ] #3 Reconnect always waits for close() (bounded or not) to finish before attempting a new connection
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom_alarm/src/texecom_alarm/protocol/client.py (modify — wrap `close()`'s `await writer.wait_closed()` in a bounded wait, e.g. `asyncio.wait_for` with a short fixed timeout; on timeout, forcibly abort the transport rather than leaving it dangling), texecom_alarm/src/texecom_alarm/reconnect.py (modify — confirm/ensure the bounded close is always awaited before the next connect attempt), texecom_alarm/tests/test_protocol_client.py (modify — a fake transport whose close() never completes, asserting close() still returns within the bound and the transport was aborted). Test strategy: how we'll know = unit test against a stand-in transport that never completes wait_closed(); `pytest tests/test_protocol_client.py -k close -q`. Novel decisions: the bound's default value (short — seconds, not the reconnect interval itself) and the abandon mechanism (transport.abort() vs a lower-level socket close).
<!-- SECTION:PLAN:END -->
