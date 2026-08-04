---
id: DRAFT-2
title: Publish alarm_control_panel discovery and live arm state
status: Draft
assignee: []
created_date: '2026-08-04 12:52'
labels:
  - 'container:texecom-alarm-app'
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Expose the alarm entity over MQTT discovery and keep its state aligned with panel area/log events, re-syncing the real armed/disarmed/triggered state on startup rather than assuming disarmed.
<!-- SECTION:DESCRIPTION:END -->
