# Acceptance

**Date:** 2026-08-05
**State:** Draft 📝
<!-- State is exactly one of: Draft 📝 | Accepted ✅ | Deferred ⏸️ -->

## What we set out to build

A Home Assistant Add-on that replaces unreliable `the prior MQTT bridge` for a Texecom Premier Elite panel: MQTT-discovered zone binary sensors and a full three-mode `alarm_control_panel` (including Home), live panel sync, panel-link health separate from app liveness, and a last-trigger snapshot — without embedding household automation rules.

## Scorecard

| # | Scenario | Result | Notes |
|---|----------|--------|-------|
| 1 | Zone inventory | ✅ pass | 40 zones + Arm Status; names match house |
| 2 | Zone open/clear (live) | ⚠️ partial | PIR pass (~2–6s); door/window/other/shock not walked |
| 3 | Arm Home (live) | ❌ fail | Command path OK; panel NAK; state stayed disarmed |
| 4 | HA aggregates / wrapper / HomeKit path | 🚫 blocked | Local HA only; household config not walked |
| 5 | Away / Night ×3, disarm matrix, trigger+outage, cutover | 🚫 blocked | Not walked tonight |

## Scenario: Zone inventory

**Status:** Pass ✅

- **What we're proving:** With `the prior MQTT bridge` not in this path, in-use zones appear in HA with correct panel names/types.
- **Examples:** Given the new add-on is running against the live panel; When HA MQTT discovery is connected; Then ~35+ in-use zone entities are present with recognisable names.
- **You:** Confirmed the Entities list under MQTT — names match the house (doors, PIRs, windows, shocks, garage).
- **I check:** Broker had 40 zone discovery configs + states; HA registry showed 40 MQTT zone sensors + alarm panel; add-on `online`, alarm `disarmed`.
- **How we know:** Pass if inventory looks complete and names match reality.
- **Result:** pass — 40 zones + Arm Status; practitioner confirmed the list looks right. Entity IDs landed as short names (e.g. `binary_sensor.front_door`) rather than a `texecom_…` prefix (see Still open).

## Scenario: Zone open/clear (live)

**Status:** Partial ⚠️

- **What we're proving:** Physical trigger/clear updates HA promptly (~2s) for representative sensor classes.
- **Examples:** Given a PIR (and ideally door/window/other); When opened/activated then cleared; Then the matching entity flips within ~2 seconds.
- **You:** Moved around briefly at night; shock skipped (would wake household); door/window/other not fully exercised.
- **I check:** Timestamped MQTT watch captured PIR transitions only.
- **How we know:** Pass per class exercised; partial if only some classes done.
- **Result:** partial — PIR pass (MICHAEL STDY PIR, FF HALLWAY PIR, GF HALLWAY PIR; on→off within ~2–6s). Door / window / other / shock not walked tonight.

## Scenario: Arm Home (live)

**Status:** Fail ❌

- **What we're proving:** Arm home transitions the panel/HA to armed_home without crashing the integration.
- **Examples:** Given disarmed; When Arm home is selected in HA; Then command reaches the panel and state becomes armed_home (or a clear failure).
- **You:** Selected Home on the Arm Status card; UI stayed on Home visually while status remained Disarmed.
- **I check:** MQTT received `ARM_HOME`; add-on called `SETAREAARM` with configured Home mode byte `2`; panel returned **NAK**; state stayed `disarmed`; add-on remained `online` (no crash).
- **How we know:** Pass if armed_home without crash; fail if no arm / crash.
- **Result:** fail — command path works (HA → MQTT → app → panel); panel NAK’d. Open zones (15/16/18/29 on at the time) are one hypothesis, not confirmed — practitioner doubts windows alone explain it. Root cause open. Also: HA card left Home selected despite Disarmed state (see Still open).

## Scenario: HA aggregates / wrapper / HomeKit path

**Status:** Blocked 🚫

- **What we're proving:** Household automations and `house_alarm_panel` keep working against new entities.
- **Examples:** Given household wrapper entities point at the new MQTT alarm/zones; When the panel arms or a zone changes; Then aggregates and HomeKit stay in sync.
- **You:** Not attempted — this accept used local Supervisor HA + local Mosquitto, not the household config layer.
- **I check:** Not attempted.
- **How we know:** Pass if wrapper/HomeKit track the new entities without breakage.
- **Result:** blocked — not walked (local HA only).

## Scenario: Away / Night ×3, disarm matrix, trigger+outage, cutover

**Status:** Blocked 🚫

- **What we're proving:** Remaining alarm-control and independence acceptance criteria from the specs.
- **Examples:** Arm Away and Night repeatedly; disarm from each armed state; live siren trigger with forced disconnect and snapshot; full uninstall cutover from `the prior MQTT bridge`.
- **You:** Not attempted tonight (household asleep; trigger/outage disruptive; cutover is a separate environment).
- **I check:** Not attempted.
- **How we know:** Pass if each path completes without crash and states match the panel.
- **Result:** blocked — not walked tonight.

## How it went

- 🚀 Booted via `/run` (Supervisor + HA); installed local Mosquitto; configured Texecom Alarm to the live panel (`192.168.1.183:10001`, UDL `1234`) and local MQTT.
- 🔌 Practitioner added the MQTT integration in HA.
- ✅ Zone inventory looked correct (40 zones + Arm Status).
- 🚶 Short live PIR walk proved open/clear publishing (~2–6s).
- ❌ Home arm from HA reached the panel but was NAK’d — no crash, no state change.
- 🌙 Stopped further live arm/zone testing for the night; product/UX gaps listed under Still open rather than fixed mid-walk.

## Still open

- [ ] **Panel-link connectivity entity missing on the broker** — code path exists (`texecom_alarm_panel_link` / `texecom/panel_link/state`) but no discovery or state retained on Mosquitto during the walk; not visible in HA. Investigate publish path.
- [x] **Part-Arm Configuration radio labels** — TASK-17: schema radios `Home 🏠` / `Night 🌙` / `Away 🔒` / `Unused`; short helpers only. Hard-refresh Configuration to confirm live UI.
- [ ] **Entity ID collision risk** — entities appeared as `binary_sensor.front_door` etc.; want a Texecom-scoped prefix/scheme (HA uses underscores, not dotted subdomains).
- [ ] **Friendly-name casing** — panel names published in CAPS (`FRONT DOOR`); decide normalisation (sentence case vs capitalise first word, etc.).
- [ ] **No Device** — MQTT entities ungrouped (Device column empty); discuss discovery `device` block.
- [ ] **Alarm entity naming** — “Arm Status” / `alarm_control_panel.arm_status` feel wrong; pick better name + entity_id.
- [ ] **Arm-mode control order** — HA card showed Home, Away, Night, Disarmed; prefer Home, Night, Away, Disarmed if the MQTT platform allows.
- [x] **Home arm NAK root cause** — TASK-14: classified as **panel reject** (app sent configured Home mode byte; framing/mapping OK). Why the panel NAKd still needs daytime corroboration (open zones not assumed).
- [x] **HA alarm card feedback on failed arm** — TASK-14: on arm NAK, republish live last-known alarm state (retained) so HA does not keep a stuck mode selection.
- [x] **UDL option clarity** — “Panel UDL password” + usual-1234 helper landed in TASK-15 (default remains `1234` in options).
- [ ] **Unwalked acceptance paths** — door/window/other zone classes; Away/Night ×3; disarm matrix; live siren + forced disconnect + snapshot; household wrapper/aggregates; production cutover with `the prior MQTT bridge` removed.
- [ ] **Published release / CHANGELOG / `/ship` cadence** — local no-fake-bump rule is in [addon-versioning.md](addon-versioning.md); when to authorize a real `version` bump and CHANGELOG depth for go-live remains deferred until `/ship` (or an explicit decision).

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-05 | Clear | — |
| 2 | 2026-08-05 | Issues found | 2 |
| 3 | 2026-08-05 | Clear | — |
