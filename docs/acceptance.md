# Acceptance

**Date:** 2026-08-07
**State:** Draft 📝
<!-- State is exactly one of: Draft 📝 | Accepted ✅ | Deferred ⏸️ -->

## What we set out to build

A Home Assistant Add-on that replaces unreliable `the prior MQTT bridge` for a Texecom Premier Elite panel: MQTT-discovered zone binary sensors and a full three-mode `alarm_control_panel` (including Home), live panel sync, panel-link health separate from app liveness, and a last-trigger snapshot — without embedding household automation rules.

## Scorecard

| # | Scenario | Result | Notes |
|---|----------|--------|-------|
| 1 | Fix-forward discovery / inventory | ✅ pass | Reconfirmed 2026-08-07 on MQTT device Texecom Alarm (Premier Elite); Supervisor “Home Assistant App” metrics device is separate |
| 2 | Zone open/clear (live) | ✅ pass | Recorder-confirmed 2026-08-07 ~17:08 BST: door, interior window, kitchen slide clear, multiple PIRs within ~1–5s; Panel Link ON; shock not walked |
| 3 | Arm Home from HA (live) | ✅ pass | 2026-08-07 ~17:25 BST after zombie restart: `arming`→`armed_home` (~7s); prior intermittent NAK when session degraded |
| 4 | Disarm from HA (live) | ❌ fail | Practitioner disarmed immediately; panel+iOS App show Disarmed; HA/MQTT stayed `armed_home` with Panel Link ON (no disarm publish) |
| 5 | External / Texecom App state sync | ❌ fail | Reconfirmed: panel/app Disarmed while HA Armed home + Panel Link ON (stale-while-live) |
| 6 | Texecom iOS App coexistence (spot check) | ⚠️ partial | Idle+command cycle: add-on survived; app Home→Disarm not reflected in MQTT; brief app spinners |
| 7 | HA aggregates / wrapper / HomeKit path | 🚫 blocked | Local HA only; household config not walked |
| 8 | Away / Night ×3, disarm matrix, trigger+outage, cutover | 🚫 blocked | Not walked |

## Scenario: Fix-forward discovery / inventory

**Status:** Pass ✅

- **What we're proving:** TASK-10–12 discovery (prefixed IDs, device block, Title Case, Panel Link, alarm naming) shows correctly in HA after a clean rediscovery.
- **Examples:** Given a wiped entity/device registry + DB; When the add-on republishes discovery; Then zones/alarm/panel-link sit under MQTT device Texecom Alarm with `texecom_alarm_*` entity IDs.
- **You:** Confirmed device nesting, Front Door naming, Panel Link connected; noted more-info arm order Home→Away→Night (HA frontend-fixed). On 2026-08-07 re-walk: confirmed inventory under MQTT / Premier Elite device (not the Supervisor add-on metrics device).
- **I check:** Registry 42/42 on device with unique_ids; broker discovery matched; unique-id UI banner contradicted by registry (false alarm). Re-walk: discovery retained for Front Door / Kitchen L Slide / Ethans Rm L Wind (`zone/1`, `20`, `13`).
- **How we know:** Pass if HA matches broker/registry after clean rediscovery.
- **Result:** pass — required wiping HA DB **and** entity/device registries (DB alone left orphaned short IDs). IDE restart needed full Supervisor bounce. More-info arm button order cannot be set via MQTT `supported_features` list order. Two HA devices both named “Texecom Alarm” confused the walk until clarified (MQTT product device vs Supervisor process metrics).

## Scenario: Zone open/clear (live)

**Status:** Pass ✅

- **What we're proving:** Physical trigger/clear updates HA promptly (~2s) for representative sensor classes.
- **Examples:** Given a PIR (and ideally door/window/other); When opened/activated then cleared; Then the matching entity flips within ~2 seconds.
- **You:** Earlier mid-walk interiors looked dead (during Mosquitto/LWT churn). Later Activity looked correct; declined a re-walk — asked for independent recorder/log review.
- **I check:** HA `home-assistant_v2.db` recorder (BST = UTC+1). **Front Door** On→Off 16:40:39→44 and 17:08:42→43 (Δ≈1–4s). **Ethans Rm L Wind** On→Off 17:08:24→26 (Δ≈2.3s) — clears the prior interior Fail. **Kitchen L Slide** ON from startup snapshot (open at connect) → live Off 17:08:56 when closed. **PIRs** (Gf Hallway, Kitchen, Michael Stdy, Playroom, Ff Hallway) multiple On→Off cycles ~2–6s. **Panel Link** stayed ON after connect. Shock sensors never went On (not exercised). Earlier Fail coincided with `texecom/status=offline` after Mosquitto bounce — not an interior-zone product gap.
- **How we know:** Pass per class exercised; partial if only some classes done; fail for a class if physical open never reaches HA while Panel Link is ON.
- **Result:** pass — door, interior window, interior contact clear, and PIR classes evidenced in recorder without a second house walk; shock still unwalked (optional class).

## Scenario: Arm Home from HA (live)

**Status:** Pass ✅

- **What we're proving:** Arm home transitions the panel/HA to armed_home without crashing the integration.
- **Examples:** Given disarmed; When Arm home is selected in HA; Then command reaches the panel and state becomes armed_home (or a clear failure).
- **You:** After add-on restart cleared a zombie session, Arm Home from HA — seemed to go well.
- **I check:** Recorder `disarmed` → `arming` 17:25:16 → `armed_home` 17:25:23; MQTT retained `armed_home`; Panel Link ON; no NAK on this attempt. Earlier same day: NAK while zones clear / zombie session; prior walk had ACK-timeout-on-success.
- **How we know:** Pass if armed_home without crash; fail if no arm / crash; partial if intermittent.
- **Result:** pass for a healthy session — Home arm works when ComIP is live; intermittent NAK/zombie remains a separate Still-open reliability gap.

## Scenario: Disarm from HA (live)

**Status:** Fail ❌

- **What we're proving:** Disarm from HA clears an armed panel (and cancels exit) via the shared disarm command.
- **Examples:** Given armed_home; When Disarm in HA; Then panel and MQTT become disarmed.
- **You:** Disarmed almost immediately after Home arm; real panel + Texecom iOS App both show Disarmed. HA more-info still showed **Armed home** (Home pill green) minutes later.
- **I check:** MQTT retained `armed_home` + Panel Link ON; recorder never left `armed_home` after 17:25:23; no disarm/NAK line in add-on logs. Same stale-while-live pattern as prior walk (then SETAREADISARM NAK ×2).
- **How we know:** Pass if disarmed without crash; fail if NAK / no state change.
- **Result:** fail — panel is disarmed; HA/MQTT did not follow.

## Scenario: External / Texecom App state sync

**Status:** Fail ❌

- **What we're proving:** Panel arm/disarm originating outside this add-on (app, keypad) still updates MQTT while Panel Link is ON.
- **Examples:** Given add-on online; When panel state changes via Texecom App or keypad; Then `texecom/alarm/state` follows.
- **You:** Panel + iOS App Disarmed while HA Armed home (this session). Prior: App disarm after failed HA disarm left HA stale.
- **I check:** `texecom/alarm/state=armed_home` with `panel_link=ON` / `status=online` while panel truth is Disarmed. Restart for area snapshot attempted; login then hit TimeoutError / add-on `error` (ComIP contention — app may hold path).
- **How we know:** Pass if external changes appear on MQTT promptly; fail if Panel Link ON but state stale.
- **Result:** fail — survive ≠ sync; snapshot repair only helps after a clean re-login.

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
- **You:** Halted 2026-08-07 ~17:33 — household returned; no more arming. Earlier also blocked by Home/Disarm instability; cutover is a separate environment.
- **I check:** Not attempted.
- **How we know:** Pass if each path completes without crash and states match the panel.
- **Result:** blocked — not walked; resume when house is free.

## How it went

- 🚀 Booted via `/run` / `ha-cold-start.sh`; port contract settled (prefer `:7123`, pin Core `:8123`).
- 🧹 Clean rediscovery needed wiping HA DB **and** entity/device registries — inventory Pass under MQTT device Texecom Alarm.
- ✅ **Zones live Pass** (recorder): Front Door, Ethans window, Kitchen slide clear, multiple PIRs ~1–5s; early interior Fail was Mosquitto LWT/`offline`, not missing pushes.
- 🧟 **Zombie ComIP (~17:20):** Panel Link ON but last-changed only at connect; zones dead; Kitchen PIR stuck; Home NAK. Restart restored live.
- ✅ **Home arm Pass** after restart (`arming`→`armed_home` ~17:25, ~7s).
- ❌ **Disarm / sync Fail:** panel + iOS App Disarmed; HA stayed Armed home + Panel Link ON until restart + area snapshot (~17:32) → `disarmed`.
- 🔬 App coexistence: survive-only; Remote Access spam; Tailscale off for reliable LAN.
- 📜 Specs Accepted (not shipped): continuous-operation self-heal; zone Entity IDs `…_zone_{N}`.
- 🛑 Walk stopped — peeps back. Draft kept; product Accept blocked while Still open has gaps.

## Still open

- [x] **Interior contact live updates** — closed via recorder; prior Fail was infra (LWT offline).
- [ ] **Zombie ComIP / stale Panel Link** — session dies while `online` + `panel_link=ON` retained (not a heartbeat). Captured in Draft [`spec-panel-link-liveness.md`](specs/spec-panel-link-liveness.md) (rename signal to **Alarm Panel Connected**).
- [ ] **HA Disarm / arm-state MQTT sync** — panel Disarmed while HA/MQTT stay `armed_home` (also prior SETAREADISARM NAK). Blocks trustworthy arm control.
- [ ] **External/app arm-disarm → MQTT** — same stale-while-live; snapshot on restart only.
- [ ] **Intermittent Home arm NAK** — when session degraded; clean session Home arm Pass once.
- [ ] **NAK / failed-command UI** — more-info pill can disagree with status text.
- [ ] **Texecom iOS App coexistence** — survive ≠ sync; Local vs cloud; Remote Access spam.
- [ ] **Panel piping noise** — does it stop when this add-on is stopped?
- [ ] **DEBUG logging for zone/area activity** — superseded by Draft [`spec-diagnostics-logging.md`](specs/spec-diagnostics-logging.md) (WARNING/INFO/DEBUG/TRACE config + instrumentation).
- [ ] **Rename Supervisor add-on** to “Texecom Alarm App”.
- [ ] **Implement Accepted specs** — continuous-operation; `_zone_{N}` naming (`/correction` → plan/build).
- [ ] **More-info arm order** — HA frontend-fixed (limitation).
- [ ] **Unwalked acceptance paths** — Away/Night ×3; disarm matrix; shock; siren+outage+snapshot; wrapper; cutover.
- [ ] **Published release / CHANGELOG / `/ship`** — see [addon-versioning.md](addon-versioning.md).
- [x] **Part-Arm radio labels** — TASK-17 limitation accepted.
- [x] **Panel-link discovery / current entity scheme** — verified after wipe; new `_zone_{N}` naming Accepted in spec, not shipped.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-05 | Clear | — |
| 2 | 2026-08-05 | Issues found | 2 |
| 3 | 2026-08-05 | Clear | — |
