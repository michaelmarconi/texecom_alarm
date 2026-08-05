---
id: TASK-15
title: Part-Arm config labels Title Case + emoji and Unused defaults
status: awaiting-review
assignee: []
created_date: '2026-08-05 15:43'
updated_date: '2026-08-05 16:15'
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
  - docs/acceptance.md
  - DOCS.md
priority: high
ordinal: 10000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Part-Arm slot options already map each slot to an HA arm mode, but the Supervisor Configuration radios show lowercase `home`/`night`/`away`, the helper copy is hard to parse, schema defaults still bake this household's Night/Home layout, and the UDL field label/helper need clearer shorter copy.
**Goal:** Configuration radios match the agreed mock (Title Case + emoji after labels + simple helper), all three slots default to Unused, and UDL shows as "Panel UDL password" with helper about the usual 1234 default / ask engineer if login fails.
**Why now:** Practitioner Hold on checkpoint TASK-13 until this polish lands; do not Approve that gate first. Do **not** bump add-on `version` — release policy is a separate task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Radio labels render as Home 🏠 / Night 🌙 / Away 🔒 / Unused (emoji after label); each slot helper matches: Which HA arm button (Home / Night / Away) this Part-Arm slot should use — or Unused if the slot isn't configured on your panel.
- [ ] #2 Schema and Settings defaults for part_arm_1, part_arm_2, and part_arm_3 are all unused (not household Night/Home); unit tests and DOCS.md reflect that; remapping still changes cmd=6 mode bytes without code edits.
- [ ] #3 UDL option name is "Panel UDL password"; description states the usual default is 1234 and to check with the engineer if login fails. Add-on version is not bumped.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: translations/en.yaml, config.yaml (defaults only — not version), DOCS.md, texecom-alarm-app/src/texecom_alarm/config.py, texecom-alarm-app/tests/test_config.py (and any tests assuming Night/Home defaults).
1. Change schema/options defaults for part_arm_1/2/3 to unused; keep list values as home|night|away|unused for the backend.
2. Update Supervisor translations (and list option display strings if required) so radios show `Home 🏠` / `Night 🌙` / `Away 🔒` / `Unused` with emoji after the label; helper: "Which HA arm button (Home / Night / Away) this Part-Arm slot should use — or Unused if the slot isn't configured on your panel."
3. Set udl_password name to "Panel UDL password" and description to "Default is usually 1234, but check with your engineer if login fails." (UDL expansion may stay brief in the same description).
4. Align Python DEFAULT_PART_ARM_* and docs. Do **not** change config.yaml `version`.
Test strategy: how we'll know = unit tests for Unused defaults + remapping still works; pytest test_config (and related) green; ruff clean. No live panel required.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Part-Arm radios show Home 🏠 / Night 🌙 / Away 🔒 / Unused via schema display strings; all slots default unused; UDL copy updated; version stays 0.0.1.
Changed files: config.yaml, translations/en.yaml, DOCS.md, texecom-alarm-app/src/texecom_alarm/config.py, texecom-alarm-app/tests/test_config.py
Verification: PYTHONPATH=src pytest tests/test_config.py → 26 passed; PYTHONPATH=src pytest tests/ → 168 passed; ruff check src tests → clean; ruff format --check on changed py files → clean
Notes/assumptions: Supervisor translation schema strips items, so radio labels are schema list members; Python normalizes to canonical home|night|away|unused. Schema defaults Title-Case Unused. Version not bumped.

## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Part-Arm radios match the agreed mock (Title Case, emoji after label, simple helper)
- [ ] #2 Defaults are Unused for all three slots (ADR-005: do not bake this household layout into defaults)
- [ ] #3 UDL label/helper match the agreed copy; config.yaml version unchanged
<!-- DOD:END -->
