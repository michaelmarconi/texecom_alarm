---
id: TASK-41
title: 'Checkpoint: texecom-alarm-app panel-connection-simplification wave'
status: done
assignee: []
created_date: '2026-08-25 15:27'
updated_date: '2026-08-25 21:52'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-39
  - TASK-40
ordinal: 35000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All tests pass (pytest exits 0)
- [x] #2 Build/lint clean
- [x] #3 FakePanel end-to-end suite (test_e2e_fake_panel.py, test_panel_trust.py) still green
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- AC1 (all tests pass): pass — pytest tests -q in texecom_alarm/ → 346 passed in 14.53s, exit code 0.
- AC2 (build/lint clean): pass — ruff check . → All checks passed! (exit 0); ruff format --check . → 46 files already formatted (exit 0).
- AC3 (FakePanel e2e suite green): pass — pytest tests/test_e2e_fake_panel.py tests/test_panel_trust.py -q → 41 passed in 4.98s, exit code 0.
- DoD 1 (no unavailable-marking on panel-link degrade): pass — panel_trust.py only calls publish_panel_link_state (a retained MQTT topic), never entity availability; availability is governed solely by the app-level MQTT Last-Will in app.py, fully decoupled from panel-link state.
- DoD 2 (ADR-011 fail-window mechanism unchanged): pass — diffed TASK-39 (8ac0c34) and TASK-40 (a22393b) against panel_trust.py; needs_session_relogin(), _command_failure_cleared(), _mark_degraded(), RECOVER_WINDOW_SECONDS, and STUCK_TRUST_FAIL_WINDOW_SECONDS are byte-for-byte unchanged — only what feeds degrade/recover changed.
- DoD 3 (architecture.md matches shipped behavior): pass — docs/architecture.md's ADR-016/017 description (connectivity via keepalive/disconnect + command-reject/timeout only; poll never feeds Connection; poll interval configurable, default 300s) matches shipped code in panel_trust.py and config.py.
Notes: TASK-39/40 both confirmed merged on main; a related follow-up commit (panel-traffic-driven recovery, c5ca23d) was also found merged and does not affect the fail-window mechanism.

## Build phase
phase: done
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 Neither task marks the alarm or any zone entity unavailable due to a panel-link issue (ADR-004)
- [x] #2 The ADR-011 mid-run heal path (TASK-27/TASK-28) is unchanged in behavior
- [x] #3 docs/architecture.md's ADR-016/017 description matches the shipped behavior
<!-- DOD:END -->
