---
id: TASK-62
title: 'Checkpoint: texecom-alarm-app busy-versus-dead session wave'
status: in-progress
assignee: []
created_date: '2026-08-31 21:20'
updated_date: '2026-09-01 08:34'
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
## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 docs/architecture.md session health (ADR-021) is not violated: extra flags read omitted when live events already published; collision after ACK is not a failed tap; Connection on if attempt-1 re-login succeeds
- [ ] #2 Do not restore skip-and-resync; do not merge check-in patience with the command-reject fail window
- [ ] #3 FakePanel is not treated as proof that a real Premier Elite torn-frame stays quiet on Connection
<!-- DOD:END -->
