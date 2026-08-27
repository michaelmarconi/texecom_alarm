---
id: TASK-46
title: 'Checkpoint: texecom-alarm-app keepalive-nak-detection wave'
status: awaiting-review
assignee: []
created_date: '2026-08-27 08:59'
updated_date: '2026-08-27 09:59'
labels:
  - 'container:texecom-alarm-app'
  - 'type:checkpoint'
dependencies:
  - TASK-45
ordinal: 40000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All tests pass (cd texecom_alarm && python -m pytest -q exits 0)
- [ ] #2 Build/lint clean (pre-commit / ruff / mypy as configured exit 0)
- [ ] #3 Reconnect end-to-end suite covers both the existing keepalive-timeout case and the new keepalive-NAK case, both green
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Verification result
verdict: pass
- All tests pass: pass - cd texecom_alarm && python3 -m pytest -q -> 343 passed in 14.34s, exit 0
- Build/lint clean: pass - python3 -m ruff check . -> All checks passed! (exit 0); python3 -m ruff format --check . -> 46 files already formatted (exit 0)
- Reconnect end-to-end suite covers both cases, both green: pass - python3 -m pytest tests/test_reconnect.py -q -k keepalive -> 2 passed, 10 deselected, matching test_keepalive_timeout_enters_reconnect_path (test_reconnect.py:501) and the new test_keepalive_nak_enters_reconnect_path (test_reconnect.py:573); unit coverage also confirmed via test_keepalive_timeout_exhausted and test_keepalive_nak_raises_protocol_error in test_protocol_client.py:110/:119

Notes: DoD spot-checked - PanelClient.keepalive() (client.py:187-204) now raises ProtocolError naming GETDATETIME/NAK on a non-6-byte reply, matching architecture.md's Idle keepalive and Panel-connection detection wording (ADR-016); the except ProtocolError block is purely additive between the pre-existing except TimeoutError (ADR-011 timeout heal path, unchanged) and the fallback except Exception.
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Rejected-keepalive handling matches docs/architecture.md § Idle keepalive and § Panel-connection detection (ADR-016)
- [ ] #2 ADR-011 mid-run session heal path for the existing timeout case is unchanged
<!-- DOD:END -->
