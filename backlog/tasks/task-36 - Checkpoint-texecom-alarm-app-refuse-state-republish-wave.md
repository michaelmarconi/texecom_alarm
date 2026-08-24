---
id: TASK-36
title: 'Checkpoint: texecom-alarm-app refuse-state-republish wave'
status: awaiting-review
assignee: []
created_date: '2026-08-24 13:33'
updated_date: '2026-08-24 15:13'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-35
ordinal: 30000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (pytest in texecom_alarm/ exits 0)
- [ ] #2 Build clean (ruff check and ruff format --check in texecom_alarm/ exit 0)
- [ ] #3 Wave end-to-end path still green: FakePanel refuse cases skip the panel, re-publish current alarm state, and emit the blocked-arm event
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- All tests pass: pass — pytest in texecom_alarm/: 337 passed, exit 0
- Build clean: pass — ruff check All checks passed; ruff format --check 46 files already formatted
- Wave e2e refuse path: pass — FakePanel refuse: no arm command; last alarm payload equals pre-command; new publish after refuse; blocked-arm event names mode only
- ADR-015 refuse contract: pass — matching switch off does not call set_area_arm; HA payload unchanged
- Re-publish matches NAK pattern: pass — refuse uses get_current_alarm_state + publish_alarm_state (retained), same as panel NAK; tests require a new publish of the same payload

Notes: Named refuse suite green; skip-panel, unchanged payload, NAK-style retained re-publish.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Refuse still does not send the arm to the panel and does not change the Home Assistant payload (ADR-015)
- [ ] #2 Re-publish on refuse matches architecture: same current state, new MQTT publish, same pattern as a panel NAK
<!-- DOD:END -->
