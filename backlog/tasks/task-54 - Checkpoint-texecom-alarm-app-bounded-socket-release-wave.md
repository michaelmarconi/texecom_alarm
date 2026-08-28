---
id: TASK-54
title: 'Checkpoint: texecom-alarm-app bounded-socket-release wave'
status: done
assignee: []
created_date: '2026-08-28 16:14'
updated_date: '2026-08-28 16:33'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-53
ordinal: 48000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 All tests pass (pytest exits 0)
- [x] #2 Lint/format clean (ruff check and ruff format --check exit 0)
- [x] #3 A transport that never completes wait_closed() is still released within the bounded time and the app successfully reconnects afterward
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- AC1 tests pass: pass — .venv/bin/python -m pytest -q -> 350 passed in 17.23s, exit 0.
- AC2 lint/format clean: pass — ruff check src tests -> All checks passed!; ruff format --check src tests -> 46 files already formatted.
- AC3 hanging-writer bounded release + reconnect proof: pass — test_close_bounds_wait_and_aborts_transport_when_wait_closed_hangs (texecom_alarm/tests/test_protocol_client.py:514) uses a wait_closed() that awaits an Event that never fires, asserts writer.close_calls == 1, transport.abort_calls == 1, and elapsed < 3.0. test_reconnect_always_awaits_close_before_next_connect_attempt (texecom_alarm/tests/test_reconnect.py:305) proves close_done precedes connect_start via event ordering with an injected delay. Both re-ran individually: 2 passed in 2.15s.
- DoD1 bound not an install-time setting: pass — _CLOSE_TIMEOUT_SECONDS = 2.0 is a module constant (protocol/client.py:46), short vs DEFAULT_RECONNECT_DELAY_SECONDS = 5.0 (config.py:26); absent from Settings dataclass and env-var mapping.
- DoD2 close always awaited before next connect: pass — reconnect.py:79 awaits close() then sleeper(delay) then connect() at reconnect.py:86 inside the same loop; app.py startup retry closes (app.py:345) before looping back to connect() (app.py:321) on failure. No code path skips the await.
Notes: All 350 tests pass, ruff clean, both bounded-close/ordering behaviors backed by genuine non-tautological tests plus source inspection.

## Build phase
phase: done
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 The bound is short relative to the reconnect interval, not itself a new install-time setting unless the practitioner asked for one
- [x] #2 No path exists where reconnect is attempted before the previous socket's release (bounded or forced) has completed
<!-- DOD:END -->
