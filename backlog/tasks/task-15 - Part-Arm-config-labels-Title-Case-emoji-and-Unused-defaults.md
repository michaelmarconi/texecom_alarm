---
id: TASK-15
title: Part-Arm config labels Title Case + emoji and Unused defaults
status: ready
assignee: []
created_date: '2026-08-05 15:43'
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

**Background:** Part-Arm slot options already map each slot to an HA arm mode, but the Supervisor Configuration radios show lowercase `home`/`night`/`away`, the helper copy is hard to parse, and schema defaults still bake this household's Night/Home layout.
**Goal:** Configuration radios match the agreed mock — Title Case labels with emoji after each mode (`Home 🏠`, `Night 🌙`, `Away 🔒`, `Unused`), simple helper text, and all three slots defaulting to Unused.
**Why now:** Practitioner Hold on checkpoint TASK-13 until this polish lands; do not Approve that gate first.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Radio labels render as Home 🏠 / Night 🌙 / Away 🔒 / Unused (emoji after label); each slot helper matches: Which HA arm button (Home / Night / Away) this Part-Arm slot should use — or Unused if the slot isn't configured on your panel.
- [ ] #2 Schema and Settings defaults for part_arm_1, part_arm_2, and part_arm_3 are all unused (not household Night/Home).
- [ ] #3 Add-on version bumped so Supervisor reloads Configuration; unit tests and DOCS.md reflect Unused defaults; remapping still changes cmd=6 mode bytes without code edits.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: config.yaml, translations/en.yaml, DOCS.md, texecom-alarm-app/src/texecom_alarm/config.py, texecom-alarm-app/tests/test_config.py (and any tests assuming Night/Home defaults).
1. Change schema/options defaults for part_arm_1/2/3 to unused; keep list values as home|night|away|unused for the backend.
2. Update Supervisor translations (and list option display strings if required) so radios show `Home 🏠` / `Night 🌙` / `Away 🔒` / `Unused` with emoji after the label; helper: "Which HA arm button (Home / Night / Away) this Part-Arm slot should use — or Unused if the slot isn't configured on your panel."
3. Align Python DEFAULT_PART_ARM_* and docs; bump add-on version so Supervisor reloads the Configuration form.
Test strategy: how we'll know = unit tests for Unused defaults + remapping still works; pytest test_config (and related) green; ruff clean. No live panel required.
<!-- SECTION:PLAN:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Part-Arm radios match the agreed mock (Title Case, emoji after label, simple helper)
- [ ] #2 Defaults are Unused for all three slots (ADR-005: do not bake this household layout into defaults)
- [ ] #3 Add-on version bumped; tests and DOCS updated for defaults
<!-- DOD:END -->
