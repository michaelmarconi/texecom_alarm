---
id: TASK-28
title: Bounded tear-down and re-login when trust stays degraded
status: in-progress
assignee: []
created_date: '2026-08-09 23:50'
updated_date: '2026-08-10 08:44'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-011'
  - 'adr:ADR-010'
  - 'adr:ADR-004'
  - 'ac:AC2'
  - 'ac:AC3'
  - 'ac:AC4'
dependencies:
  - TASK-27
documentation:
  - docs/specs/spec-panel-session-heal.md
  - >-
    docs/adrs/adr-011-use-automatic-session-recovery-for-mid-run-panel-path-failures.md
  - docs/architecture.md
priority: medium
ordinal: 22000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Soft trust failures already mark Alarm Panel Connection off and can return to live after a successful house-state check once the recent command-failure window clears. If the path stays untrustworthy forever, tonight that still means waiting for a human restart.
**Goal:** Prefer corroboration first; if Connection is still off after a bounded fail window (plan default 90 seconds, tunable), tear down and log in again, re-sync state, and restore live monitoring without a manual restart — and never silently re-fire a failed arm/disarm tap.
**Why now:** Health-check reconnect (prior task) covers dead keepalive; ADR-011 AC2 needs the stuck-trust heal path next.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 After FakePanel trust-fail that later clears on corroboration within the fail window, Connection returns ON with re-synced state and no session tear-down required
- [ ] #2 After FakePanel trust stays OFF past the fail window (default 90s, shortened in tests), the app tears down, re-logins, re-syncs, and Connection returns ON without add-on restart
- [ ] #3 Heal never auto-retries the failed arm/disarm command; zone/alarm stay available with last-known state during recovery
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

### Files likely affected

- `texecom-alarm-app/src/texecom_alarm/panel_trust.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/app.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/reconnect.py` (modify)
- `texecom-alarm-app/src/texecom_alarm/config.py` (modify — tunable fail window)
- `config.yaml` (modify — optional setting)
- `texecom-alarm-app/tests/fake_panel.py` (modify)
- `texecom-alarm-app/tests/test_panel_trust.py` (modify)
- `texecom-alarm-app/tests/test_session_heal.py` (modify)
- `texecom-alarm-app/tests/test_e2e_fake_panel.py` (modify)

### Implementation steps

1. Keep existing corroboration-first recover (`_maybe_recover` after successful trust poll past command-failure recover window).
2. Add a tunable stuck-trust fail window defaulting to **90 seconds** (3× the shipping 30s trust-poll interval). Document as tunable / live-adjustable — not a final hardcoded forever value (ADR-011 / AGENTS stop condition).
3. When Connection has been continuously OFF for that fail window (soft trust / zombie path, process still up), tear down the panel session and perform re-LOGIN + zone/area snapshots + SETEVENTMESSAGES (reuse reconnect helpers where practical), then publish Connection ON only after re-sync.
4. Never auto-retry the arm/disarm command that caused the original failure as part of heal.
5. Everyday logs for stuck-window expiry and re-login attempts (not TRACE-only). Zone/alarm stay available with last-known state throughout (ADR-004).
6. FakePanel shapes: trust-fail then recover via corroboration alone; trust-fail stuck through fail window then accept re-login; assert no command auto-retry.

### Test strategy

How we'll know = FakePanel unit/integration for corroboration recover vs bounded re-login (session-heal AC2/AC3/AC4). Command: `cd texecom-alarm-app && python -m pytest tests/test_panel_trust.py tests/test_session_heal.py tests/test_e2e_fake_panel.py -q`. Shorten fail window in tests. Live zombie corroboration remains `/accept`.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->
