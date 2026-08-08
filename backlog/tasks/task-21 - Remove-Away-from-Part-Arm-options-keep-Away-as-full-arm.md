---
id: TASK-21
title: Remove Away from Part-Arm options; keep Away as full arm
status: ready
assignee: []
created_date: '2026-08-08 09:52'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-008'
  - 'adr:ADR-003'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-008-use-confirmed-shared-arm-disarm-with-away-full-arm-and-home-night-part-arm-mapping.md
  - docs/specs/spec-alarm-control.md
priority: high
ordinal: 16000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Shipped Part-Arm configuration (TASK-1, TASK-11, TASK-15, TASK-17) and arm mapping (TASK-7) still let installers assign Away to a Part-Arm slot. That contradicts ADR-008 and already caused a live false-disarmed incident when Away occupied a slot instead of full arm.
**Goal:** Part-Arm options are Home / Night / Unused only; Away always arms with the panel full-arm mode; any persisted Away slot value migrates to Unused with a clear warning.
**Why now:** Architecture and AGENTS now forbid Away on Part-Arm; this is the corrective rework for the conflicting-done Part-Arm/Away tasks.

Corrective for TASK-1 / TASK-7 / TASK-11 / TASK-15 / TASK-17.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 part_arm_1/2/3 schema and Supervisor helpers offer Home, Night, and Unused only — Away is absent
- [ ] #2 ARM_AWAY always uses full-arm mode byte 0; assigning Away on a Part-Arm slot is impossible after load (legacy Away coerces to Unused with a warning)
- [ ] #3 Home and Night still map to configured Part-Arm slots; unit tests cover remapping and reject Away as a Part-Arm label
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

Files likely affected: config.yaml (modify), translations/en.yaml (modify), DOCS.md (modify), texecom-alarm-app/src/texecom_alarm/config.py (modify), texecom-alarm-app/src/texecom_alarm/arm_commands.py (modify — comment/ADR cite only if needed), texecom-alarm-app/tests/test_config.py (modify), texecom-alarm-app/tests/test_arm_commands.py (modify), docs/run.md (modify if migration/refresh notes needed).

1. Change schema list tokens for part_arm_1/2/3 to Home/Night/Unused only (keep Title Case + emoji display form already used); drop Away from radios.
2. Update translations helpers so they no longer offer Away as a Part-Arm choice.
3. In Settings: reject or coerce legacy Away on a slot to unused with an explicit warning; mode_byte_for_ha_mode("away") must always return full-arm byte 0 and must never resolve Away from a Part-Arm slot; ha_mode_for_part_arm_slot must not return away.
4. Fix unit tests that still assign part_arm_*=away or assert Away as a Part-Arm label; keep coverage that ARM_AWAY → mode byte 0 and Home/Night still use configured slots.
5. Align DOCS.md (and run notes if any) with Away excluded from Part-Arm options.

Test strategy: how we'll know = unit tests for schema/Settings parse + arm mode-byte selection (stand-in: FakePanel where arm tests already use it); command: cd texecom-alarm-app && python -m pytest tests/test_config.py tests/test_arm_commands.py -q. Live Configuration radios Home/Night/Unused only is accept/smoke after rebuild — not CI.
<!-- SECTION:PLAN:END -->
