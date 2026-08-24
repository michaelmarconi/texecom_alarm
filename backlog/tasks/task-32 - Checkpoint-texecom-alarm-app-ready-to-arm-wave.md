---
id: TASK-32
title: 'Checkpoint: texecom-alarm-app ready-to-arm wave'
status: awaiting-review
assignee: []
created_date: '2026-08-23 18:37'
updated_date: '2026-08-24 09:46'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-30
  - TASK-31
ordinal: 26000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Ready-to-arm suites pass (cd texecom-alarm-app && python -m pytest tests/test_mqtt_discovery.py tests/test_arm_commands.py tests/test_app_mqtt.py tests/test_e2e_fake_panel.py -q exits 0)
- [ ] #2 FakePanel: matching switch off means no arm command, unchanged alarm MQTT state, and a blocked-arm event naming the mode; disarm still reaches the panel
- [ ] #3 Build/import clean for texecom_alarm package (python -c 'import texecom_alarm' from app env / pytest collection succeeds)
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- Ready-to-arm suites pass: pass — `.venv/bin/python -m pytest tests/test_mqtt_discovery.py tests/test_arm_commands.py tests/test_app_mqtt.py tests/test_e2e_fake_panel.py -q` → 93 passed in 4.04s, exit 0
- FakePanel refuse + disarm: pass — `test_e2e_unready_arm_skips_panel_and_publishes_blocked_event` (away/home/night: `panel.last_arm_mode` unchanged, alarm MQTT payloads unchanged, blocked event `event_type` == mode, no reason); `test_e2e_disarm_still_sent_when_all_ready_switches_off` (`panel.disarm_calls` increments). Same behaviour in `test_unready_arm_does_not_call_panel_or_change_alarm_state` / `test_disarm_ignores_ready_flags`
- Build/import clean: pass — `.venv/bin/python -c 'import texecom_alarm'` exit 0; pytest collected and ran 93 tests
- DoD: three switches start on; refuse encodes no household rules: pass — `publish_ready_to_arm_discovery` publishes away/home/night with `on=True`; `_ReadyToArmState` defaults all True; blocked payload is `{"event_type": mode}` only (`test_publish_ready_to_arm_discovery_retained_starts_on`, `test_publish_blocked_arm_event_not_retained_mode_only`, `test_e2e_ready_to_arm_switches_start_on_and_round_trip`)
- DoD: disarm never gated; switch-off while armed does not disarm: pass — DISARM in `handle_alarm_command` calls `set_area_disarm()` before any ready check; `_handle_ready_command` only updates flags/MQTT; proven by `test_e2e_disarm_still_sent_when_all_ready_switches_off` and `test_e2e_ready_switch_off_while_armed_does_not_disarm` (`disarm_calls` unchanged, `last_arm_mode` still 0)
- DoD: Away full arm; Home/Night install-time Part-Arm: pass — `Settings.mode_byte_for_ha_mode`: away → `FULL_ARM_AWAY_MODE_BYTE` (0); home/night → configured slots; Away on a Part-Arm option coerced to unused; `test_remapped_part_arm_slots_change_mode_bytes` (ARM_AWAY→0, ARM_HOME→1, ARM_NIGHT→3)
Notes: All AC and DoD items evidenced from existing TASK-30/31 tests plus a brief code read; no product or ledger edits.

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Three ready-to-arm switches start on; refuse does not encode household rules (ADR-015, ADR-003)
- [ ] #2 Disarm is never gated; turning a switch off while already armed does not disarm (ADR-015)
- [ ] #3 Away remains full arm; Home/Night remain install-time Part-Arm mapping (ADR-008)
<!-- DOD:END -->
