---
id: TASK-2
title: 'Protocol client: framing, CRC, login, resync'
status: in-progress
assignee: []
created_date: '2026-08-04 12:51'
updated_date: '2026-08-04 13:37'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-002'
  - 'adr:ADR-001'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-002-use-frame-resync-and-asymmetric-reconnect-for-panel-protocol-collisions.md
  - docs/protocol-reference.md
priority: medium
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** Nothing in the package yet speaks the panel's binary session — framing, checksums, login, and surviving junk bytes on the wire are still unimplemented.
**Goal:** An asyncio protocol client can open a session against a FakePanel, log in, keep the session alive with a safe read-only probe, and skip past non-protocol bytes without tearing down.
**Why now:** Unblocked and next — zone enumeration and every later panel path sit on this client.

Asyncio is the chosen runtime for TCP and later MQTT.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 FakePanel login completes successfully and yields an authenticated session in tests
- [ ] #2 Injected non-protocol bytes are skipped via frame resync without closing the session
- [ ] #3 Idle keepalive sends a safe read-only command and retries once on short timeout with the same sequence number
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected: texecom-alarm-app/src/texecom_alarm/protocol/__init__.py (create), texecom-alarm-app/src/texecom_alarm/protocol/crc.py (create), texecom-alarm-app/src/texecom_alarm/protocol/frame.py (create), texecom-alarm-app/src/texecom_alarm/protocol/client.py (create), texecom-alarm-app/tests/fake_panel.py (create), texecom-alarm-app/tests/test_protocol_frame.py (create), texecom-alarm-app/tests/test_protocol_client.py (create), texecom-alarm-app/tests/test_e2e_fake_panel.py (modify), texecom-alarm-app/pyproject.toml (modify — pytest-asyncio if needed).
1. Implement Connect-protocol frame encode/decode and CRC-8 per docs/protocol-reference.md / spike findings.
2. Asyncio TCP client: connect, wait ≥500ms, LOGIN with injected UDL password, sequence handling.
3. Frame resync: on unexpected bytes, scan forward for the next valid header — never treat as fatal (ADR-002).
4. Idle keepalive via GETDATETIME (or equivalent safe read-only) with same-sequence retry on short timeout.
5. Expand FakePanel into an asyncio test double that speaks enough framing for login + keepalive + garbage injection.
Test strategy: TDD unit tests for CRC/framing; async client tests against FakePanel for login success, resync-after-garbage, and keepalive retry — never the live household panel.
<!-- SECTION:PLAN:END -->
