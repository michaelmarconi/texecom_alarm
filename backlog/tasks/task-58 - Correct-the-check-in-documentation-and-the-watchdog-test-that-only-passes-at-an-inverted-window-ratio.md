---
id: TASK-58
title: >-
  Correct the check-in documentation and the watchdog test that only passes at
  an inverted window ratio
status: ready
assignee: []
created_date: '2026-08-29 11:01'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-011'
  - 'adr:ADR-016'
  - 'adr:ADR-020'
dependencies: []
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Reviews of the ADR-020 wave found three places where what is written no longer matches what the code does.

- The add-on's own documentation contradicts itself thirteen lines apart: one paragraph still lists a failed keepalive check-in as something that turns Alarm Panel Connection off, which ADR-020 made false, while the next section correctly explains that a refusal inside the patience window changes nothing.
- The architecture document describes the patience mechanism as measuring time since the last *successful* check-in. The code measures from the *start of the current failure streak*, which is what ADR-020 actually specifies. The two differ by a whole check-in interval in when a session is declared dead.
- The test asserting the command-rejection watchdog is independent of the check-in patience window configures a 10s fail window against the helper's default 30s recover window - the inverse of the shipped 90s against 30s. The whole test therefore runs inside the recover window, where the recovery path short-circuits before it can interfere. It proves independence only in a regime that never occurs in production, and its name and docstring claim considerably more than it establishes.

**Goal:** The documentation says what the code does, and the test either exercises the shipped window ratio or is renamed and re-scoped to claim only what it actually proves.

**Why now:** The misleading test is the reason a real gap in the command-rejection watchdog shipped green through review. Whatever is decided about that gap separately, the test should not be able to hide it again.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The add-on documentation no longer contradicts itself about what a failed check-in does to Alarm Panel Connection
- [ ] #2 The architecture document describes the patience clock the code actually implements - measured from the start of the failure streak, not from the last success
- [ ] #3 The watchdog-independence test either runs at the shipped window ratio or is renamed and re-scoped so it no longer claims coverage it does not have
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 No behavioural change to the check-in or watchdog code in this task - documentation and tests only
- [ ] #2 Shipping code and tests cite behaviour in product language, not pipeline task IDs
<!-- DOD:END -->
