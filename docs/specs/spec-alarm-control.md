# Spec: alarm-control

**Date:** 2026-09-03
**State:** Accepted ✅

---

## Problem

The household arms and disarms from Home Assistant (dashboard, automations, or
anything that drives the alarm entity). A double submit of the same arm — two
identical commands a few tens of milliseconds apart — must not confuse the add-on:
the panel may already have accepted the first arm and be busy sending exit
events. If the add-on treats a torn follow-up as a failed arm, Home Assistant can
briefly show Off and **Alarm Panel Connection** off while Night (or Home/Away) is
actually in progress. During exit, a reconnect status read can still look unset;
that must not flash Off over an in-progress exit or entry.

## Goal

Arm away, night, and home, plus disarm from any state, work reliably: a second
identical arm after that mode already succeeded (or while the card already shows
that mode's `armed_*` state, or generic `arming` for this same gesture) does not
go to the panel again; disarm and a different arm mode still do, including while
the card shows generic `arming`. Live state includes arming and pending. A
sounding alarm does not crash the add-on. Entity availability stays tied to the
app process, not the panel link; freshness is a separate connection signal.

## Scope

**In scope**

- Arm away, arm night, and arm home, each reliably reaching the matching armed
  (or arming) state without crashing the add-on — including when the same arm is
  submitted twice in quick succession.
- Disarm, reliably, from any state (already disarmed, armed_away, armed_night,
  armed_home, triggered, pending, arming).
- Live reporting of the panel's current state (disarmed / armed_away / armed_night /
  armed_home / triggered / pending / arming) so automations and dashboards can
  react to it.
- Surviving an actual alarm trigger (siren activation) without crashing, and
  correctly reporting the `triggered` state throughout the event.
- A persisted snapshot of the most recent zone/log activity leading into a trigger
  (which zone initiated entry, and when), surviving any subsequent connection
  outage.
- A dedicated connectivity/freshness signal reporting whether the panel link is
  currently live or degraded, independent of the `alarm_control_panel`/zone
  entities' own state — those entities' availability is governed solely by whether
  the app itself is running, never by panel-link health.

**Out of scope**

- Zone monitoring (the ~35 zone `binary_sensor` entities) — covered by
  `spec-zone-monitoring.md`.
- Household rules for when arming is allowed (which doors and windows, night,
  guests) and the wording of blocked-arm notifications — those stay in the HA
  config layer. Ready-to-arm switches and refusing arm before it reaches the
  panel are specified in `spec-ready-to-arm.md`, not here.
- Building or changing the Lovelace dashboard or HomeKit exposure.

## Acceptance Criteria

1. Given the new integration is running with the prior MQTT bridge fully uninstalled, When
   `arm_away`, `arm_night`, and `arm_home` are each triggered 3 consecutive times,
   Then the panel transitions to the corresponding armed state each time without the
   integration crashing or restarting.
   - **How we'll know:** manual acceptance test (live panel ×3 arm cycles with
     the prior MQTT bridge uninstalled); MQTT arm command path also covered by end-to-end
     test (stand-in: FakePanel)
2. Given the panel is in any state (disarmed, armed_away, armed_night, armed_home,
   triggered, pending, or arming), When disarm is triggered, Then the panel
   transitions to disarmed without the integration crashing.
   - **How we'll know:** manual acceptance test (live disarm from each state); MQTT
     disarm command path also covered by end-to-end test (stand-in: FakePanel)
3. Given the panel is armed in any mode, When a zone is triggered while armed such
   that the alarm actually activates (siren sounds), Then the integration continues
   running without crashing and the `alarm_control_panel` entity correctly reports
   the `triggered` state throughout the event, including through any connection
   outage the panel itself forces at trigger time — the entity's last known state
   persists; only a true app-offline condition (see Edge Cases) would ever mark it
   unavailable.
   - **How we'll know:** manual acceptance test (live siren trigger through forced
     disconnect)
4. Given the `house_alarm_panel` wrapper entity forwards an arm or disarm call to the
   new `alarm_control_panel` entity, When that call succeeds or fails, Then the
   wrapper entity's state accurately reflects the outcome, preserving today's
   forwarding behavior.
   - **How we'll know:** manual acceptance test (household HA wrapper → new entity)
5. Given the prior MQTT bridge has been fully uninstalled, When arm/disarm control is
   exercised end-to-end (including a triggered alarm event), Then no functionality
   depends on it being present — no crashes, no missing state, no silent fallback
   behavior.
   - **How we'll know:** manual acceptance test (the prior MQTT bridge uninstalled; arm/disarm
     plus trigger exercised)
6. Given a zone triggers the alarm while armed, When the panel's connection is
   subsequently forced closed and reconnection is in progress, Then the
   `alarm_control_panel` entity continues reporting `triggered` (never "unavailable"
   due to this), a connectivity `binary_sensor` reflects the degraded panel link, and
   a "last trigger" snapshot (initiating zone, timestamp) remains visible throughout
   the outage.
   - **How we'll know:** end-to-end test (stand-in: FakePanel) for retained `triggered`,
     connectivity off, and snapshot attributes across reconnect; manual acceptance
     test for live trigger-time outage

7. Given an arm mode has already succeeded for this gesture (panel accepted that
   arm), or the alarm card already shows that mode's `armed_*` state, When a
   second identical arm for the same mode is submitted, Then the add-on does
   not send another arm to the panel. Generic `arming` (exit does not name the
   mode) ignores only that same gesture's mode, not a different `ARM_*`. Disarm
   and a different arm mode still go through. A reconnect flags snapshot that
   still looks unset is not “the house is Off” for this gate — flags omit
   exit/entry — so a later same-mode arm during that exit is still ignored.
   Once the house is unset — including from the keypad or vendor app, not
   only Home Assistant Disarm — a later same-mode arm is a new gesture and is sent.
   - **How we'll know:** unit test and end-to-end test (stand-in: FakePanel); assert
     a single panel arm for duplicate same-mode submits, that a different mode
     (including while the card shows generic `arming`) or disarm still reaches
     the panel, and that a same-mode arm after the house is unset is sent
8. Given the panel has already accepted an arm, When a follow-up read of the stream
   cannot be understood, Then that is not treated as a failed arm: the house still
   ends in that armed or arming state, including while the card still shows Off
   (connection behaviour is owned by the heal / liveness specs). A hang-up or
   the panel ending the session (`+++`) is still a lost session, not that
   unreadable-follow-up case — even if a prior arm already succeeded or the card
   already shows `arming`.
   - **How we'll know:** unit test and/or end-to-end test (stand-in: FakePanel);
     Connection and heal details asserted in those specs' tests

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
- Network/connection drop to the panel (during an arm/disarm command, while
  triggered, or at any other time) — the `alarm_control_panel` entity continues
  reporting its last known state; it never drops to "unavailable" because of a
  panel-link issue. Only a genuine app-offline condition (the app process itself
  down, detected via MQTT's standard availability/Last-Will mechanism) marks the
  entity "unavailable". A dedicated connectivity/freshness `binary_sensor` reports
  whether the panel link is currently live or degraded, so the household can judge
  how current the displayed state is.
- Integration restart while the panel is armed or triggered — must re-sync to the
  panel's actual current state on startup, not default to disarmed or another
  incorrect value.
- Rapid successive identical arm commands (e.g. an accidental double-tap) — after
  that mode has already succeeded for this gesture, or while the card shows
  that `armed_*` mode, the duplicate arm is ignored. Generic `arming` does not
  ignore a different arm mode (for example Away during Night exit). Disarm is
  still sent. A second disarm while already unset stays ignored as today. A
  reconnect flags snapshot that still looks unset must not forget this
  gesture (flags omit exit). Once the house is unset (including keypad /
  vendor live state), a later same-mode arm is a new gesture and is sent.
- Hang-up or `+++` while an arm is in flight is a lost session (Connection off),
  not a torn-message collision, even if the card already shows `arming` or a
  prior arm already succeeded. Unreadable Connect bytes after a successful arm
  remain a collision to resync.
- Alarm and zone entities are never marked unavailable because the panel link
  dropped; only the app process being down does that (via MQTT Last-Will).

## Constraints

- No runtime dependency on the prior MQTT bridge — it will be uninstalled once this
  capability is delivered.
- Away (`arm_away`) always maps to the panel's full-arm command (mode byte `0`),
  never to a Part-Arm slot. The mapping between HA's `arm_home` / `arm_night`
  labels and the panel's physical Part-Arm slot numbers (up to three
  engineer-configured slots) must be a documented, per-installation configuration
  value — never hardcoded to this household's own panel layout. Each Part-Arm
  config choice is Home, Night, or Unused only; Away must not appear as a
  Part-Arm option. Different Premier Elite installations can and do configure
  these slots differently.
- Household arm policy and blocked-arm notifications are not specified here (see
  `spec-ready-to-arm.md`). This spec only needs the underlying entity's
  forwarding contract (state in, command out) intact.
- Must support all seven MQTT alarm states used by Home Assistant:
  disarmed, armed_away, armed_night, armed_home, triggered, pending, arming.

## Open Questions

None open for this change.

## Spike Candidates

None for this change.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-01 | Clear | — |
| 2 | 2026-08-03 | Clear | — |
| 3 | 2026-08-04 | Issues found | 1 |
| 4 | 2026-08-04 | Clear | — |
| 5 | 2026-08-08 | Issues found | 2 |
| 6 | 2026-08-08 | Clear | — |
