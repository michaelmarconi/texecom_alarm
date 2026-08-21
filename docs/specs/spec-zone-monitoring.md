# Spec: zone-monitoring

**Date:** 2026-08-01  
**Amended:** 2026-08-07 (zone Entity ID shape → `_zone_{N}`)  
**State:** Accepted ✅

---

## Problem

Zone monitoring itself works fine today vithe prior MQTT bridge's MQTT discovery, but it
depends entirely on that closed-source, unreliable add-on, which is being removed.
Once it's gone, Home Assistant automations and the household's Security dashboard
will lose all zone-state visibility unless that dependency is eliminated first.

Separately: publishing zone Entity IDs as `texecom_alarm_{slug}_{N}` makes the
trailing `_{N}` look like Home Assistant's collision suffix (`_2`, `_3`, …), which
misleads operators. Trial installs beside the prior MQTT bridge also need Entity IDs that
do not claim the same bare `texecom_alarm_{slug}` ids.

## Goal

Home Assistant — the primary consumer, since automations and guard-condition
aggregates run off zone state — and the household, who occasionally check the
Security dashboard, have full zone-state visibility reproduced as native HA
entities, with zero runtime dependency on the prior MQTT bridge, so it can be safely
uninstalled once this is delivered.

Zone Entity IDs use an explicit `_zone_{N}` disambiguator (readable, unique, and
side-by-side-friendly with the prior MQTT bridge bare slugs), with stable zone-number
`unique_id`s so UI renames can stick.

## Scope

**In scope**

- All ~35 zone entities (door contacts, window contacts, shock sensors, PIR motion
  sensors, and the garage mirror sensor) reproduced as HA `binary_sensor` entities
  reflecting current physical/panel zone state.
- Zone **Entity ID** shape: `binary_sensor.texecom_alarm_{slug}_zone_{N}` (e.g.
  `binary_sensor.texecom_alarm_front_door_zone_1`). Stable `unique_id` keyed
  by zone number (e.g. `texecom_alarm_zone_1`). Friendly **name** remains
  Title-Cased panel text without `_zone_N`.
- Entity naming/state accompanied by a documented migration path for consumers of
  today's `binary_sensor.texecom_alarm_*` (scheme match, not bit-identical legacy
  IDs; cutover may need household updates).
- State updates delivered within 2 seconds of a physical trigger/clear, so
  time-sensitive automations (e.g. the 60s auto-arm motion-cancel countdown, the
  "I'm leaving" script's wait for the front door to transition on→off) keep
  working correctly.
- Operation fully independent of the prior MQTT bridge, which will be uninstalled once
  this capability is delivered.
- The same connectivity/freshness signal defined in `spec-alarm-control.md` covers
  zone entities too: their availability is governed solely by whether the app
  itself is running, never by panel-link health.

**Out of scope**

- Alarm arm/disarm control (the `alarm_control_panel` entity, arm modes, and the
  Home-mode fix) — covered by a separate spec.
- The aggregate/derived sensors (`binary_sensor.all_doors`,
  `windows_with_sensors`, `all_motion_sensors`, etc.) and all automation,
  notification, and guard-condition logic built on top of zone state — these stay
  as-is in the HA config layer and are not reimplemented here.
- Building or changing the Lovelace dashboard or HomeKit exposure.
- Adding new zone types or sensors beyond today's ~35-zone inventory.
- The protocol decode work itself (Phase 1 packet capture / framing research) —
  that's investigative groundwork, not part of this spec.
- Bit-identical the prior MQTT bridge Entity IDs or automatic migration of household
  automations.
- Panel serial in Entity ID or `unique_id` (unproven command; optional later spike).
- Install-time “legacy bare slug” Entity ID option — not required here: default
  `_zone_{N}` already enables side-by-side trial with the prior MQTT bridge, and cutover is
  covered by the documented migration path.
- Changing alarm or panel-link Entity IDs (`alarm_control_panel.texecom_alarm_arm_status`,
  `binary_sensor.texecom_alarm_panel_link`).

## Acceptance Criteria

1. Given the new integration is running with the prior MQTT bridge fully uninstalled,
   When Home Assistant starts up, Then all ~35 zone entities are present with
   correct names/types (door contact, window contact, shock sensor, PIR motion,
   other).
   - **How we'll know:** manual acceptance test (live ~35 inventory match with
     the prior MQTT bridge uninstalled); in-use zone discovery also covered by end-to-end
     test (stand-in: FakePanel)
2. Given one representative zone from each of the five sensor classes (door,
   window, shock, PIR, other), When that zone is physically triggered and then
   cleared, Then the corresponding HA entity state changes to reflect it within 2
   seconds of the physical trigger/clear.
   - **How we'll know:** manual acceptance test (physical open/clear on one zone per
     sensor class)
3. Given a dependent aggregate or automation (e.g. `binary_sensor.all_doors`, the
   auto-arm motion-cancel, or the "I'm leaving" script's front-door wait), When
   the underlying zone entities change state, Then that aggregate/automation
   continues to function correctly without modification to its own logic.
   - **How we'll know:** manual acceptance test (household HA aggregates/automations
     against live zone entities)
4. Given the prior MQTT bridge has been fully uninstalled, When zone monitoring is
   exercised end-to-end, Then no functionality depends on it being present — no
   crashes, no missing data, no silent fallback behavior.
   - **How we'll know:** manual acceptance test (the prior MQTT bridge uninstalled; zone
     monitoring exercised)
5. Given the panel/network connection drops, When reconnection is in progress,
   Then every zone `binary_sensor` entity continues reporting its last known state
   (never "unavailable" due to this) and the shared connectivity `binary_sensor`
   (see `spec-alarm-control.md`) reflects the degraded panel link.
   - **How we'll know:** end-to-end test (stand-in: FakePanel) for last-known zone
     state plus panel-link connectivity sensor; optional manual acceptance test for
     a live connection drop
6. Given discovery for an in-use zone (e.g. Front Door, zone 1), When Home
   Assistant creates the entity, Then Entity ID is
   `binary_sensor.texecom_alarm_{slug}_zone_{N}` (e.g.
   `binary_sensor.texecom_alarm_front_door_zone_1`) — not bare `_{N}` and not
   slug-only without `_zone_{N}`.
   - **How we'll know:** unit test on discovery payload; end-to-end test
     (stand-in: FakePanel)
7. Given the same zone rediscovered after a wipe/restart, When the entity is
   recreated, Then `unique_id` remains zone-stable (e.g. `texecom_alarm_zone_1`)
   so a user-renamed Entity ID can stick across rediscovery.
   - **How we'll know:** unit test on discovery `unique_id`
8. Given discovery, When the entity appears in Home Assistant, Then the friendly
   name is Title-Cased panel text without `_zone_N`.
   - **How we'll know:** unit test on discovery `name`
9. Given our discovery default Entity ID and a hypothetical the prior MQTT bridge entity
   `binary_sensor.texecom_alarm_{slug}`, When both use their default ids, Then ours
   is `…_{slug}_zone_{N}` and does not claim the bare `…_{slug}` id.
   - **How we'll know:** unit test asserting `default_entity_id` shape (no live
     dual-bridge required)

## User Stories

- As Home Assistant (running automations), I want up-to-date zone state, so that
  guard-condition aggregates and automations (auto-arm cancel-on-motion, the "I'm
  leaving" wait, garage integration) continue working unmodified.
- As a household member, I want to see zone state on the Security dashboard, so
  that I can check which doors/windows are open before arming.

## Edge Cases

- Panel/network connection drops: zone entities continue reporting their last known
  state; they never drop to "unavailable" because of a panel-link issue. Only a
  genuine app-offline condition (the app process itself down, detected via MQTT's
  standard availability/Last-Will mechanism) marks zone entities "unavailable". The
  same connectivity/freshness `binary_sensor` used by the alarm entity (see
  `spec-alarm-control.md`) reports panel-link health, so zone-state currency is
  visible.
- Integration restart: zone entities should re-sync to the panel's current state
  on startup rather than defaulting to an incorrect on/off value.
- Entity ID/naming migration: zone Entity IDs use
  `texecom_alarm_{slug}_zone_{N}` (not bit-identical to the prior MQTT bridge bare slugs, and
  not the prior `_{N}`-only suffix). Documented migration / household updates remain
  required at cutover; trial side-by-side with the prior MQTT bridge must not claim the same
  bare `…_{slug}` Entity IDs.
- Co-located sensors: two sensors on the same physical opening (e.g. a window
  contact and a shock sensor on the same window) must be reported as independent
  entities, not merged or conflated.

## Constraints

- State changes must be reported to HA within 2 seconds of the physical
  trigger/clear, so time-sensitive automations (the 60s auto-arm countdown
  cancel-on-motion, front-door on→off transition detection) keep working
  correctly.
- No runtime dependency on the prior MQTT bridge — it will be uninstalled once this
  capability is delivered.
- Entity naming/state values must use the `texecom_alarm_*` scheme with explicit
  `_zone_{N}` on zone Entity IDs, with a documented migration for consumers listed
  in `the product brief and capability specs` (not bit-identical legacy IDs).

## Open Questions

- ~~Should new zone entity IDs exactly match today's `binary_sensor.texecom_alarm_*`
  naming, or is a documented rename/migration acceptable?~~ **Answered 2026-08-05;
  amended 2026-08-07:** Use the `texecom_alarm_*` scheme (not bit-identical legacy
  IDs). Zone Entity IDs are `texecom_alarm_{slug}_zone_{N}` via discovery
  `default_entity_id` (and matching topic/`object_id` as needed). `unique_id` is
  zone-stable (e.g. `texecom_alarm_zone_{N}`). Friendly name is Title-Cased panel
  text without `_zone_N`. The prior `texecom_alarm_{slug}_{N}` shape is rejected
  because raw `_{N}` looks like HA's collision suffix. Cutover may need household
  automation/entity updates; side-by-side trial with the prior MQTT bridge is intentional.

## Spike Candidates

- Whether/how the Texecom Connect protocol supports enumerating the zone
  list/count programmatically, versus requiring zones to be manually specified in
  configuration. (Raised during the spec interview — needs protocol-level
  investigation, likely during Phase 1, before Phase 2 build starts.)
- Whether a stable numeric panel serial can be read for device/`unique_id`
  namespacing (the prior MQTT bridge uses a separate serial command; not validated here).

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-01 | Issues found | 2 |
| 2 | 2026-08-01 | Clear | — |
| 3 | 2026-08-04 | Clear | — |
| 4 | 2026-08-07 | Issues found | 1 |
| 5 | 2026-08-07 | Clear | — |


