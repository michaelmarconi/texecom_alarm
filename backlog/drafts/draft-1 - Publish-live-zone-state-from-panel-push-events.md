---
id: DRAFT-1
title: Publish live zone state from panel push events
status: Draft
assignee: []
created_date: '2026-08-04 12:52'
labels:
  - 'container:texecom-alarm-app'
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After discovery, subscribe to panel zone pushes and publish MQTT state updates within the latency budget, including re-syncing current zone state on startup so entities do not default incorrectly.
<!-- SECTION:DESCRIPTION:END -->
