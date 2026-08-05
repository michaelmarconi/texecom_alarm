# Acceptance

**Date:** 2026-08-05
**State:** Draft 📝
<!-- State is exactly one of: Draft 📝 | Accepted ✅ | Deferred ⏸️ -->

## What we set out to build

A Home Assistant Add-on that replaces unreliable `the prior MQTT bridge` for a Texecom Premier Elite panel: MQTT-discovered zone binary sensors and a full three-mode `alarm_control_panel` (including Home), live panel sync, panel-link health separate from app liveness, and a last-trigger snapshot — without embedding household automation rules.

## Scorecard

| # | Scenario | Result | Notes |
|---|----------|--------|-------|
| 1 | Fix-forward discovery / inventory | ✅ pass | After HA DB+registry wipe: 42 MQTT entities on device, prefixed IDs, Title Case, Panel Link ON |
| 2 | Zone open/clear (live) | ⚠️ partial | Earlier PIR pass (~2–6s); door/window/other/shock still not walked |
| 3 | Arm Home from HA (live) | ⚠️ partial | Succeeded once (`armed_home`); later attempts NAK’d (zones clear); ACK timeout on success path |
| 4 | Disarm from HA (live) | ❌ fail | `SETAREADISARM NAK` ×2; UI did nothing |
| 5 | External / Texecom App state sync | ❌ fail | App/keypad-path changes left MQTT stale while Panel Link stayed ON |
| 6 | Texecom iOS App coexistence (spot check) | ⚠️ partial | Idle+command cycle: add-on survived; app Home→Disarm not reflected in MQTT; brief app spinners |
| 7 | HA aggregates / wrapper / HomeKit path | 🚫 blocked | Local HA only; household config not walked |
| 8 | Away / Night ×3, disarm matrix, trigger+outage, cutover | 🚫 blocked | Not walked |

## Scenario: Fix-forward discovery / inventory

**Status:** Pass ✅

- **What we're proving:** TASK-10–12 discovery (prefixed IDs, device block, Title Case, Panel Link, alarm naming) shows correctly in HA after a clean rediscovery.
- **Examples:** Given a wiped entity/device registry + DB; When the add-on republishes discovery; Then zones/alarm/panel-link sit under MQTT device Texecom Alarm with `texecom_alarm_*` entity IDs.
- **You:** Confirmed device nesting, Front Door naming, Panel Link connected; noted more-info arm order Home→Away→Night (HA frontend-fixed).
- **I check:** Registry 42/42 on device with unique_ids; broker discovery matched; unique-id UI banner contradicted by registry (false alarm).
- **How we know:** Pass if HA matches broker/registry after clean rediscovery.
- **Result:** pass — required wiping HA DB **and** entity/device registries (DB alone left orphaned short IDs). IDE restart needed full Supervisor bounce. More-info arm button order cannot be set via MQTT `supported_features` list order.

## Scenario: Zone open/clear (live)

**Status:** Partial ⚠️

- **What we're proving:** Physical trigger/clear updates HA promptly (~2s) for representative sensor classes.
- **Examples:** Given a PIR (and ideally door/window/other); When opened/activated then cleared; Then the matching entity flips within ~2 seconds.
- **You:** Earlier evening: brief PIR walk; shock skipped; door/window/other not fully exercised. Not re-walked after rediscovery.
- **I check:** Earlier MQTT watch captured PIR on→off within ~2–6s.
- **How we know:** Pass per class exercised; partial if only some classes done.
- **Result:** partial — PIR only (prior walk). Other classes still open.

## Scenario: Arm Home from HA (live)

**Status:** Partial ⚠️

- **What we're proving:** Arm home transitions the panel/HA to armed_home without crashing the integration.
- **Examples:** Given disarmed; When Arm home is selected in HA; Then command reaches the panel and state becomes armed_home (or a clear failure).
- **You:** One successful Home arm (HA showed Armed Home). Later attempts: Home highlighted but status stayed Disarmed.
- **I check:** Success path published `armed_home` but logged `TimeoutError` awaiting SETAREAARM ACK (add-on stayed up). Later: `alarm_command_arm_rejected` (NAK) twice with **no open zones** on broker; state stayed `disarmed`; Panel Link ON.
- **How we know:** Pass if armed_home without crash; fail if no arm / crash; partial if intermittent.
- **Result:** partial — works sometimes; intermittent panel NAK and ACK-timeout-on-success. Root cause open (not explained by open zones alone). Piping noise from panel noted around failures.

## Scenario: Disarm from HA (live)

**Status:** Fail ❌

- **What we're proving:** Disarm from HA clears an armed panel (and cancels exit) via the shared disarm command.
- **Examples:** Given armed_home; When Disarm in HA; Then panel and MQTT become disarmed.
- **You:** Disarm from HA did nothing; had to clear via Texecom iOS App.
- **I check:** `SETAREADISARM NAK` at 23:21:05 and 23:21:35; MQTT remained `armed_home` until add-on restart + area snapshot republished `disarmed`.
- **How we know:** Pass if disarmed without crash; fail if NAK / no state change.
- **Result:** fail — command reached panel, panel rejected; no usable HA disarm tonight.

## Scenario: External / Texecom App state sync

**Status:** Fail ❌

- **What we're proving:** Panel arm/disarm originating outside this add-on (app, keypad) still updates MQTT while Panel Link is ON.
- **Examples:** Given add-on online; When panel state changes via Texecom App or keypad; Then `texecom/alarm/state` follows.
- **You:** Disarmed via Texecom App after failed HA disarm — app showed disarmed, HA stayed Armed Home. Later app Part-Arm Home then Disarm while add-on watched.
- **I check:** After App disarm, retained MQTT stayed `armed_home` with Panel Link ON (stale while claiming live). App Home→Disarm cycle: add-on survived; MQTT never left `disarmed` (no `armed_home` publish). Keypad-disarm-after-HA-Home test aborted — HA Home NAK’d.
- **How we know:** Pass if external changes appear on MQTT promptly; fail if Panel Link ON but state stale.
- **Result:** fail — survive ≠ sync. ADR-007 snapshot on restart did repair state once ComIP was free.

## Scenario: Texecom iOS App coexistence (spot check)

**Status:** Partial ⚠️

- **What we're proving:** Official iOS app and this add-on can both be used without destroying each other’s session or correctness.
- **Examples:** Given add-on holds ComIP; When app is opened / used for arm-disarm; Then add-on stays connected and states stay correct (or we learn which hypothesis fails).
- **You:** Opened app (brief spinners, then OK); Part-Armed Home then Disarmed; noted reams of “Remote Access Started” in app calendar; killed app earlier when ComIP login failed.
- **I check:** Idle+command: our session stayed `online` / Panel Link ON (against pure “app steals ComIP” for this run). Second TCP to `:10001` hung with no data while we held the slot (single-client confirmed). App-originated arm not on MQTT. Tailscale off required for reliable LAN path (known confounder).
- **How we know:** Pass if both work with correct state; partial if survive-only; fail if mutual destruction.
- **Result:** partial — coexistence for survival looks plausible on cloud-path app use; correctness and Remote Access log spam unresolved. App does not need ComIP for normal cloud use; optional Local Connection would contend; cloud remote ops can still disturb ComIP (SPIKE-002) even without holding the TCP slot.

## Scenario: HA aggregates / wrapper / HomeKit path

**Status:** Blocked 🚫

- **What we're proving:** Household automations and `house_alarm_panel` keep working against new entities.
- **Examples:** Given household wrapper entities point at the new MQTT alarm/zones; When the panel arms or a zone changes; Then aggregates and HomeKit stay in sync.
- **You:** Not attempted — local Supervisor HA + local Mosquitto only.
- **I check:** Not attempted.
- **How we know:** Pass if wrapper/HomeKit track the new entities without breakage.
- **Result:** blocked — not walked.

## Scenario: Away / Night ×3, disarm matrix, trigger+outage, cutover

**Status:** Blocked 🚫

- **What we're proving:** Remaining alarm-control and independence acceptance criteria from the specs.
- **Examples:** Arm Away and Night repeatedly; disarm from each armed state; live siren trigger with forced disconnect and snapshot; full uninstall cutover from `the prior MQTT bridge`.
- **You:** Not attempted (fatigue; Home/Disarm unstable; trigger/outage disruptive; cutover separate environment).
- **I check:** Not attempted.
- **How we know:** Pass if each path completes without crash and states match the panel.
- **Result:** blocked — not walked.

## How it went

- 🚀 Booted / re-booted via `/run` (Supervisor + HA); IDE restart required a full stack bounce.
- 🧹 Clean rediscovery needed wiping `home-assistant_v2.db` **and** entity/device registries — then fix-forward discovery looked right (device nesting, prefixed IDs, Panel Link).
- ✅ One live HA → Home arm reached `armed_home` (with SETAREAARM ACK timeout in logs).
- ❌ HA Disarm NAK’d; App disarm left HA stale until add-on restart + area snapshot.
- 🔬 App coexistence spot check: we kept ComIP through app Home→Disarm; MQTT did not track app arm; “Remote Access Started” spam likely our standing ComIP/UDL session (log type 53 class).
- ⚠️ Home arm later NAK’d with no open zones; piping from panel noted — check if pip stops when add-on is stopped.
- 🌙 Stopped further live testing for fatigue; product gaps listed under Still open.

## Still open

- [ ] **Intermittent Home arm NAK** — succeeded once, later rejected with zones clear; ACK timeout observed on the success path; piping may correlate.
- [ ] **HA Disarm → SETAREADISARM NAK** — cannot disarm from HA tonight.
- [ ] **External/app arm-disarm not reflected in MQTT** while Panel Link ON (stale-while-live).
- [ ] **NAK / failed-command UI** — more-info can stay on Home while state is Disarmed (TASK-14 republish incomplete for this UX).
- [ ] **Texecom iOS App coexistence** — need durable design so app + add-on both work (survive and sync); Local vs cloud paths; not “app holds ComIP” as the only model.
- [ ] **Remote Access Started log spam** — likely our always-on ComIP LOGIN / type-53 session markers; confirm and decide if acceptable.
- [ ] **Panel piping noise** — check whether it stops when this add-on is not running.
- [ ] **DEBUG logging for zone/area activity** — not seeing expected DEBUG lines for entering/leaving areas, doors opening/closing, etc.; sort out log level / event logging later.
- [ ] **More-info arm order** Home→Away→Night — HA frontend-fixed; use Lovelace `states:` if household cares (limitation).
- [ ] **Unwalked acceptance paths** — door/window/other/shock zones; Away/Night ×3; full disarm matrix; keypad-disarm-after-arm MQTT proof; live siren + forced disconnect + snapshot; household wrapper/aggregates; production cutover with `the prior MQTT bridge` removed.
- [ ] **Published release / CHANGELOG / `/ship` cadence** — see [addon-versioning.md](addon-versioning.md); real version bump deferred to `/ship` or an explicit decision.
- [x] **Part-Arm Configuration radio labels** — TASK-17 (limitation accepted for accept checklist).
- [x] **Panel-link connectivity discovery** — verified after rebuild + clean rediscovery (was stale image / orphaned registry on first walk).
- [x] **Entity ID scheme / device / Title Case / alarm naming** — verified after registry wipe (TASK-12); first-discovery orphans needed wipe, not just republish.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-05 | Clear | — |
| 2 | 2026-08-05 | Issues found | 2 |
| 3 | 2026-08-05 | Clear | — |
