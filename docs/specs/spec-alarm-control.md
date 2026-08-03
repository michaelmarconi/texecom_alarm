# Spec: alarm-control

**Date:** 2026-08-01
**State:** Accepted ✅

---

## Problem

Today, arming to Home mode (`part_arm_2`) has never worked without crashing the
`the prior MQTT bridge` add-on — the HA template wrapper has no `arm_home` handler at all,
because it's never been safe to expose one. Separately, the add-on also crashes when
the alarm is actually triggered (siren activation) — the exact moment reliability
matters most. On top of both of these specific failure modes, the add-on is also
generally crash/restart-prone (a suspected TX/RX collision bug), so arm/disarm
control as a whole can't be trusted to keep working.

## Goal

The `house_alarm_panel` wrapper entity — and through it, the household's automations
(auto-arm on empty house, auto-disarm on return, the `im_leaving`/`cancel_leaving`
scripts, garage integration) and HomeKit exposure — has a reliable underlying
`alarm_control_panel` entity that supports all three arm modes (away, night, and
home) plus disarm and accurate live state reporting, without crashing during either
normal arm/disarm cycles or an actual alarm trigger.

## Scope

**In scope**

- Arm away, arm night, and arm home, each reliably transitioning the panel to the
  corresponding HA state without crashing the integration.
- Disarm, reliably, from any state (already disarmed, armed_away, armed_night,
  armed_home, triggered, pending, arming).
- Live reporting of the panel's current state (disarmed / armed_away / armed_night /
  armed_home / triggered / pending / arming) so the wrapper entity and its dependent
  automations/scripts/HomeKit exposure can react to it.
- Surviving an actual alarm trigger (siren activation) without crashing, and
  correctly reporting the `triggered` state throughout the event.
- Operation fully independent of `the prior MQTT bridge`, which will be uninstalled once this
  capability is delivered.

**Out of scope**

- Zone monitoring (the ~35 zone `binary_sensor` entities) — covered by
  `spec-zone-monitoring.md`.
- The arm guard-condition logic (blocking `arm_away`/`arm_night` when doors/windows
  are open, or the night-mode dark/no-guests checks) — lives in
  `configuration/templates/house_alarm.yaml` and stays as-is.
- The notification logic for blocked-arm explanations (`script.notify_actor`) —
  stays as-is in the HA config layer.
- Building or changing the Lovelace dashboard or HomeKit exposure.

## Acceptance Criteria

1. Given the new integration is running with `the prior MQTT bridge` fully uninstalled, When
   `arm_away`, `arm_night`, and `arm_home` are each triggered 3 consecutive times,
   Then the panel transitions to the corresponding armed state each time without the
   integration crashing or restarting.
2. Given the panel is in any state (disarmed, armed_away, armed_night, armed_home,
   triggered, pending, or arming), When disarm is triggered, Then the panel
   transitions to disarmed without the integration crashing.
3. Given the panel is armed in any mode, When a zone is triggered while armed such
   that the alarm actually activates (siren sounds), Then the integration continues
   running without crashing and the `alarm_control_panel` entity correctly reports
   the `triggered` state throughout the event.
4. Given the `house_alarm_panel` wrapper entity forwards an arm or disarm call to the
   new `alarm_control_panel` entity, When that call succeeds or fails, Then the
   wrapper entity's state accurately reflects the outcome, preserving today's
   forwarding behavior.
5. Given `the prior MQTT bridge` has been fully uninstalled, When arm/disarm control is
   exercised end-to-end (including a triggered alarm event), Then no functionality
   depends on it being present — no crashes, no missing state, no silent fallback
   behavior.

## User Stories

- As the `house_alarm_panel` wrapper entity (and the automations/scripts that target
  it — auto-arm on empty house, auto-disarm on return, `im_leaving`/`cancel_leaving`,
  garage integration), I want a reliable underlying `alarm_control_panel` entity for
  all three arm modes plus disarm, so that today's automation behavior keeps working
  unmodified.
- As a household member, I want to arm/disarm via the dashboard or HomeKit —
  including Home mode, which has never worked — without triggering a crash, so that
  I can trust the alarm to actually respond to my command.

## Edge Cases

- An arm command is issued while the panel is already mid-transition
  (arming/pending) — must not crash or leave the entity in an inconsistent state.
- Network/connection drop to the panel during an arm/disarm command or while
  triggered — the entity should reflect an "unavailable" state rather than silently
  freezing on a stale value.
- Integration restart while the panel is armed or triggered — must re-sync to the
  panel's actual current state on startup, not default to disarmed or another
  incorrect value.
- Rapid successive arm/disarm commands (e.g. an accidental double-tap) — must not
  induce the suspected TX/RX collision crash pattern described in the brief.

## Constraints

- No runtime dependency on `the prior MQTT bridge` — it will be uninstalled once this
  capability is delivered.
- The `house_alarm_panel` wrapper entity's guard-condition and notification logic is
  not reimplemented here — this spec only needs to keep the underlying entity's
  forwarding contract (state in, command out) intact.
- Must support all seven states referenced in `docs/ha-alarm-usage-spec.md`:
  disarmed, armed_away, armed_night, armed_home, triggered, pending, arming.

## Open Questions

- Should the new `alarm_control_panel` entity ID exactly match today's
  `alarm_control_panel.texecom_alarm_arm_status` naming, or is a documented
  rename/migration (updating `house_alarm.yaml`'s target) acceptable? (Owner:
  household/spec author — resolve before Phase 2 build starts on this capability.)

## Spike Candidates

- Whether the new integration can expose the alarm as a more natively-modeled HA
  alarm system (e.g. via MQTT `alarm_control_panel` discovery) in a way that removes
  the need for the `house_alarm_panel` template wrapper layer entirely, versus
  keeping the current two-layer (raw entity + template wrapper) architecture.
  (Raised during the spec interview — architectural/technical choice, needs
  `/analyse` investigation.)
- The exact byte-level command framing for `arm_home` (`part_arm_2`) and for
  reliably surviving/reporting a triggered event without inducing the suspected
  TX/RX collision crash — needs Phase 1 protocol research before this can be built.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-01 | Clear | — |
| 2 | 2026-08-03 | Clear | — |
