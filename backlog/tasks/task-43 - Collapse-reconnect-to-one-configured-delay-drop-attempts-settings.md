---
id: TASK-43
title: Collapse reconnect to one configured delay; drop attempts settings
status: in-progress
assignee: []
created_date: '2026-08-26 17:19'
updated_date: '2026-08-26 17:29'
labels:
  - 'container:texecom-alarm-app'
  - 'size:L'
  - 'risk:low'
  - 'parallel:safe'
  - 'mode:tdd'
  - 'adr:ADR-018'
  - 'adr:ADR-019'
dependencies: []
documentation:
  - >-
    docs/adrs/adr-018-use-interval-only-reconnect-budgets-for-panel-disconnects.md
  - >-
    docs/adrs/adr-019-use-a-single-reconnect-interval-and-no-line-noise-defense-for-panel-disconnects.md
priority: medium
ordinal: 37000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
### Overview

**Background:** When the panel connection drops, the app waits and tries again — but today there are four separate settings doing this: two 'how many tries' counters that don't actually do anything (the app always keeps trying forever regardless), and two separate wait times depending on whether the drop followed a real alarm trigger.
**Goal:** One setting — "Reconnection delay" (reconnect_delay_seconds, default 5 seconds) — used every time, no matter why the connection dropped. The two dead 'how many tries' settings disappear from the Configuration panel entirely. The app still retries forever if the panel stays unreachable — that guarantee doesn't change.
**Why now:** ADR-018 (drop the attempts settings) and ADR-019 (merge the two intervals) both land here; doing them together avoids reworking the same files twice.

Corrective for TASK-9, whose accepted work (the four reconnect settings and the normal/trigger profile split) is exactly what ADR-018 and ADR-019 retire.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Settings/config.yaml/translations expose exactly one reconnect-wait setting (reconnect_delay_seconds, default 5), with the four old attempts/interval settings fully removed from all three
- [ ] #2 reconnect_after_disconnect uses the same configured delay for every disconnect regardless of the last decoded alarm payload, with no ReconnectProfile/normal-vs-trigger selection left in the code
- [ ] #3 The reconnect loop still retries a dropped panel connection indefinitely (no attempt-count cap reintroduced), matching ADR-004/ADR-011/ADR-018
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Files affected: texecom_alarm/src/texecom_alarm/config.py (modify), texecom_alarm/config.yaml (modify), texecom_alarm/translations/en.yaml (modify), texecom_alarm/src/texecom_alarm/reconnect.py (modify), texecom_alarm/src/texecom_alarm/app.py (modify — one-line change), texecom_alarm/tests/test_reconnect.py (modify), texecom_alarm/tests/test_config.py (modify), texecom_alarm/tests/test_e2e_fake_panel.py (modify), texecom_alarm/DOCS.md (modify).

1. config.py: remove reconnect_normal_attempts, reconnect_trigger_attempts, reconnect_normal_interval_seconds, reconnect_trigger_interval_seconds (dataclass fields + _ENV_KEYS mappings + _optional_int/_optional_float parsing calls); add reconnect_delay_seconds: float = 5.0 with its own env mapping (TEXECOM_RECONNECT_DELAY_SECONDS) parsed the same way as the existing optional-float settings.
2. config.yaml: remove the four old keys from both the options defaults block and the schema block; add reconnect_delay_seconds: 5 (default) and reconnect_delay_seconds: float(0,) (schema).
3. translations/en.yaml: remove the four old name/description entries (reconnect_normal_attempts, reconnect_normal_interval_seconds, reconnect_trigger_attempts, reconnect_trigger_interval_seconds); add one entry for reconnect_delay_seconds — name 'Reconnection delay', description stating it's the wait before retrying after any panel disconnect, in seconds, default 5.
4. reconnect.py: remove the ReconnectProfile dataclass, select_reconnect_profile function, and the last_alarm_payload parameter on reconnect_after_disconnect; the retry loop sleeps settings.reconnect_delay_seconds between attempts and keeps retrying indefinitely (ADR-004/ADR-011/ADR-018 unaffected — only interval selection collapses, not the indefinite-retry guarantee). Reword the info/debug log lines to drop 'profile'/'budget' language (just log the delay and attempt count).
5. app.py: drop the last_alarm_payload=last_alarm_payload keyword argument from the one call site to reconnect_after_disconnect. last_alarm_payload itself stays tracked and used for the unrelated trigger-snapshot feature (maybe_publish_trigger_snapshot) — nothing else there changes.
6. test_reconnect.py: replace the normal/trigger profile-selection tests with a single-delay test (reconnect always uses settings.reconnect_delay_seconds regardless of last alarm state).
7. test_config.py: replace the four old settings' tests (defaults + env overrides) with one for reconnect_delay_seconds (default 5.0, env override).
8. test_e2e_fake_panel.py: use the single setting in test fixture setup; drop any dual-profile assertions.
9. DOCS.md: replace the 'Reconnect behaviour' table's four rows with one row for 'Reconnection delay' (default 5s) and reword the prose to drop the normal/trigger distinction — the app reconnects using the same wait interval no matter what caused the disconnect.

Test strategy: how we'll know = unit + config tests; `cd texecom_alarm && python -m pytest tests/test_reconnect.py tests/test_config.py tests/test_e2e_fake_panel.py -q` — asserts the four old settings are gone from Settings/config.yaml/translations, the new reconnect_delay_seconds defaults to 5.0 and is env-overridable, and reconnect timing no longer depends on the last alarm payload.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Build phase
phase: executing
<!-- SECTION:FINAL_SUMMARY:END -->
