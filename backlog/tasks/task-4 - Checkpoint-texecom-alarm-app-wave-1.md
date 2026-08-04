---
id: TASK-4
title: 'Checkpoint: texecom-alarm-app wave 1'
status: done
assignee: []
created_date: '2026-08-04 12:52'
updated_date: '2026-08-04 15:20'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-1
  - TASK-2
  - TASK-3
ordinal: 4000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All tests pass (pytest in texecom-alarm-app/ exits 0), including FakePanel + Mosquitto (Docker) E2E — never live panel or household broker
- [x] #2 Build and lint clean (pip install -e ".[dev]", ruff check, ruff format --check)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- #1 All tests pass (pytest, FakePanel + Mosquitto E2E): pass — `pytest --cov=texecom_alarm --cov-fail-under=90` in `texecom-alarm-app/` exited 0: 70 passed (incl. `tests/test_e2e_fake_panel.py` FakePanel + Docker Mosquitto); coverage 96.15% (≥90%)
- #2 Build and lint clean: pass — `pip install -e ".[dev]"` ok; `ruff check .` “All checks passed!”; `ruff format --check .` “24 files already formatted”
Notes: Human-review DoD items (#1–#3) not assessed; one RuntimeWarning in FakePanel E2E (unawaited coroutine) did not fail the suite.

## Build phase
phase: done
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 Unused zones are not published; discovery is MQTT-only (ADR-001, ADR-003)
- [x] #2 Frame resync does not fatal on garbage bytes (ADR-002); entity availability uses app LWT not panel-link (ADR-004)
- [x] #3 Part-Arm mapping remains install-time config fields, not hardcoded household layout (ADR-005)
<!-- DOD:END -->
