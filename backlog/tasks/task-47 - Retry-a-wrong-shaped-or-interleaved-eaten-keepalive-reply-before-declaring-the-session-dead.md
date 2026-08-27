---
id: TASK-47
title: >-
  Retry a wrong-shaped or interleaved-eaten keepalive reply before declaring the
  session dead
status: awaiting-review
assignee: []
created_date: '2026-08-27 19:35'
updated_date: '2026-08-27 20:46'
labels:
  - 'container:texecom-alarm-app'
  - 'size:M'
  - 'risk:medium'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-016'
  - 'adr:ADR-011'
dependencies: []
documentation:
  - docs/architecture.md
  - docs/protocol-reference.md
priority: high
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** The app treats a single bad routine health-check reply as proof the panel session is dead and immediately tears it down and reconnects. A live incident showed the panel legitimately answers that health check late, or with an empty stand-in reply, for a moment right after a burst of sensor activity - not because anything is actually broken - which turned an earlier fix for a real dead-session case into a same-day string of unnecessary reconnects during ordinary occupancy.
**Goal:** A single odd health-check reply during normal activity no longer forces a reconnect; the app quietly retries the same check a couple of times first, and only treats the session as dead once that retry budget is genuinely exhausted - so the real dead-session case is still caught just as fast as before.
**Why now:** Unblocked and next - the architecture doc was just tightened to require this bounded retry (matching an external reference implementation's documented experience with the same panel protocol), and it is the one remaining gap between that decision and shipped behaviour.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A wrong-shaped or interleaved-M-eaten keepalive reply within the retry budget does not flip Alarm Panel Connection or reconnect the session - verified end-to-end against FakePanel's new transient-burst scenario (mirrors the 2026-08-27 'near miss' cases)
- [ ] #2 Once the retry budget is genuinely exhausted (every attempt still bad, no M traffic), keepalive() still raises and the app still degrades Connection and reconnects - verified end-to-end, preserving TASK-45's zombie-session fix with no regression
- [ ] #3 A unit test proves PanelClient.keepalive() retries the same command/sequence on a wrong-shaped reply before raising, and the full existing test suite stays green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files likely affected:
- texecom_alarm/src/texecom_alarm/protocol/client.py (modify) - keepalive() currently raises ProtocolError immediately on any non-6-byte GETDATETIME reply (added by TASK-45), with zero retry - send_command's existing same-sequence retry loop only fires on TimeoutError, never on a reply that arrives but fails the length check. Give a wrong-shaped reply the same same-sequence retry treatment as a timeout (e.g. a response-validator/predicate passed into send_command's existing attempt loop, or an equivalent local retry wrapper in keepalive()) - same command, same sequence, matching the tightened architecture wording. Raise the effective keepalive retry budget from the current keepalive_retries=1 (2 attempts) to a small bounded number - 3 attempts is documented prior art for this exact panel/protocol (docs/protocol-reference.md Design alternatives) and also covers the interleaved type=M-eats-the-attempt case for free, since that already produces a TimeoutError through the existing per-attempt deadline and already retries via the existing mechanism - only the wrong-length-reply path needs new retry logic. Only after the full budget is exhausted does keepalive() raise ProtocolError / let a TimeoutError propagate, preserving the existing downstream handling in app.py (_listen_panel_messages's except TimeoutError / except ProtocolError blocks convert to ForcedDisconnect unchanged - no app.py change expected).
- texecom_alarm/tests/fake_panel.py (modify) - extend the existing nak_keepalive / silence_keepalive scenario flags (or add new ones) to support: (a) a wrong-shaped reply for only the first N-1 attempts then a normal reply (must NOT disconnect), (b) a wrong-shaped reply for every attempt across the full budget (must still disconnect - preserves the TASK-45 zombie fix), (c) interleaved unsolicited M frames eating one attempt then a normal reply on retry (must NOT disconnect) - mirroring the 2026-08-27 incident's 'near miss' shape.
- texecom_alarm/tests/test_protocol_client.py (modify) - unit tests: keepalive() succeeds after a bounded number of wrong-shaped replies within budget (no exception); keepalive() still raises after the full budget is exhausted with no good reply (zombie case unchanged).
- texecom_alarm/tests/test_reconnect.py (modify) - end-to-end: a transient wrong-shaped-reply burst within budget must NOT flip Alarm Panel Connection or tear down the session; a sustained bad-reply run beyond the budget still enters the existing keep-trying reconnect path (no regression to TASK-45's fix or the mid-run heal path).
- texecom_alarm/CHANGELOG.md (modify) - Fixed entry under [Unreleased] documenting the reconnect-storm fix, referencing the 2026-08-27 incident.

Test strategy: how we'll know = unit test (client-level bounded retry + budget-exhausted-still-fails) + end-to-end test against the FakePanel stand-in (transient-burst no-disconnect + sustained-failure still-disconnects, against the recording MQTT broker harness already used by test_reconnect.py). Command: cd texecom_alarm && python -m pytest tests/test_protocol_client.py tests/test_reconnect.py tests/test_app_mqtt.py -q
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build result
Summary: PanelClient.keepalive() now retries a wrong-shaped keepalive reply (same command/sequence) up to a 3-attempt budget before raising, matching the tightened architecture wording and the 2026-08-27 incident fix.
Changed files: texecom_alarm/src/texecom_alarm/protocol/client.py, texecom_alarm/tests/fake_panel.py, texecom_alarm/tests/test_protocol_client.py, texecom_alarm/tests/test_reconnect.py, texecom_alarm/CHANGELOG.md
Verification: unit test (client-level bounded retry + budget-exhausted-still-fails) + end-to-end test against FakePanel (transient-burst no-disconnect + sustained-failure still-disconnects). Ran cd texecom_alarm && python -m pytest tests/test_protocol_client.py tests/test_reconnect.py tests/test_app_mqtt.py -q -> 68 passed. Full repo suite (pytest -q) -> 348 passed, no regressions. ruff check / ruff format --check clean. pytest --cov=texecom_alarm --cov-fail-under=90 -> 92.61%.
Notes/assumptions: send_command() gained an optional retry_if predicate reusing the existing timeout-retry loop; only keepalive() passes it. Bumped PanelClient.__init__'s keepalive_retries default from 1 to 2 (3 total attempts) per task's documented prior art; this default is also reused by login()'s retry budget (no separate knob existed), raising login's own attempt count from 2 to 3 as a side effect -- no ADR/test constrains login's attempt count separately and all login-focused tests pin keepalive_retries=0 explicitly, so not flagged as a stop condition. Added two new FakePanel scenario controls: wrong_shape_keepalive_replies and eat_keepalive_attempts_with_message, both cleared on successful re-LOGIN mirroring the existing nak_keepalive/silence_keepalive convention. Added a new [Unreleased] section to CHANGELOG.md (none existed previously).

## Build phase
phase: awaiting-review
<!-- SECTION:FINAL_SUMMARY:END -->
