---
id: TASK-18
title: Add log_level config and apply at startup
status: awaiting-review
assignee: []
created_date: '2026-08-07 17:22'
updated_date: '2026-08-07 17:30'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'ac:AC1'
  - 'ac:AC2'
  - 'ac:AC3'
dependencies: []
documentation:
  - docs/specs/spec-diagnostics-logging.md
priority: high
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Logging is hard-wired at INFO with no add-on option, so operators cannot quiet the app to WARNING or turn up detail when hunting faults.
**Goal:** Add-on configuration offers WARNING, INFO, DEBUG, and TRACE (default INFO), and the running process applies the selected level after options take effect.
**Why now:** Unblocked coverage gap from Accepted spec-diagnostics-logging; required before instrumentation work can assume a selectable level.

Open calls accepted at plan time: panel-link-liveness deferred; AC7 manual on checkpoint.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 config.yaml schema list tokens for log_level are exactly WARNING, INFO, DEBUG, TRACE
- [ ] #2 Unset/default configuration starts the app at INFO
- [ ] #3 Selecting DEBUG or TRACE at startup results in that effective logging level
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: config.yaml (modify), texecom-alarm-app/src/texecom_alarm/config.py (modify), texecom-alarm-app/src/texecom_alarm/app.py (modify), texecom-alarm-app/tests/test_config.py (modify or create), texecom-alarm-app/tests/test_logging_level.py (create). 1. Add log_level to options/schema as list(WARNING|INFO|DEBUG|TRACE) with default INFO — schema list tokens are the visible Supervisor labels (AC1). 2. Parse into Settings; default INFO when unset (AC2). 3. Map TRACE to a logging level below DEBUG (e.g. custom level 5 named TRACE) and call basicConfig/root setLevel from settings at startup (AC3). 4. Tests: schema/option tokens; default INFO; selected level filters a logger (unit). Test strategy: how we'll know = unit test; pytest on config + logging setup modules.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Add-on log_level (WARNING|INFO|DEBUG|TRACE, default INFO) parses into Settings and is applied at startup, with TRACE as custom level 5.
Changed files: config.yaml, DOCS.md, translations/en.yaml, texecom-alarm-app/src/texecom_alarm/config.py, texecom-alarm-app/src/texecom_alarm/app.py, texecom-alarm-app/src/texecom_alarm/logging_setup.py, texecom-alarm-app/tests/test_logging_level.py, texecom-alarm-app/tests/test_app_mqtt.py, texecom-alarm-app/tests/test_reconnect.py
Verification: unit tests (schema tokens, default INFO, INFO/DEBUG/TRACE filtering); pytest --cov=texecom_alarm --cov-fail-under=90 → 183 passed, 93.75% coverage; ruff clean
Notes/assumptions: Supervisor UI name set to "Log level" (spec left label open); DOCS.md + translations updated for DoD config docs

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->
