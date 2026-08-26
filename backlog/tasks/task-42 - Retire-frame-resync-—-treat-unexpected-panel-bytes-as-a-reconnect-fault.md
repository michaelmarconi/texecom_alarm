---
id: TASK-42
title: Retire frame-resync — treat unexpected panel bytes as a reconnect fault
status: in-progress
assignee: []
created_date: '2026-08-26 17:19'
updated_date: '2026-08-26 17:28'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-019'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-019-use-a-single-reconnect-interval-and-no-line-noise-defense-for-panel-disconnects.md
priority: medium
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** If a stray, garbled, or unexpected byte shows up on the connection to the panel, the app currently just shrugs it off and keeps listening, quietly noting it at the most detailed log level.
**Goal:** The app now treats that stray byte as a sign the connection needs to be re-established — it ends the session and reconnects fresh, the same way it already does when the panel deliberately hangs up. This matches the household's decision that the app no longer defends against noise on the wire in code — the dedicated network module is what prevents that noise, not this app.
**Why now:** ADR-019 requires this; it's a self-contained cleanup with no dependency on the other reconnect task.

Corrective for TASK-2 and TASK-19, whose accepted work (frame-resync skip path and its quiet-logging behaviour) is exactly what ADR-019 retires.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Injecting non-protocol bytes into a FakePanel session raises ForcedDisconnect and ends the session instead of being silently skipped
- [ ] #2 No log line anywhere reports a byte-skip/resync event, at any log level
- [ ] #3 The steady-state listen loop's existing ForcedDisconnect handling reconnects normally after this fault, with no new exception-handling path added
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files affected: texecom_alarm/src/texecom_alarm/protocol/client.py (modify), texecom_alarm/src/texecom_alarm/protocol/frame.py (modify — docstring/comment only, no behaviour change), texecom_alarm/tests/fake_panel.py (modify), texecom_alarm/tests/test_protocol_client.py (modify), texecom_alarm/tests/test_diagnostics_logging.py (modify).

1. In client.py's _recv_frame, when try_decode_frame returns a non-frame result for reasons other than the '+++' marker (which already raises ForcedDisconnect), raise ForcedDisconnect there too instead of incrementing the skip counter and continuing. This reuses the app's one established 'session is dead, reconnect' signal (already used for the +++ marker, an unanswered health-check, and a stuck-trust window expiry) so _listen_panel_messages's existing `except ForcedDisconnect: return` handles it with no new catch site needed anywhere — raising the separate ProtocolError class here instead would NOT be caught by the steady-state listen loop and would crash the app, violating ADR-004.
2. Remove the skip/hex-log machinery (skipped, skipped_bytes, the 'panel_resync skipped %s bytes' TRACE line) since nothing is skipped anymore.
3. Update frame.py's module docstring and try_decode_frame docstring to drop the 'so callers can discard exactly one byte and resync (ADR-002)' framing — cite ADR-019 instead; no functional change to try_decode_frame itself.
4. fake_panel.py: repurpose or remove resync_survivals (it counted successful skips; there's nothing left to count) — keep the existing garbage-injection helper as the trigger for the new fault-based test.
5. test_protocol_client.py: replace test_resync_skips_injected_garbage_without_closing with a test asserting the injected junk now raises ForcedDisconnect (ends the session) rather than surviving it.
6. test_diagnostics_logging.py: remove the AC3/AC6 assertions that unexpected bytes stay quiet at WARNING-DEBUG and log a compact TRACE notice — that AC no longer applies (already marked retired in spec-diagnostics-logging.md).

Test strategy: how we'll know = unit + integration against FakePanel (stand-in); `cd texecom_alarm && python -m pytest tests/test_protocol_client.py tests/test_diagnostics_logging.py -q` — asserts injected garbage now faults the session and triggers reconnect, and that no resync-skip log line is emitted anywhere.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: provisioned
<!-- SECTION:FINAL_SUMMARY:END -->
