---
id: TASK-61
title: 'Log why a panel message could not be read, including the leading bytes'
status: awaiting-review
assignee: []
created_date: '2026-08-31 21:20'
updated_date: '2026-09-01 08:33'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:needs-coordination'
  - 'mode:tdd'
  - 'adr:ADR-021'
  - 'ac:AC4'
dependencies:
  - TASK-60
documentation:
  - >-
    docs/adrs/adr-021-use-one-busy-versus-dead-session-model-for-panel-connection-health.md
  - docs/specs/spec-panel-session-heal.md
priority: medium
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** When a panel read does not parse, the add-on closes the session but everyday logs do not show why or the arriving bytes. TRACE already dumps traffic; default Home Assistant log level is not TRACE, so a torn frame looks the same as a hang-up unless you turned TRACE on.
**Goal:** A decode miss logs the reason and the leading bytes in hex at normal log level, together in that same event, so a torn message is distinguishable from a hung-up connection without enabling TRACE.
**Why now:** Coverage gap — ADR-021 requires that log; no existing task owned it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decode miss logs reason and leading hex together at INFO or WARNING, not TRACE-only
- [ ] #2 Unexpected bytes still end the session without scanning forward for the next valid message
- [ ] #3 End-of-session +++ remains distinguishable in logs from a torn Connect frame
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

When `try_decode_frame` yields no frame and the session is ended (unexpected bytes, not `+++` which already has a specific message), log at INFO or WARNING (not TRACE): a short reason plus leading hex of the buffer (enough to tell torn vs hang-up). Keep reason and hex on the same log event. Do not skip the unexpected bytes hoping to find the next valid message.

### Files likely affected

- `texecom_alarm/src/texecom_alarm/protocol/client.py` (modify)
- `texecom_alarm/src/texecom_alarm/protocol/frame.py` (modify if the reason string is produced here)
- `texecom_alarm/tests/test_protocol_client.py` (modify)
- `texecom_alarm/tests/test_protocol_frame.py` (modify)

### Test strategy

How we'll know: unit tests capturing log records (no live panel). Command: `cd texecom_alarm && python -m pytest tests/test_protocol_client.py tests/test_protocol_frame.py -q`. Inject non-Connect bytes; assert a non-TRACE log contains a reason and leading hex; session still ForcedDisconnect without skipping bytes. FakePanel e2e already forbids skip-and-resync — keep that green at the checkpoint.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Decode misses now log reason and leading hex together at WARNING; unexpected bytes still end the session without skip-and-resync, and +++ stays a distinct hang-up path.
Changed files: texecom_alarm/src/texecom_alarm/protocol/client.py, texecom_alarm/src/texecom_alarm/protocol/frame.py, texecom_alarm/tests/test_protocol_client.py, texecom_alarm/tests/test_protocol_frame.py
Verification: Unit tests capturing log records (no live panel). `cd texecom_alarm && python -m pytest tests/test_protocol_client.py tests/test_protocol_frame.py -q` → 58 passed. Full DoD: `pytest --cov=texecom_alarm --cov-fail-under=90 -q` → 402 passed, 92.28% coverage; `ruff check` and `ruff format --check` clean.
Notes/assumptions: Log event is `panel_decode_miss reason=%s leading_hex=%s` at WARNING (not TRACE). Reasons: `not 't'`, `bad length`, `bad CRC`, `unknown type`. Leading hex is the first 32 buffer bytes. `+++` still raises ForcedDisconnect with its existing message and does not emit `panel_decode_miss`. Skip-and-resync was not restored.

## Build phase
phase: merging
<!-- SECTION:FINAL_SUMMARY:END -->
