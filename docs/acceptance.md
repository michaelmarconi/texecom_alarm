# Acceptance

**Date:** 2026-09-01
**State:** Accepted ✅
<!-- State is exactly one of: Draft 📝 | Accepted ✅ | Deferred ⏸️ -->

## What we set out to build

A Home Assistant add-on that replaces the prior MQTT bridge for a Texecom Premier Elite panel: zone sensors and an alarm control panel over MQTT, including a working Home arm mode. Ready-to-arm switches let the household block Away, Home, or Night without encoding their rules in the add-on; a refused arm must not set the panel, and the Home Assistant card must snap back to the real state.

## Scorecard

| # | Scenario | Result | Notes |
|---|----------|--------|-------|
| 1 | Replacement still live | ✅ pass | Add-on started after local rebuild; panel keepalives and zone MQTT flowing |
| 2 | Ready-to-arm switches | ✅ pass | Away, Home, Night present |
| 3 | Refused arm snaps back | ✅ pass | Away refused; card snapped back; logs showed blocked then MQTT arming |
| 4 | Disarm still works | ✅ pass | Disarm not gated by ready switches |
| 5 | Simplified config panel | ✅ pass | Reconnect settings collapsed to one; two labels rewritten in plain language during the walk |
| 6 | Rejected keepalive heals like a timeout | ✅ pass | Verified via merged automated end-to-end test; live corroboration skipped this round (practitioner's call) |
| 7 | Transient keepalive hiccup no longer forces an unnecessary reconnect | ✅ pass | Verified via merged automated end-to-end test (executor + independent review re-run + checkpoint verifier); live corroboration skipped (practitioner's call — not reliably triggerable on demand) |
| 8 | Busy-versus-dead while the phone app arms | ✅ pass | Sim add-on 0.3.0 on the local module saw iOS arm → Away → disarm; Connection stayed up. Household HA card still to walk |

## Scenario: Replacement still live

**Status:** Pass ✅

- **What we're proving:** The replacement is the live panel in Home Assistant — zones, alarm, connection healthy; old MQTT bridge gone.
- **Examples:** Given the add-on is running with the prior MQTT bridge uninstalled, When Home Assistant is up, Then in-use zone entities and the alarm control panel are present and Alarm Panel Connection is on.
- **You:** Open Home Assistant, find the Texecom Alarm device, confirm zones look like the house, the alarm entity is there, Connection is on, and the old MQTT bridge is not installed.
- **I check:** Add-on `started`; panel keepalives and zone MQTT still flowing.
- **How we know:** Pass if the house view looks right and Connection is on. Fail if zones are missing, Connection is off, or the old bridge is still in use.
- **Result:** pass — practitioner confirmed the live view; add-on had been rebuilt and was publishing zone updates.

## Scenario: Ready-to-arm switches

**Status:** Pass ✅

- **What we're proving:** Away, Home, and Night each have a ready-to-arm switch, and they start on so arming still works until someone turns one off.
- **Examples:** Given a fresh install or restart, When Home Assistant has received discovery, Then three ready-to-arm controls exist and each starts on.
- **You:** Find Ready to arm Away, Home, and Night; confirm they exist and are on (unless turned off on purpose).
- **I check:** Discovery names match those three switches.
- **How we know:** Pass if all three are there. Fail if a switch is missing.
- **Result:** pass — practitioner confirmed all three switches.

## Scenario: Refused arm snaps back

**Status:** Pass ✅

- **What we're proving:** If a mode is not ready, that arm never hits the panel; the alarm card briefly shows Arming then the real state; Home Assistant can see the mode was blocked, not why.
- **Examples:** Given Ready to arm Away (or Home/Night) is off, When that arm is tapped on the alarm card, Then the panel stays as it was and the card returns to that state after a brief Arming.
- **You:** Turn the matching ready switch off, tap that mode, watch the card snap back, confirm the panel did not arm, check Blocked arm named the mode only.
- **I check:** Add-on logs for blocked command and MQTT `arming`.
- **How we know:** Pass if the card snaps back and the panel stays put. Fail if the card stays on the tapped mode or the panel arms.
- **Result:** pass — practitioner confirmed snap-back; logs showed `alarm_command_blocked mode=away` then MQTT `arming`.

## Scenario: Disarm still works

**Status:** Pass ✅

- **What we're proving:** Ready switches never block Disarm. Turning a switch off while already armed does not disarm.
- **Examples:** Given every ready switch is off, When Disarm is requested, Then the panel still disarms. Given the house is already armed, When a ready switch is turned off, Then the panel stays armed.
- **You:** With a ready switch off, tap Disarm; confirm switch-off did not disarm an armed house.
- **I check:** Disarm is not gated on the ready switches.
- **How we know:** Pass if Disarm still works and switch-off did not disarm. Fail if Disarm is refused because a ready switch is off.
- **Result:** pass — practitioner confirmed Disarm still works.

## Scenario: Simplified config panel (connection-simplification wave)

**Status:** Pass ✅

- **What we're proving:** The connection-simplification wave (ADR-016–019) actually simplified what the household sees — one reconnect-wait setting instead of four, with plain-language labels and no jargon or units baked into titles.
- **Examples:** Given an install still holding the four retired reconnect settings in its options, When the add-on is rebuilt from current source, Then the Configuration tab shows only Reconnection delay, Force reconnect after, and Recheck interval as the tunable knobs, with no attempts/normal/trigger fields left.
- **You:** Opened the Texecom Alarm Configuration tab and reviewed the settings and their descriptions.
- **I check:** Confirmed `config.yaml`'s schema declares only the three settings; cleaned stale option keys via the Supervisor API since a rebuild alone doesn't strip them; rewrote two labels (`trust_fail_window_seconds` → "Force reconnect after", `reconciliation_poll_interval_seconds` → "Recheck interval") that still read as jargon, moving units/defaults into their descriptions.
- **How we know:** Pass if only the new settings show with clear plain-language labels. Fail if old settings persist or wording still reads as jargon.
- **Result:** pass — practitioner confirmed the panel reads clearly after the label rewrite ("Much better, accepted").

## Scenario: Rejected keepalive heals like a timeout

**Status:** Pass ✅

- **What we're proving:** A panel check-in the panel answers but rejects (NAK) is treated as a dead session, same as one it never answers at all — no zombie session that looks live while monitoring is actually frozen (`spec-panel-session-heal` AC1).
- **Examples:** Given monitoring was live, When the panel NAKs a routine keepalive instead of returning datetime, Then Alarm Panel Connection goes off, the app keeps retrying, and Connection returns live with zone/alarm state re-synced once the panel accepts again — same path as an unanswered keepalive, without a manual restart.
- **You:** Reviewed the fix and its test coverage; chose to accept on merged evidence rather than wait for a live reproduction.
- **I check:** `test_keepalive_nak_enters_reconnect_path` (end-to-end, FakePanel NAK'd keepalive) and `test_keepalive_nak_raises_protocol_error` (unit) both green in the merged suite; TASK-46 checkpoint independently re-verified the same before this walk.
- **How we know:** Pass if a NAK'd keepalive drives the same `ForcedDisconnect` → reconnect → re-sync path as a timeout. Fail if a NAK is silently treated as a healthy check-in (the original incident).
- **Result:** pass — this AC's spec `how we'll know` is already automated end-to-end (live corroboration is called out as optional). Real household panel wasn't configured this session (`panel_host` empty), so no live NAK reproduction was attempted; the merged test evidence plus the TASK-46 checkpoint stand in, same as the 26 Aug round left the general live-reconnect check to the merged suites.

## Scenario: Transient keepalive hiccup no longer forces an unnecessary reconnect

**Status:** Pass ✅

- **What we're proving:** A single odd routine keepalive reply right after a burst of sensor activity no longer tears down and reconnects the panel session — the app quietly retries the same check a couple of times first — while a genuinely dead session (every attempt still bad) is still caught and reconnected just as fast as before (no regression to the prior NAK-heals-like-a-timeout fix).
- **Examples:** Given the panel answers `GETDATETIME` with a short/wrong-shaped reply (or the reply is eaten by an interleaved zone-event push) shortly after zone activity, When that happens within the retry budget, Then the app retries the same command/sequence and Alarm Panel Connection never flips off. Given every attempt in the budget still comes back bad, When the budget is exhausted, Then Alarm Panel Connection degrades and the app reconnects and re-syncs, same as an unanswered keepalive.
- **You:** Reviewed the fix, the review findings (and how the one flagged item — a shared retry-count setting also nudging `login()`'s own attempt count — was explicitly decided rather than silently shipped), and the test coverage; chose to accept on merged evidence rather than reconfigure for a live PIR-timed reproduction.
- **I check:** `test_keepalive_wrong_shape_transient_burst_does_not_flip_connection` (transient burst within budget → `Connection` never goes off) and `test_keepalive_wrong_shape_sustained_failure_still_reconnects` (budget exhausted → still reconnects, no `TASK-45` regression) both green in the merged suite; TASK-48 checkpoint independently re-verified the same before this walk.
- **How we know:** Pass if a within-budget bad reply never flips Connection, and a budget-exhausted run still reconnects. Fail if either a harmless hiccup forces a reconnect, or a real dead session goes undetected.
- **Result:** pass — this scenario's `how we'll know` is automated end-to-end only (no manual reproduction step); the real household panel wasn't reachable from this session (a precisely PIR-timed keepalive collision against live hardware "isn't reliably triggerable on demand anyway" — same call as the 27 Aug entry above), so the merged test evidence plus the TASK-48 checkpoint stand in.

## Scenario: Busy-versus-dead while the phone app arms

**Status:** Pass ✅

- **What we're proving:** Alarm Panel Connection means we cannot talk to the panel — not that the panel is busy with another client’s arm or disarm. Zone and alarm entities stay visible.
- **Examples:** Given this add-on holds the dedicated local module, When the Texecom iOS app arms and then disarms, Then MQTT follows arming → armed Away → disarmed, check-ins keep succeeding, and Connection does not go off.
- **You:** Armed and disarmed from the Texecom iOS app (household HA was stopped so this sim could hold the local module). Confirmed this is not the household-card walk.
- **I check:** Add-on logs on `local_texecom_alarm` 0.3.0 (`panel_host=192.168.1.51`).
- **How we know:** Pass if live AREA events publish the right alarm states and the session stays up. Fail if Connection goes off, the session drops, or alarm MQTT never follows the phone app.
- **Result:** pass — 10:26:07 remote command then MQTT `arming`; 10:26:16 full arm MQTT `armed_away`; 10:26:51 remote command then MQTT `disarmed`. Keepalives continued. No hang-up, reconnect, or decode miss. Zones then followed the walk back upstairs. Not a substitute for watching the card on household Home Assistant.

## How it went

- Home Assistant was already up; the add-on had just been rebuilt from the UI and was started.
- This walk focused on the live replacement plus the new ready-to-arm refuse snap-back — not a repeat of the 21 Aug Home/siren walks.
- Refused Away from the alarm card snapped back; add-on logs matched (blocked, then MQTT arming).
- We did not re-walk Night ×3, every sensor class, TRACE log hunting, the household alarm wrapper, a crash-free month, or a second household install — those stayed accepted limitations from 21 Aug.
- HomeKit/iOS refuse (button still offered when the matching ready switch is off; that mode still must not arm) cannot be walked until this add-on is on household Home Assistant.
- 26 Aug: re-entered accept to cover the connection-simplification wave (ADR-016–019, TASK-39–44), which landed after the 24 Aug walk and changed the config panel. Walked the config panel live against the real household panel (`local_texecom_alarm`, `panel_host=192.168.1.51`); the live-reconnect scenario (physically interrupting the panel connection to watch Alarm Panel Connection recover) was deliberately left to the merged tasks' test suites rather than walked live this round.
- 27 Aug: re-entered accept to cover the keepalive-NAK reconnect fix (TASK-45/46) that closed out a real household incident (a rejected `GETDATETIME` was miscounted as a healthy check-in, freezing motion detection behind an "ON" connection signal). Booted the sim (`local_texecom_alarm` started, `panel_host` empty this session — no `TEXECOM_PANEL_HOST` set), then accepted on the merged automated evidence rather than reconfiguring for a live NAK reproduction, which isn't reliably triggerable on demand anyway.
- 27 Aug (later): re-entered accept again to cover the keepalive-retry-budget fix (TASK-47/48) — a same-day follow-up incident where the TASK-45/46 NAK fix over-corrected into a reconnect storm on ordinary PIR bursts. Rebuilt and started `local_texecom_alarm` (0.2.0 → 0.2.1, `panel_host` still empty this session), confirmed it starts clean and only refuses to run for the expected missing-panel-target reason, then accepted on the merged automated evidence (executor + independent review re-run + checkpoint verifier) rather than a live reproduction, for the same reason as the entry above.
- 1 Sep: re-entered accept after the busy-versus-dead session wave. Booted sim HA (`local_texecom_alarm` 0.3.0 on the live local module). Coming-home / ordinary-arm from the household HA card could not be walked — those apps were stopped so this sim could hold the panel’s only slot, and the card the household uses is not this sim. Practitioner armed and disarmed from the Texecom iOS app instead: this add-on stayed up and published `arming` → `armed_away` → `disarmed` with Connection still on. **Still need to check live household Home Assistant** (card state, Connection name, coming home via garage) once this release is installed there.

## Still open

- [x] HomeKit/iOS refuse when a ready switch is off — cannot walk until this add-on is on household HA (limitation accepted)
- [x] Household HA card walk (coming home, ordinary arm, Connection name) — still required once this release is on household HA; not walked 1 Sep because household HA was stopped (limitation accepted for closing this record)

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-24 | Issues found | 1 |
| 2 | 2026-08-24 | Clear | — |
| 3 | 2026-08-27 | Clear | — |
