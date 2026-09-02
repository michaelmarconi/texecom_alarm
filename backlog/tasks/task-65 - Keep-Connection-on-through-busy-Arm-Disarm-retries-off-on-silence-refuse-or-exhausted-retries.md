---
id: TASK-65
title: >-
  Keep Connection on through busy Arm/Disarm retries; off on silence, refuse, or
  exhausted retries
status: ready
assignee: []
created_date: '2026-09-02 10:51'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:low'
  - 'parallel:needs-coordination'
  - 'mode:tdd'
  - 'adr:ADR-022'
  - 'adr:ADR-004'
  - 'adr:ADR-015'
  - 'ac:AC4'
  - 'ac:AC3'
dependencies:
  - TASK-64
documentation:
  - >-
    docs/adrs/adr-022-use-one-busy-versus-dead-session-model-including-late-command-replies-for-panel-connection-health.md
  - docs/specs/spec-panel-session-heal.md
priority: high
ordinal: 59000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Today a late Arm or Disarm reply turns Alarm Panel Connection off even when the panel is still sending ordinary updates. The household sees a lost panel for about half a minute; a second tap on the same link then works.
**Goal:** Connection stays on while those busy retries run. It goes off at once if the panel refuses, if the wait is silent, or if the retry budget is used up with no reply. Do not silently send the tap again after failure is declared.
**Why now:** Follows the new-request retry task — ADR-022.

Corrective for TASK-7 (left done; this task is the rework). FakePanel is not proof that a real trigger-then-Disarm flood stays quiet on Connection — that remains live /accept.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Arm or Disarm timeout while events arrive does not turn Connection off if a new-request retry then gets a reply
- [ ] #2 NAK or a silent timeout still turns Connection off immediately and still uses the refused-command countdown, not hello patience
- [ ] #3 Using up the busy-retry budget with no reply turns Connection off; heal does not re-send that failed tap
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom_alarm/src/texecom_alarm/protocol/client.py (modify), texecom_alarm/src/texecom_alarm/panel_trust.py (modify), texecom_alarm/src/texecom_alarm/ (runtime arm/disarm caller — modify), texecom_alarm/tests/test_e2e_fake_panel.py (modify), texecom_alarm/tests/test_panel_trust.py (modify), texecom_alarm/tests/fake_panel.py (modify). 1. Do not record command failure / Connection off on the first busy timeout. 2. NAK and silent timeout still record failure immediately and start the refused-command fail window (not hello patience). 3. Exhausted busy retries without ACK then record failure the same way. 4. FakePanel: flood unsolicited events so the first sequence gets no ACK; second sequence ACKs; Connection stays on. 5. Separate cases: silent timeout offs immediately; NAK offs immediately. Test strategy: how we'll know = hermetic e2e against FakePanel; command: cd texecom_alarm && python -m pytest tests/test_e2e_fake_panel.py tests/test_panel_trust.py -q. Do not claim CI proves a real Premier Elite siren flood.
<!-- SECTION:PLAN:END -->
