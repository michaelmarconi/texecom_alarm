---
id: TASK-48
title: 'Checkpoint: texecom-alarm-app keepalive-retry-budget wave'
status: done
assignee: []
created_date: '2026-08-27 19:36'
updated_date: '2026-08-27 22:16'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-47
ordinal: 42000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All tests pass (cd texecom_alarm && python -m pytest -q exits 0)
- [x] #2 Build/lint clean (ruff check / ruff format --check, as configured, exit 0)
- [x] #3 Reconnect end-to-end suite covers the existing keepalive-timeout/NAK-immediate zombie case and the new bounded-retry transient-burst case, both green
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- Tests pass: pass — cd texecom_alarm && python3 -m pytest -q -> 348 passed in 14.90s, exit 0.
- Lint/format clean: pass — ruff check . -> All checks passed!; ruff format --check . -> 46 files already formatted; both exit 0.
- Reconnect suite covers both zombie and transient-burst cases: pass — texecom_alarm/tests/test_reconnect.py has test_keepalive_nak_enters_reconnect_path (sustained bad reply -> still degrades Connection and reconnects, TASK-45 regression guard) and test_keepalive_wrong_shape_transient_burst_does_not_flip_connection (recovers within budget -> Connection never goes OFF); test_keepalive_wrong_shape_sustained_failure_still_reconnects further corroborates the exhausted-budget path. All pass.
Notes: PanelClient.keepalive()/send_command() retry the same command+sequence via a shared retries=self.keepalive_retries budget with retry_if gating on reply shape, only raising once exhausted — matches the tightened architecture wording and protocol-reference rows. The shared-knob decision (keepalive_retries used by both keepalive() and login()) is visible as inline code comments at both sites, not merely claimed.

## Build phase
phase: done
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 Bounded keepalive retry matches docs/architecture.md's tightened Idle keepalive / Panel-connection detection / Mid-run session heal wording, and docs/protocol-reference.md's documented behavioural constraint
- [x] #2 TASK-45's zombie-session fix (sustained bad keepalive still degrades Connection and reconnects) has no regression
<!-- DOD:END -->
