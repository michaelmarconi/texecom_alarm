---
id: TASK-17
title: 'Part-Arm Configuration radios: Title Case + emoji labels'
status: in-progress
assignee: []
created_date: '2026-08-05 19:09'
updated_date: '2026-08-05 19:11'
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
  - docs/run.md
  - docs/addon-versioning.md
  - DOCS.md
priority: high
ordinal: 12000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** TASK-15 closed with Part-Arm radios still showing lowercase `home`/`night`/`away`/`unused`. Bugbot had forced schema list tokens back to lowercase because Supervisor `vol.In` matches persisted options exactly — and for add-on `list(...)`, those tokens **are** the radio labels (no separate label/value). Emoji/Title Case were left only in helpers, so AC #1 was marked done without a live Configuration match. Practitioner Hold on checkpoint TASK-13 until radios match the agreed mock.
**Goal:** Configuration radios show `Home 🏠` / `Night 🌙` / `Away 🔒` / `Unused` (emoji after the word); slot helpers are only: Which HA arm button (Home / Night / Away) this Part-Arm slot should use — or Unused if the slot isn't configured on your panel. Drop the "Stored values are home / night…" sentence. Python already canonicalises Title Case + emoji to `home|night|away|unused` for cmd=6 mapping.
**Why now:** Gate review rediscovered the gap; do not Approve TASK-13 until this lands. Do **not** bump `config.yaml` `version` (see docs/addon-versioning.md / docs/run.md).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Live Supervisor Configuration radios for part_arm_1/2/3 show Home 🏠 / Night 🌙 / Away 🔒 / Unused (emoji after label), not lowercase tokens
- [ ] #2 Each slot helper is only: Which HA arm button (Home / Night / Away) this Part-Arm slot should use — or Unused if the slot isn't configured on your panel — with no stored-values/schema sentence
- [ ] #3 Settings still map selections to canonical home|night|away|unused for arm commands; config.yaml version is not bumped; tests and DOCS.md match the display schema
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: config.yaml (modify), translations/en.yaml (modify), DOCS.md (modify), texecom-alarm-app/tests/test_config.py (modify); optionally migrate notes in docs/run.md. 1. Change schema to `list(Home 🏠|Night 🌙|Away 🔒|Unused)` and options defaults to `Unused` for part_arm_1/2/3. 2. Simplify translations helpers (no stored-values / schema-lowercase sentence). 3. Replace the test that forbids Title Case in schema with assertions that schema uses display tokens and that Settings still normalize both forms; migrate any persisted lowercase options on the local install when refreshing (ha store reload + rebuild/update per docs/run.md). 4. Verify on a live Configuration tab after refresh — radio labels must match, not helpers alone. Do **not** bump version.
Test strategy: how we'll know = pytest test_config (+ related) green; ruff clean; live HA Configuration radios show Title Case + emoji after store reload + rebuild/update.
<!-- SECTION:PLAN:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Live Configuration radios match the agreed mock (Title Case + emoji after label)
- [ ] #2 Helpers match the short wording only; no fake version bump
- [ ] #3 Canonical arm mapping unchanged; verified via tests + live UI after refresh per docs/run.md
<!-- DOD:END -->
