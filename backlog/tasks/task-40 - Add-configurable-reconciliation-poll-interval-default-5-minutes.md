---
id: TASK-40
title: 'Add configurable reconciliation poll interval, default 5 minutes'
status: awaiting-review
assignee: []
created_date: '2026-08-25 15:27'
updated_date: '2026-08-25 21:06'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-017'
dependencies:
  - TASK-39
documentation:
  - >-
    docs/adrs/adr-017-use-a-configurable-5-minute-interval-for-the-panel-reconciliation-poll.md
priority: medium
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** The reconciliation poll's interval is hardcoded at 30 seconds — a value only chosen to satisfy the fast connectivity-detection bound the previous decision required. The household also asked whether this cadence is behind occasional audible pips from the panel.
**Goal:** The reconciliation poll runs on a household-configurable interval, defaulting to 5 minutes, with no effect on Alarm Panel Connection either way.
**Why now:** depends on TASK-39's decoupling landing first — changing the cadence before that would still let a slower poll degrade connectivity for longer.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 When unset, the reconciliation poll interval defaults to 300 seconds (5 minutes)
- [ ] #2 Setting reconciliation_poll_interval_seconds in add-on options changes the interval the poll actually fires on
- [ ] #3 Changing the interval has no effect on Alarm Panel Connection's degraded/live state — only on how often reconciliation runs
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom_alarm/src/texecom_alarm/config.py (modify) — add DEFAULT_RECONCILIATION_POLL_INTERVAL_SECONDS = 300.0, a reconciliation_poll_interval_seconds Settings field + env key (TEXECOM_RECONCILIATION_POLL_INTERVAL_SECONDS) + _optional_float parse call, mirroring the existing trust_fail_window_seconds pattern. texecom_alarm/config.yaml (modify) — add reconciliation_poll_interval_seconds: 300 option + float(0,) schema entry (root config.yaml is a symlink to this file, no separate edit). texecom_alarm/src/texecom_alarm/app.py (modify) — wire cfg.reconciliation_poll_interval_seconds into PanelTrust(poll_interval=...) the same way trust_fail_window_seconds flows into fail_window, replacing the current TRUST_POLL_INTERVAL_SECONDS literal default. texecom_alarm/src/texecom_alarm/panel_trust.py (modify) — update the module-level default constant to 300.0 with a comment citing ADR-017. texecom_alarm/tests/test_config.py (modify) — add parse tests: default 300s when unset, override via options/env, rejects negative. texecom_alarm/tests/test_panel_trust.py (modify) — add/confirm a test that changing the interval changes poll cadence without touching the connection signal. Test strategy: how we'll know = unit tests in test_config.py (stand-in: raw options mapping) and test_panel_trust.py (stand-in: fake clock); run pytest texecom_alarm/tests/test_config.py texecom_alarm/tests/test_panel_trust.py.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Reconciliation poll interval is now a configurable add-on setting (reconciliation_poll_interval_seconds), defaulting to 300s (5 minutes), with no effect on Alarm Panel Connection.
Changed files: texecom_alarm/config.yaml, texecom_alarm/src/texecom_alarm/app.py, texecom_alarm/src/texecom_alarm/config.py, texecom_alarm/src/texecom_alarm/panel_trust.py, texecom_alarm/tests/test_config.py, texecom_alarm/tests/test_panel_trust.py
Verification: pytest tests — 346 passing; ruff check . — clean; ruff format --check . — clean; pytest --cov=texecom_alarm --cov-fail-under=90 — 92.48% coverage.
Notes/assumptions: Mirrored the trust_fail_window_seconds pattern exactly in config.py (default constant, Settings field, env key, _optional_float parse call). No app.py-level wiring test added, consistent with the existing test depth for the sibling trust_fail_window_seconds setting; coverage comes via config.py parse tests plus panel_trust.py cadence tests.

## Build phase
phase: merging
<!-- SECTION:FINAL_SUMMARY:END -->
