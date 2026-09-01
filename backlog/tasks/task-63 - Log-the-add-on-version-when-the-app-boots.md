---
id: TASK-63
title: Log the add-on version when the app boots
status: awaiting-review
assignee: []
created_date: '2026-09-01 09:44'
updated_date: '2026-09-01 11:48'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
dependencies: []
priority: medium
ordinal: 57000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Supervisor logs do not say which add-on version is running. After an Update it is hard to tell which release produced a log dump.
**Goal:** On a successful start, at the default log level, the add-on logs its version so a household log identifies the running release.
**Why now:** Asked after a live walk where mixed versions were easy to confuse, and household HA still needs a card check of the new cut.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A successful boot logs the add-on version at INFO, visible at the default log level
- [ ] #2 The logged version matches the package version
- [ ] #3 The line is emitted after log level is applied, not as a TRACE-only or pre-config leak
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

After log level is applied at process start, emit one INFO line that includes the package version (the same string as `__version__` / the Supervisor release id). Do not rely on the existing DEBUG `app_start` line — default log level is INFO, so that never shows. Keep it a single boot line, not a reconnect spam.

### Files likely affected

- `texecom_alarm/src/texecom_alarm/app.py` (modify)
- `texecom_alarm/tests/test_app_mqtt.py` (modify)

### Test strategy

How we'll know: unit test capturing log records (no live panel). Command: `cd texecom_alarm && python -m pytest tests/test_app_mqtt.py -q`. Drive `main()` with settings loaded and asyncio.run stubbed; after `configure_logging`, assert an INFO record contains `__version__`. Default INFO must show it; TRACE-only is a fail.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Successful boot now logs the package version at INFO after log level is applied, matching `texecom_alarm.__version__`.
Changed files: texecom_alarm/src/texecom_alarm/app.py, texecom_alarm/tests/test_app_mqtt.py, texecom_alarm/CHANGELOG.md
Verification: PYTHONPATH=src pytest tests/test_app_mqtt.py -q → 21 passed; pytest --cov=texecom_alarm --cov-fail-under=90 -q → 407 passed, 92.67% coverage; ruff check + ruff format --check on touched files → clean.
Notes/assumptions: The line is emitted from main() immediately after configure_logging, not from run(), so reconnects do not repeat it. Default log_level=INFO is what the test drives.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->
