# Spec: zone-monitoring

**Date:** 2026-08-01
**State:** Accepted ✅

---

## Problem

Zone monitoring itself works fine today via `the prior MQTT bridge`'s MQTT discovery, but it
depends entirely on that closed-source, unreliable add-on, which is being removed.
Once it's gone, Home Assistant automations and the household's Security dashboard
will lose all zone-state visibility unless that dependency is eliminated first.

## Goal

Home Assistant — the primary consumer, since automations and guard-condition
aggregates run off zone state — and the household, who occasionally check the
Security dashboard, have full zone-state visibility reproduced as native HA
entities, with zero runtime dependency on `the prior MQTT bridge`, so it can be safely
uninstalled once this is delivered.

## Scope

**In scope**

- All ~35 zone entities (door contacts, window contacts, shock sensors, PIR motion
  sensors, and the garage mirror sensor) reproduced as HA `binary_sensor` entities
  reflecting current physical/panel zone state.
- Entity naming/state compatible with (or accompanied by a documented migration
  path for) the existing aggregates and automations that consume today's
  `binary_sensor.texecom_alarm_*` entities.
- State updates delivered within 2 seconds of a physical trigger/clear, so
  time-sensitive automations (e.g. the 60s auto-arm motion-cancel countdown, the
  "I'm leaving" script's wait for the front door to transition on→off) keep
  working correctly.
- Operation fully independent of `the prior MQTT bridge`, which will be uninstalled once
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

## Acceptance Criteria

1. Given the new integration is running with `the prior MQTT bridge` fully uninstalled,
   When Home Assistant starts up, Then all ~35 zone entities are present with
   correct names/types (door contact, window contact, shock sensor, PIR motion,
   other).
2. Given one representative zone from each of the five sensor classes (door,
   window, shock, PIR, other), When that zone is physically triggered and then
   cleared, Then the corresponding HA entity state changes to reflect it within 2
   seconds of the physical trigger/clear.
3. Given a dependent aggregate or automation (e.g. `binary_sensor.all_doors`, the
   auto-arm motion-cancel, or the "I'm leaving" script's front-door wait), When
   the underlying zone entities change state, Then that aggregate/automation
   continues to function correctly without modification to its own logic.
4. Given `the prior MQTT bridge` has been fully uninstalled, When zone monitoring is
   exercised end-to-end, Then no functionality depends on it being present — no
   crashes, no missing data, no silent fallback behavior.
5. Given the panel/network connection drops, When reconnection is in progress,
   Then every zone `binary_sensor` entity continues reporting its last known state
   (never "unavailable" due to this) and the shared connectivity `binary_sensor`
   (see `spec-alarm-control.md`) reflects the degraded panel link.

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
- Entity ID/naming migration: if new entity IDs differ from today's
  `binary_sensor.texecom_alarm_*` naming, a documented migration path must exist
  so dependent automations aren't silently broken.
- Co-located sensors: two sensors on the same physical opening (e.g. a window
  contact and a shock sensor on the same window) must be reported as independent
  entities, not merged or conflated.

## Constraints

- State changes must be reported to HA within 2 seconds of the physical
  trigger/clear, so time-sensitive automations (the 60s auto-arm countdown
  cancel-on-motion, front-door on→off transition detection) keep working
  correctly.
- No runtime dependency on `the prior MQTT bridge` — it will be uninstalled once this
  capability is delivered.
- Entity naming/state values must be compatible with (or have a documented
  migration for) all consumers listed in `docs/ha-alarm-usage-spec.md`.

## Open Questions

- Should new zone entity IDs exactly match today's `binary_sensor.texecom_alarm_*`
  naming, or is a documented rename/migration acceptable? (Owner: household/spec
  author — resolve before Phase 2 build starts on this capability.)

## Spike Candidates

- Whether/how the Texecom Connect protocol supports enumerating the zone
  list/count programmatically, versus requiring zones to be manually specified in
  configuration. (Raised during the spec interview — needs protocol-level
  investigation, likely during Phase 1, before Phase 2 build starts.)

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-01 | Issues found | 2 |
| 2 | 2026-08-01 | Clear | — |
