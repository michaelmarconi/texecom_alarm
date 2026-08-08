---
id: TASK-23
title: 'Checkpoint: texecom-alarm-app Away-full-arm and connectivity rename wave'
status: in-progress
assignee: []
created_date: '2026-08-08 09:52'
updated_date: '2026-08-08 10:07'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-21
  - TASK-22
ordinal: 18000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pytest green for config, arm_commands, mqtt discovery, and e2e FakePanel suites touched by this wave
- [ ] #2 Part-Arm schema/tests prove Away is not a Part-Arm option and ARM_AWAY uses full-arm mode byte 0
- [ ] #3 Connectivity discovery tests assert friendly name Alarm Panel Connected
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 ADR-008 Away-full-arm / Home-Night-Unused Part-Arm constraints are not violated by TASK-21
- [ ] #2 ADR-004 connectivity-vs-availability separation is unchanged by TASK-22
- [ ] #3 Live Configuration radios and HA connectivity name match after rebuild/rediscovery when walked
<!-- DOD:END -->
