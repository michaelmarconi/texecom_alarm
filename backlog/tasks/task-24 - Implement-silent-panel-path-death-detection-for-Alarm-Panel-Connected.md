---
id: TASK-24
title: Implement silent panel-path death detection for Alarm Panel Connected
status: done
assignee: []
created_date: '2026-08-08 09:52'
updated_date: '2026-08-09 13:01'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-010'
  - 'adr:ADR-004'
  - 'ac:AC1'
  - 'ac:AC2'
  - 'ac:AC3'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-010-use-command-reject-events-and-periodic-house-state-polling-for-silent-panel-path-death-detection.md
  - docs/specs/spec-panel-link-liveness.md
  - docs/spikes/spike-008-silent-panel-path-death-detection/SPIKE.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Alarm Panel Connected today mainly flips off on forced disconnect. Arm/disarm can fail while the idle heartbeat still succeeds, and we still do not know when that zombie starts on the live panel — we need a truthful signal and enough logs to diagnose the next occurrence.
**Goal:** Detect untrustworthy panel path (command reject/timeout + house/arm trust poll), flip Alarm Panel Connected accordingly, recover to live after corroboration without restart — and emit operator-grade logs so a live zombie can be reconstructed from add-on logs.
**Why now:** Detection is ADRed; recovery/auto-reLOGIN stays deferred until we have live evidence; this slice ships visibility first.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Arm or disarm reject/timeout publishes Alarm Panel Connected OFF even while keepalive can still succeed; zone/alarm entities are not marked unavailable solely for that degrade; the log line includes reason and keepalive-still-ok context
- [x] #2 With no zone push traffic, connectivity stays ON; a failed trust poll publishes OFF and logs reason trust_poll_* with timing context
- [x] #3 After a single transient command reject, connectivity returns ON after a successful trust poll past the 30s recover window without restarting the process, and the recover path logs the transition to live
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom-alarm-app/src/texecom_alarm/panel_trust.py (create), texecom-alarm-app/src/texecom_alarm/arm_commands.py (modify), texecom-alarm-app/src/texecom_alarm/app.py (modify), texecom-alarm-app/tests/fake_panel.py (modify), texecom-alarm-app/tests/test_panel_trust.py (create), texecom-alarm-app/tests/test_arm_commands.py (modify), texecom-alarm-app/tests/test_e2e_fake_panel.py (modify).

1. Add a panel-link trust helper: record command-failure time; on arm/disarm reject/timeout publish Alarm Panel Connected OFF; every 30s run a get_area_flags trust poll alongside (not instead of) the existing ~15s idle keepalive; on poll NAK/timeout publish OFF; publish ON only when a poll succeeds and no command failure in the last 30s recover window. Never degrade on quiet zones alone. Do not auto tear-down/re-LOGIN or auto-retry the failed command.
2. Wire arm and disarm so reject/timeout records failure + OFF (keep existing arm NAK → republish last-known alarm state).
3. Diagnostic logging (required for live watch): on command reject/timeout and on trust-poll failure/success-to-live, log at WARNING (failure) / INFO (recover) with: reason (arm_nak / disarm_nak / arm_timeout / disarm_timeout / trust_poll_nak / trust_poll_timeout), HA mode if any, whether the last idle keepalive still succeeded, seconds since last successful trust poll and since last command failure, and panel-link payload being published (OFF/ON). Do not log UDL/password or full frame dumps at INFO/WARNING (TRACE remains for raw traffic).
4. Drive the trust poll from the panel listen loop; reuse existing area-flags sizing helpers from the startup snapshot path.
5. Extend FakePanel for: keepalive OK + arm NAK; trust-poll fail then succeed; quiet (no zone pushes) stays live.
6. Tests cover detector ACs plus assertions that failure/recover paths emit the structured reason fields (caplog / logger extra).

Test strategy: how we'll know = unit/integration against FakePanel stand-in (no live panel). Command: cd texecom-alarm-app && python -m pytest tests/test_panel_trust.py tests/test_arm_commands.py tests/test_e2e_fake_panel.py -q
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Implemented ADR-010 silent panel-path death detection — command reject/timeout + 30s area-flags trust poll drive Alarm Panel Connected, with auto-recover and structured logs.
Changed files: texecom-alarm-app/src/texecom_alarm/panel_trust.py, texecom-alarm-app/src/texecom_alarm/arm_commands.py, texecom-alarm-app/src/texecom_alarm/app.py, texecom-alarm-app/tests/fake_panel.py, texecom-alarm-app/tests/test_panel_trust.py, texecom-alarm-app/tests/test_arm_commands.py, texecom-alarm-app/tests/test_e2e_fake_panel.py, texecom-alarm-app/src/texecom_alarm/protocol/client.py (ruff format only), texecom-alarm-app/tests/test_reconnect.py (ruff format only)
Verification: how we'll know = FakePanel unit/integration for AC1–AC3 + structured log fields; python -m pytest tests/test_panel_trust.py tests/test_arm_commands.py tests/test_e2e_fake_panel.py -q → 35 passed; full suite pytest --cov=texecom_alarm --cov-fail-under=90 → 210 passed, ~93% coverage; ruff check/format clean
Notes/assumptions: Poll/recover defaults are 30s (plan-time); run(..., trust_poll_interval=, trust_recover_window=) are test-only overrides. No auto re-LOGIN or command auto-retry. Zone/alarm availability unchanged (ADR-004). Pre-commit fixed isinstance UP038 in test_panel_trust.py before landing.

## Build phase
phase: done
<!-- SECTION:FINAL_SUMMARY:END -->
