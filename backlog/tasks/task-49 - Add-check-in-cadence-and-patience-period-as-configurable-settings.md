---
id: TASK-49
title: Add check-in cadence and patience-period as configurable settings
status: done
assignee: []
created_date: '2026-08-28 16:13'
updated_date: '2026-08-28 17:08'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:mechanical'
  - 'adr:ADR-020'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-020-use-scheduled-check-ins-and-a-patience-window-for-panel-session-recovery.md
priority: medium
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** How often the app checks in with the panel, and how long it tolerates a refused or unanswered check-in before treating the session as dead, are both currently baked into code rather than exposed to the household.
**Goal:** Both are ordinary add-on settings, so a household can tune them without a code change, and the defaults ship sane (cadence comfortably shorter than the panel's own idle tolerance; patience roughly three missed check-ins).
**Why now:** Every later task in this wave reads these settings — this is the foundation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Settings exposes checkin_interval_seconds and checkin_patience_seconds with documented defaults
- [x] #2 Both are overridable via add-on config and the equivalent environment variables
- [x] #3 Settings validation rejects a patience period shorter than one check-in interval
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom_alarm/src/texecom_alarm/config.py (modify — add `checkin_interval_seconds` and `checkin_patience_seconds` fields, env var mapping, and loader defaults, following the existing `reconnect_delay_seconds`/`trust_fail_window_seconds` pattern), texecom_alarm/config.yaml (modify — add schema entries + translations), texecom_alarm/translations/en.yaml (modify — labels), texecom_alarm/tests/test_config.py (modify — default + override + validation cases). Test strategy: how we'll know = unit tests against Settings loader (no stand-in needed); `pytest tests/test_config.py -q`. Defaults: cadence well under the panel's ~60s idle-hang tolerance (docs/protocol-reference.md); patience ≈ 3× cadence per ADR-020.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Added checkin_interval_seconds and checkin_patience_seconds as configurable Settings (with defaults, env-var overrides, and cross-field validation) per ADR-020.
Changed files: texecom_alarm/src/texecom_alarm/config.py, texecom_alarm/config.yaml, texecom_alarm/translations/en.yaml, texecom_alarm/DOCS.md, texecom_alarm/tests/test_config.py
Verification: pytest -q -> 355 passed; ruff check/format clean; coverage 92.56% (>=90%). Mechanical fix cycle: re-worded 6 test docstrings that cited pipeline AC numbers to plain product language (product-code-comments.mdc); re-verified 355 passed, ruff clean; re-review verdict clean.
Notes/assumptions: Defaults 15.0s check-in interval (matches existing hardcoded idle timeout) and 45.0s patience (3x, per ADR-020's roughly three missed check-ins). Validation boundary is inclusive (patience == interval allowed).

## Build phase
phase: done
<!-- SECTION:FINAL_SUMMARY:END -->
