---
id: TASK-62
title: 'Checkpoint: texecom-alarm-app busy-versus-dead session wave'
status: awaiting-review
assignee: []
created_date: '2026-08-31 21:20'
updated_date: '2026-09-01 08:37'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-59
  - TASK-60
  - TASK-61
ordinal: 56000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (pytest in texecom_alarm/ exits 0)
- [ ] #2 Lint/format clean (ruff check and ruff format --check exit 0)
- [ ] #3 Wave e2e: FakePanel omits post-ACK GetAreaFlags when live AREA already published; ACK then unparseable housekeeping is not command-failure and Connection stays on if re-login succeeds on attempt 1; decode-fail logs reason plus leading hex at INFO or WARNING; patience, refused-arm Connection-off, and never-skip-bytes stay green
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- All tests pass: pass — `python -m pytest --cov=texecom_alarm --cov-fail-under=90 -q` in `.worktrees/task-62/texecom_alarm` (primary `.venv`): **402 passed**, coverage **92.10%** (≥90), exit 0
- Lint/format clean: pass — `ruff check`: All checks passed; `ruff format --check`: 46 files already formatted; both exit 0
- Wave e2e (omit GetAreaFlags when live AREA published; ACK then unparseable housekeeping not command-failure, Connection on if re-login attempt 1 succeeds; decode-fail logs reason plus leading hex at INFO/WARNING; patience, refused-arm Connection-off, never-skip-bytes stay green): pass — named e2e + `tests/test_protocol_client.py` + `tests/test_protocol_frame.py`: **62 passed**. Confirmed in code: `flags_round_trip_needed_after_command` omits post-ACK GetAreaFlags when live AREA already published (`test_e2e_arm_omits_flags_when_live_area_already_published`; Home disarm without AREA still reads flags). Post-ACK `ForcedDisconnect` calls `note_session_collision()`, not `record_command_failure`; collision reconnect keeps Connection ON if attempt-1 re-login succeeds (`test_e2e_post_ack_unparseable_flags_is_collision_not_failed_tap`). Decode miss logs `reason=` + `leading_hex=` at WARNING; `+++` is a distinct hang-up. Unexpected bytes raise `ForcedDisconnect` (consume 1, no scan-forward). Check-in patience (`_checkin_patience`) is a separate clock from the command-reject fail/recover windows; NAK arm still publishes Connection OFF immediately. FakePanel is not treated as proof of a real Premier Elite torn-frame (AGENTS.md CI-may-not-claim).
Notes: Wave ACs and ADR-021 DoD hold on FakePanel/CI; live garage-return torn-frame remains `/accept`.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 docs/architecture.md session health (ADR-021) is not violated: extra flags read omitted when live events already published; collision after ACK is not a failed tap; Connection on if attempt-1 re-login succeeds
- [ ] #2 Do not restore skip-and-resync; do not merge check-in patience with the command-reject fail window
- [ ] #3 FakePanel is not treated as proof that a real Premier Elite torn-frame stays quiet on Connection
<!-- DOD:END -->
