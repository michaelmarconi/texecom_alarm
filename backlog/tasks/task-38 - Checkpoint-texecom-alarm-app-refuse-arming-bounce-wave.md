---
id: TASK-38
title: 'Checkpoint: texecom-alarm-app refuse-arming-bounce wave'
status: done
assignee: []
created_date: '2026-08-24 16:10'
updated_date: '2026-08-24 16:59'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-37
documentation:
  - docs/specs/spec-ready-to-arm.md
  - docs/architecture.md
ordinal: 32000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All tests pass (pytest in texecom_alarm/ exits 0)
- [x] #2 Build clean (ruff check and ruff format --check in texecom_alarm/ exit 0)
- [x] #3 Wave end-to-end FakePanel refuse path: no panel arm; MQTT arming then pre-command payload; blocked-arm event names mode only
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- All tests pass: pass — pytest -q in texecom_alarm/ exited 0 (338 passed in 15.22s)
- Build clean: pass — ruff check and ruff format --check exited 0 (46 files already formatted)
- Wave e2e FakePanel refuse path: pass — AC3 suite 67 passed; handle_alarm_command skips set_area_arm when ready is off, MQTT is arming then current, blocked event is event_type only; DISARM is handled before the ready gate; switch-off-while-armed tests do not disarm
Notes: ADR-015 and architecture bounce (arming then current, not duplicate-only) hold in source and FakePanel e2e.

## Build phase
phase: done
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 ADR-015: refuse does not send the arm to the panel; disarm is not gated; switch-off while armed does not disarm
- [x] #2 Architecture: refuse publishes MQTT arming then current alarm state (not a duplicate-only republish)
<!-- DOD:END -->
