---
id: TASK-25
title: Progressive backoff for startup panel login retries
status: ready
assignee: []
created_date: '2026-08-09 13:45'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'ac:AC1'
  - 'ac:AC2'
  - 'ac:AC3'
  - 'ac:AC4'
dependencies: []
documentation:
  - docs/specs/spec-startup-login-backoff.md
  - docs/architecture.md
priority: medium
ordinal: 19000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** When the add-on starts and the panel is still busy or releasing a previous session, first connect/login fails are retried on a short fixed pause, which can hammer ComIP and makes logs look like a hang.
**Goal:** Failed first-login attempts wait progressively longer (capped at 30 seconds), each next wait is named in the log, and the add-on still reaches normal monitoring when the panel accepts — without exiting.
**Why now:** Architecture and the accepted startup-login-backoff spec are settled; unblocked and next for reliability at restart.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After repeated startup connect/login failures, recorded waits are strictly non-decreasing, increase at least once, never exceed 30 seconds, and remain at 30 once the cap is reached
- [ ] #2 Each failed startup login attempt logs the wait duration that will be used before the next try
- [ ] #3 After several failed startup logins under backoff, when the panel accepts login the app proceeds into normal monitoring without exiting the process
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom-alarm-app/src/texecom_alarm/app.py (modify), texecom-alarm-app/tests/test_startup_login_backoff.py (create), texecom-alarm-app/tests/fake_panel.py (modify if needed for N failed logins then succeed), texecom-alarm-app/tests/test_operator_errors.py (modify — keep startup retry injectable for fast tests).

1. Replace the fixed-interval first-login retry in `_connect_and_login_with_retry` (today uses a single interval, defaulting to reconnect_normal_interval_seconds) with the accepted schedule: after the k-th failure (k=1,2,3,…), wait min(5 × 2^(k-1), 30) seconds before the next try — 5→10→20→30 then stay at 30. Never exit; never wait longer than 30s. Do not change ADR-002 mid-run reconnect budgets.
2. Keep (or refine) test-only injection so CI can use a clock/sleep double and optional scale factor without changing production defaults — how we'll know must still assert the production schedule shape (non-decreasing, increases at least once, never exceeds 30).
3. On each failed attempt, log the wait duration that will be used before the next try (ERROR/INFO recovery line must include that number).
4. FakePanel / integration: fail login for N attempts then succeed; assert recorded waits; assert monitoring startup continues after success; assert indefinite failures stay at 30s cap.

Test strategy: how we'll know = unit/integration against FakePanel stand-in (no live panel). Command: cd texecom-alarm-app && python -m pytest tests/test_startup_login_backoff.py tests/test_operator_errors.py -q
<!-- SECTION:PLAN:END -->
