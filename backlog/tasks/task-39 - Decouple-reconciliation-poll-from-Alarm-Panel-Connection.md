---
id: TASK-39
title: Decouple reconciliation poll from Alarm Panel Connection
status: in-progress
assignee: []
created_date: '2026-08-25 15:27'
updated_date: '2026-08-25 15:38'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-016'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-016-use-keepalive-failure-and-command-reject-events-for-panel-connection-detection.md
priority: medium
ordinal: 33000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Alarm Panel Connection currently goes degraded whenever the periodic reconciliation poll times out or is rejected, even when routine check-ins and commands are healthy. A live incident showed a single isolated poll timeout during a burst of panel activity produced a false ~27-second "disconnected" signal.
**Goal:** Alarm Panel Connection degrades only on a missed check-in/disconnect or a rejected/timed-out arm/disarm command; recovery is driven by check-ins resuming, not by the reconciliation poll succeeding; an isolated poll failure with everything else healthy never flips the signal.
**Why now:** unblocked and next — this is the shipped behavior the new decision supersedes; the poll-interval change queued after this depends on it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A reconciliation-poll NAK or timeout, in isolation (keepalive healthy, no recent command failure), does not publish Alarm Panel Connection OFF
- [ ] #2 A rejected/timed-out arm or disarm command still immediately publishes Alarm Panel Connection OFF, and recovers to ON once keepalives resume and the command-failure recover window has cleared — with no dependency on a poll succeeding
- [ ] #3 Missed keepalives / disconnect still publish Alarm Panel Connection OFF and recover via the existing reconnect path, unchanged
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom_alarm/src/texecom_alarm/panel_trust.py (modify) — stop _on_poll_failure from calling _mark_degraded(); move the _maybe_recover() trigger from poll() success to note_keepalive_ok(); update module docstring/log wording to cite ADR-016 instead of ADR-010. texecom_alarm/src/texecom_alarm/app.py (modify) — update _listen_panel_messages docstring/comments citing ADR-010 to ADR-016. texecom_alarm/tests/test_panel_trust.py (modify) — remove/rewrite test_trust_poll_nak_publishes_off_with_timing_context and test_trust_poll_timeout_reason (poll failure must no longer publish OFF); rework the recovery assertions in test_transient_command_reject_recovers_after_window, test_corroboration_within_fail_window_does_not_request_relogin, and test_e2e_trust_poll_fail_then_recover to be keepalive-driven; add a new test asserting an isolated poll NAK/timeout with keepalive healthy never publishes OFF (the SPIKE-011 S6 shape). texecom_alarm/tests/test_e2e_fake_panel.py (modify) — update ADR-010 docstring citations to ADR-016 (no behavior change). texecom_alarm/tests/test_arm_commands.py (modify) — same docstring citation update. Test strategy: how we'll know = unit tests in test_panel_trust.py (stand-ins: RecordingMqttPublisher + fake clock) plus the FakePanel end-to-end suite; run pytest texecom_alarm/tests/test_panel_trust.py texecom_alarm/tests/test_e2e_fake_panel.py texecom_alarm/tests/test_arm_commands.py.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->
