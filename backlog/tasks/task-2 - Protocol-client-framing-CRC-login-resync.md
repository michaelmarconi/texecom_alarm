---
id: TASK-2
title: 'Protocol client: framing, CRC, login, resync'
status: done
assignee: []
created_date: '2026-08-04 12:51'
updated_date: '2026-08-04 13:52'
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
- [x] #1 FakePanel login completes successfully and yields an authenticated session in tests
- [x] #2 Injected non-protocol bytes are skipped via frame resync without closing the session
- [x] #3 Idle keepalive sends a safe read-only command and retries once on short timeout with the same sequence number
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

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: Asyncio Connect-protocol client with CRC-8 framing, login, ADR-002 resync, and GETDATETIME keepalive retry — verified against FakePanel.
Changed files: texecom-alarm-app/src/texecom_alarm/protocol/__init__.py, texecom-alarm-app/src/texecom_alarm/protocol/crc.py, texecom-alarm-app/src/texecom_alarm/protocol/frame.py, texecom-alarm-app/src/texecom_alarm/protocol/client.py, texecom-alarm-app/tests/fake_panel.py, texecom-alarm-app/tests/test_protocol_frame.py, texecom-alarm-app/tests/test_protocol_client.py, texecom-alarm-app/tests/test_e2e_fake_panel.py, texecom-alarm-app/pyproject.toml
Verification: `uv run pytest --cov=texecom_alarm --cov-fail-under=90` → 27 passed, 97% coverage; `ruff check` + `ruff format --check` → clean; `bandit -r src` → clean
Notes/assumptions: Production defaults are `login_delay=0.5` and `response_timeout=2.0`; tests inject shorter values. Keepalive uses exactly one same-sequence retry (`keepalive_retries=1`). CRC-8 matches SPIKE-001 (`poly=0x185` / working `0x85`, init `0xff`). Never targeted the live panel. Left `uv.lock` untracked (not in task scope).

## Build phase
phase: done
<!-- SECTION:FINAL_SUMMARY:END -->
