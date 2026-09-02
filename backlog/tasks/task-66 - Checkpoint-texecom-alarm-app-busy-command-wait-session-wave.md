---
id: TASK-66
title: 'Checkpoint: texecom-alarm-app busy command-wait session wave'
status: awaiting-review
assignee: []
created_date: '2026-09-02 10:51'
updated_date: '2026-09-02 12:21'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-64
  - TASK-65
ordinal: 60000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (cd texecom_alarm && python -m pytest -q exits 0)
- [ ] #2 Coverage and lint bars still hold (pytest --cov=texecom_alarm --cov-fail-under=90; ruff check + ruff format --check)
- [ ] #3 FakePanel e2e: timeout-with-events then new-request ACK keeps Connection on; silent timeout and NAK still turn Connection off immediately
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- All tests pass (cd texecom_alarm && python -m pytest -q exits 0): pass — 425 passed in 23.64s, exit 0
- Coverage and lint bars still hold (pytest --cov=texecom_alarm --cov-fail-under=90; ruff check + ruff format --check): pass — 425 passed, coverage 92.91% (≥90); ruff check All checks passed; ruff format --check 46 files already formatted
- FakePanel e2e: timeout-with-events then new-request ACK keeps Connection on; silent timeout and NAK still turn Connection off immediately: pass — 7 targeted tests passed (test_e2e_busy_arm_timeout_retry_keeps_connection_on, test_e2e_silent_arm_timeout_turns_connection_off_immediately, test_e2e_arm_nak_still_turns_connection_off_immediately, test_e2e_exhausted_busy_arm_retries_turn_connection_off_without_heal_retry, test_chatty_arm_disarm_timeout_retries_as_new_request ×2, test_silent_disarm_timeout_does_not_retry_as_new_request); architecture.md session-health matches ADR-022; unexpected bytes are not skipped; e2e docstring does not claim a live Premier Elite flood
Notes: architecture busy/new-request/refuse/silent/exhausted text matches ADR-022; CI does not claim live trigger-then-Disarm flood; no byte-skip/resync reintroduced.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Session health in docs/architecture.md matches ADR-022: busy Arm/Disarm wait retries as a new request; Connection off on refuse, silent timeout, or exhausted retries
- [ ] #2 ADR-022 live-only walks (real trigger-then-Disarm flood) are not claimed by CI
- [ ] #3 No skip-and-resync path was reintroduced
<!-- DOD:END -->
