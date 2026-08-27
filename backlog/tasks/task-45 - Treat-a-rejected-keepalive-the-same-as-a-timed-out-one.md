---
id: TASK-45
title: Treat a rejected keepalive the same as a timed-out one
status: in-progress
assignee: []
created_date: '2026-08-27 08:59'
updated_date: '2026-08-27 09:47'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-016'
  - 'adr:ADR-011'
  - 'adr:ADR-018'
dependencies: []
documentation:
  - docs/architecture.md
  - >-
    docs/adrs/adr-016-use-keepalive-failure-and-command-reject-events-for-panel-connection-detection.md
priority: medium
ordinal: 39000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** The app periodically checks that the panel session is still alive by sending a routine health-check command. Today the app only notices trouble if the panel stays silent (a timeout) — if the panel actually answers but refuses the check (a rejection), the app currently treats that as a success. A live incident showed exactly this: the health check kept getting rejected while the TCP connection stayed open, so Home Assistant kept showing the panel as connected even though live monitoring had silently stopped.
**Goal:** A rejected health-check reply is treated exactly like an unanswered one — the connection indicator degrades and the app automatically reconnects and re-syncs, with no manual restart, matching what already happens for a timeout.
**Why now:** Unblocked and next — the architecture doc was just tightened to state this explicitly (ADR-016 already required check-ins to actually succeed, not merely avoid an exception), and this is the one remaining gap between that decision and shipped behaviour.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A NAK'd keepalive reply now degrades Alarm Panel Connection and drives the same keep-trying reconnect + re-sync path as an unanswered keepalive (no manual restart), verified end-to-end against the FakePanel stand-in
- [ ] #2 A unit test proves PanelClient.keepalive() raises a failure when the panel's reply is a NAK instead of the expected datetime payload
- [ ] #3 Existing behaviour for a healthy keepalive and for a timed-out keepalive is unchanged — the full existing test suite stays green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Detail

### Files likely affected

- `texecom_alarm/src/texecom_alarm/protocol/client.py` (modify) — `keepalive()` currently returns `send_command`'s raw payload unchecked. Every sibling read/write command (`get_zone_state`, `get_area_flags`, `set_event_messages`, `set_area_arm`, `set_area_disarm`) already raises `ProtocolError` when the reply is a single-byte NAK or otherwise the wrong shape. Apply the same length-first check to `keepalive()`: the panel's real GETDATETIME reply is a fixed 6-byte payload (see `_handle_getdatetime` in the test double and docs/protocol-reference.md); anything else (in particular a 1-byte NAK) raises `ProtocolError` with a message naming GETDATETIME/NAK, mirroring the existing sibling-method wording style.
- `texecom_alarm/src/texecom_alarm/app.py` (modify) — in `_listen_panel_messages`, the keepalive call site already special-cases `TimeoutError` by re-raising it as `ForcedDisconnect` ("Panel health check went unanswered...") so the outer `except ForcedDisconnect: return` hands control back to `_listen_with_reconnect`'s keep-trying loop. A bare `ProtocolError` from the change above would instead fall into the generic `except Exception:` branch, propagate past that `ForcedDisconnect`-only catch, and break `_listen_with_reconnect` out of its loop entirely — defeating ADR-018's indefinite-retry requirement. Add an explicit `except ProtocolError as exc:` branch alongside the existing `TimeoutError` one that calls `trust.note_keepalive_failed()` and re-raises as `ForcedDisconnect` with an analogous message (e.g. "Panel rejected the keepalive check-in — treating the session as dead and reconnecting."). Keep the existing bare `except Exception:` branch as the fallback for anything else (e.g. `ForcedDisconnect` from injected-garbage/ADR-019 already passes through unchanged above it).
- `texecom_alarm/tests/fake_panel.py` (modify) — add a scenario flag (e.g. `nak_keepalive`) alongside the existing `silence_keepalive` flag so `_handle_getdatetime` can return a 1-byte NAK instead of the normal 6-byte reply, without needing a timeout. Clear it on successful re-LOGIN, mirroring how `silence_keepalive` is already cleared in `_handle_login`.
- `texecom_alarm/tests/test_protocol_client.py` (modify) — unit test alongside the existing `test_keepalive_timeout_exhausted`: `keepalive()` raises `ProtocolError` (not silently succeeding) when the panel replies with a NAK.
- `texecom_alarm/tests/test_reconnect.py` (modify) — end-to-end test mirroring the existing `test_keepalive_timeout_enters_reconnect_path` (same run()/FakePanel/RecordingMqttPublisher harness), but setting the new `nak_keepalive` flag instead of `silence_keepalive`: Connection publishes OFF then recovers to ON with zone/alarm re-synced and no process restart.

### Test strategy

How we'll know = unit test (client-level NAK rejection) + end-to-end test against the FakePanel stand-in (full degrade → reconnect → re-sync cycle), run alongside the existing timeout-path tests to confirm no regression there. Command: `cd texecom_alarm && python -m pytest tests/test_protocol_client.py tests/test_reconnect.py tests/test_app_mqtt.py -q`.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->
