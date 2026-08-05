---
id: TASK-16
title: Define add-on versioning and release policy
status: in-progress
assignee: []
created_date: '2026-08-05 15:50'
updated_date: '2026-08-05 15:54'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:mechanical'
dependencies: []
documentation:
  - docs/run.md
  - docs/definition-of-done.md
  - docs/acceptance.md
priority: medium
ordinal: 11000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Supervisor treats config.yaml `version` as the add-on release id, but this project has no written rule for when to bump it, how local rebuilds reload Configuration without a fake release, or what CHANGELOG/ship expectations apply. A session already bumped 0.0.1→0.0.3 as a cache-buster and had to revert.
**Goal:** A short written policy (and DoD/run pointers) so agents and humans know when `version` may change, how to force a local UI reload without inventing semver, and how that relates to /ship.
**Why now:** Unblocks safe config polish (TASK-15) and future builds without accidental release trains.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A written policy states when config.yaml version may be bumped vs left alone, including that local Configuration reload must not invent release numbers.
- [ ] #2 docs/run.md (or DoD) tells operators how to rebuild/reload the local add-on so schema/translations refresh without a version bump.
- [ ] #3 Policy notes relationship to /ship (or explicitly defers ship/changelog detail) so agents have a stop/ask line rather than guessing.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: docs/definition-of-done.md and/or docs/run.md and/or a short docs/ note under docs/; optionally docs/acceptance.md Still open.
1. Draft a minimal policy: version bumps only for intentional releasable builds; local Supervisor reload via rebuild/store reload documented in docs/run.md; no silent mid-task bumps.
2. Wire a one-line DoD or AGENTS-facing reminder if appropriate without over-building a full release handbook.
3. Leave CHANGELOG/semver depth proportional to current pre-ship state — prefer explicit "not decided" over inventing 1.0 rules.
Test strategy: how we'll know = docs exist and are cross-linked; no code change required unless a stale version comment remains.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: provisioned
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Version/release policy is written and findable under docs/
- [ ] #2 Local reload without version bump is documented
- [ ] #3 Agents have a clear stop/ask rather than silent semver bumps
<!-- DOD:END -->
