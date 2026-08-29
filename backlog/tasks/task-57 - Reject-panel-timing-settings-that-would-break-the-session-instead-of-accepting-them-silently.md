---
id: TASK-57
title: >-
  Reject panel timing settings that would break the session instead of accepting
  them silently
status: in-progress
assignee: []
created_date: '2026-08-29 11:01'
updated_date: '2026-08-29 11:12'
labels:
  - 'container:texecom-alarm-app'
  - 'size:S'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-017'
  - 'adr:ADR-019'
  - 'adr:ADR-020'
dependencies: []
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** The new check-in dials and the reconnect wait are all validated as merely "zero or more", in both the loader and the add-on schema. That accepts several values that quietly break the add-on:

- A check-in interval above the panel's observed ~60s tolerance for a connection it has not heard from (protocol-reference.md). A household setting 120s - a plausible reaction to the unresolved audible-pips question - gets a permanent drop-and-reconnect loop with nothing in the log pointing at the setting they changed. Today a 120s interval happens to be refused only as a side effect of the default 45s patience being smaller; raise patience too and any interval passes.
- A check-in interval of zero, which makes the listen loop send check-ins as fast as the panel can answer.
- A patience period of zero, which makes the very first refusal end the session - defeating the entire point of the patience window.
- A reconnect wait of zero, which is exactly the value live capture recorded as refused three times out of three, because the panel needs roughly two seconds to free its single connection slot.

**Goal:** Each of these is refused at startup with a message naming the setting and the real panel behaviour behind the limit, so a household gets an actionable error instead of a silently broken alarm integration.

**Why now:** These dials were only just exposed to households in the ADR-020 wave, so nobody has had a chance to misconfigure them yet. The ceiling is the important one: ADR-020 requires the cadence stay comfortably shorter than the panel's tolerance, and nothing enforces that.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A check-in interval that is not comfortably under the panel's ~60s idle tolerance is refused at startup with a message naming the setting and why the limit exists
- [ ] #2 A zero check-in interval, a zero patience period, and a zero reconnect wait are each refused with their own clear operator-facing message
- [ ] #3 The add-on schema advertises the same bounds as the loader enforces, so the Supervisor UI rejects bad values too
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 The shipped defaults (15s interval, 45s patience, 5s reconnect wait) all still load unchanged
- [ ] #2 Reconnection still retries indefinitely with no attempt cap (ADR-018)
<!-- DOD:END -->
