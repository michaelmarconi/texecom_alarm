---
id: TASK-51
title: >-
  Declare the session dead only after check-in failure persists past the
  patience window
status: attention
assignee: []
created_date: '2026-08-28 16:14'
updated_date: '2026-08-29 09:07'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Attention
## Attention
Category: 3 governance
Attempted: Implemented the check-in patience window (ADR-020) - consecutive check-in failures tracked via PanelTrust._checkin_failure_since, only raising ForcedDisconnect once checkin_patience_seconds is exceeded. Full suite green (366 passed), ruff clean, coverage 92.15%. Required code review and Bugbot both ran as the gate pair.
Failed: Both the required review and Bugbot independently flagged the same governance violation: panel_trust.py's note_panel_traffic() (~line 149) clears _checkin_failure_since on every well-formed unsolicited push frame (zone/area/log), not just on a successful check-in reply (note_keepalive_ok already clears it correctly on that path). This treats unprompted panel traffic as evidence the check-in session is healthy, which ADR-020 explicitly rejected as Option E ('reproduces the 0.2.0 zombie, where the connection carried traffic all day while every command was refused') and which AGENTS.md lists as an explicit stop condition under ADR-020: 'Before treating unprompted panel traffic as evidence the session is healthy for patience-window purposes: stop and ask a human.' Concretely: in app.py's listen loop, a due check-in that fails and starts the patience clock can have that clock immediately reset by trust.note_panel_traffic() called on the very same received frame (or on any later unsolicited frame before the next scheduled check-in) - so a panel that continuously refuses check-ins while still pushing other traffic may never reach the patience deadline, and Connection could incorrectly stay ON indefinitely. No existing test exercises concurrent unsolicited traffic alongside a failing check-in, so CI is green despite this. Two smaller mechanical findings also surfaced (stale TASK-47/TASK-45 pipeline-ID citations in comments/docstrings actively rewritten by this diff - protocol/client.py:84, tests/test_reconnect.py:788) but per the stop taxonomy, a non-mechanical finding halts the whole findings budget - no fix cycle was dispatched.
Decision needed: Should note_panel_traffic() stop clearing _checkin_failure_since entirely (leaving only a successful GETDATETIME reply via note_keepalive_ok as proof the check-in path itself is healthy), or is there a narrower, deliberate reason unprompted traffic should still count toward check-in liveness that the ADR/stop-condition wording doesn't anticipate? If the former, TASK-51 needs a fix-and-re-review cycle (removing that one line, adding a regression test for concurrent traffic + failing check-in, and cleaning up the two stale pipeline-ID citations) before this can merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Softened check-in failures into a patience window (ADR-020) - a refused/unanswered check-in now only ends the session once failures persist continuously past checkin_patience_seconds, with login()'s retry budget decoupled from keepalive()'s (now single-attempt) behavior, plus a frame-parsing fix the retry removal exposed.
Changed files: texecom_alarm/src/texecom_alarm/app.py, texecom_alarm/src/texecom_alarm/panel_trust.py, texecom_alarm/src/texecom_alarm/protocol/client.py, texecom_alarm/src/texecom_alarm/protocol/frame.py, texecom_alarm/tests/test_protocol_client.py, texecom_alarm/tests/test_startup_login_backoff.py, texecom_alarm/tests/test_operator_errors.py, texecom_alarm/tests/test_session_heal.py, texecom_alarm/tests/test_e2e_fake_panel.py, texecom_alarm/tests/test_reconnect.py, texecom_alarm/tests/test_panel_trust.py
Verification: pytest -q -> 366 passed; ruff check/format clean; coverage 92.15% (>=90% gate). AC1/AC2 via test_panel_trust.py (checkin-failure-within-patience / past-patience / success-restarts-clock / outright-disconnect-bypasses-patience) plus reconnect/session-heal/e2e updates. AC3 via test_command_watchdog_fail_window_independent_of_checkin_patience.
Notes/assumptions: Tracker lives on PanelTrust as its own _checkin_failure_since field, structurally separate from _degraded_since (command-rejection watchdog) - no shared clock/helper. PanelClient.keepalive_retries renamed to login_retries (breaking rename, all in-repo usages updated); keepalive() simplified to single attempt (retries=0). FakePanel already had sufficient primitives - no new API added. Fixed a latent bug in protocol/frame.py's try_decode_frame: 3-byte +++ end-of-session marker was only recognized once buffer held >=4 bytes, so +++ arriving alone would time out instead of raising ForcedDisconnect - previously masked by keepalive()'s old same-call retry; this touches a file outside the task's originally-scoped list, flagging for reviewer awareness. Patience boundary is inclusive (>=), matching TASK-49's inclusive patience==interval convention. run() gained a trust_checkin_patience override parameter mirroring existing trust_poll_interval/trust_recover_window/trust_fail_window pattern.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->
