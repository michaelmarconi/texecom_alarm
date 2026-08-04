---
id: TASK-1
title: Add-on configuration surface
status: in-progress
assignee: []
created_date: '2026-08-04 12:51'
updated_date: '2026-08-04 13:37'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:mechanical'
  - 'adr:ADR-005'
  - 'adr:ADR-003'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-005-use-confirmed-shared-arm-disarm-commands-with-configurable-part-arm-mapping.md
  - docs/definition-of-done.md
  - DOCS.md
priority: medium
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** The add-on still exposes only a placeholder `message` option, so installers cannot supply panel, MQTT, or Part-Arm facts the bridge needs.
**Goal:** Documented Supervisor options load into a typed config object covering panel connection, MQTT broker settings, and Away/Night/Home mode-byte mapping.
**Why now:** Unblocked and next — every later session and publish path reads this config.

Part-Arm mapping uses three discrete mode-byte fields (configurable per install, never this household's layout hardcoded).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Typed settings expose panel, MQTT, and three Part-Arm mode-byte fields from options/schema
- [ ] #2 DOCS.md describes every option and the the prior MQTT bridge stop-before-start cutover note
- [ ] #3 Invalid or missing required options fail with a clear error in tests
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: config.yaml (modify), DOCS.md (modify), rootfs/etc/services.d/texecom_alarm/run (modify), texecom-alarm-app/src/texecom_alarm/config.py (create), texecom-alarm-app/tests/test_config.py (create).
1. Replace placeholder `message` with panel host/port, UDL password, MQTT host/port/credentials/topic prefix, and three Part-Arm mode-byte options (away/night/home) plus schema defaults.
2. Implement a small asyncio-friendly loader that reads Supervisor options (or env/file stand-in for local pytest) into a typed settings object.
3. Document each option in DOCS.md, including cutover note that the prior MQTT bridge must be stopped before first connect.
4. Wire bashio::config keys in the s6 run script for the real option names.
Test strategy: pytest unit tests for defaults, required fields, and Part-Arm mapping parse — no broker or panel.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->
