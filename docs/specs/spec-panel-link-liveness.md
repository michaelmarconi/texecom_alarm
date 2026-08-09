# Spec: panel-link-liveness

**Date:** 2026-08-07  
**State:** Accepted ✅

---

## Problem

The household and Home Assistant automations use the connectivity signal as proof
that zone and alarm state are current. Today that signal can stay “live” after the
panel path has silently stopped delivering trustworthy updates (zones freeze,
sensors stick, commands fail) while the app process and MQTT availability still
look healthy — so automations and people act as if the panel is monitored when it
is not.

## Goal

Home Assistant can treat the connectivity signal as a truthful live-vs-degraded
freshness indicator: when the panel path is no longer trustworthy, the signal
shows degraded promptly; when monitoring resumes, it returns to live and state is
re-synced — without a manual add-on restart and without blanking zone/alarm
entities solely because of panel recovery.

## Scope

**In scope**

- Detect when a previously healthy panel session has stopped delivering
  trustworthy updates (including silent failure, not only clean disconnects) and
  set the connectivity signal to degraded.
- Keep zone and alarm entities available with last-known state while degraded;
  freshness is communicated only via the connectivity signal.
- Resume monitoring automatically when the panel path works again (re-sync state;
  connectivity signal live) without an operator restarting the add-on.
- Present the connectivity entity in Home Assistant with the friendly name
  **Alarm Panel Connected** (replacing the current “Panel Link” label).
- Preserve correct degraded → live behaviour for obvious panel drops (no regression
  of the existing clean-disconnect recovery path).

**Out of scope**

- Household automations, dashboards, or notifications that react to the
  connectivity signal — those stay in the Home Assistant configuration layer;
  this app only makes the signal truthful.
- Marking zone or alarm entities unavailable because the panel path is dead —
  availability stays tied to whether the app process itself is running; last-known
  state remains visible.
- Guaranteeing a live session while another client permanently holds the single
  panel connection — the app can only show degraded and retry; it cannot share or
  preempt that slot.
- Startup “never exit / keep retrying on first connect failure” — owned by
  `spec-continuous-operation.md`; this spec covers silent death after a session
  looked healthy.

## Acceptance Criteria

### AC1: Silent panel-path death sets connectivity degraded

Given a panel session that was reporting live, When the panel path stops
delivering trustworthy updates without a clean disconnect the household would
notice, Then **Alarm Panel Connected** shows degraded within a short, fixed bound
suitable for automation gating (target: on the order of tens of seconds, not
minutes or hours).

- **How we'll know:** end-to-end test (stand-in: FakePanel that goes silent after
  a healthy session; recording MQTT broker)

### AC2: Zone and alarm entities stay available while degraded

Given the connectivity signal is degraded because the panel path is not
trustworthy, When Home Assistant inspects zone and alarm entities, Then they are
not marked unavailable solely for that reason; they retain last-known state and
only the connectivity signal indicates staleness.

- **How we'll know:** end-to-end test (stand-in: FakePanel + recording MQTT
  broker)

### AC3: Monitoring resumes without manual restart

Given connectivity is degraded after silent panel-path death, When the panel path
becomes usable again, Then zone and alarm state are re-synced from the panel and
**Alarm Panel Connected** returns to live — without an operator restarting the
add-on.

- **How we'll know:** end-to-end test (stand-in: FakePanel); optional manual
  acceptance test on a live silent-death reproduction if needed to corroborate

### AC4: Connectivity entity is named Alarm Panel Connected

Given MQTT discovery for the connectivity entity, When the household views it in
Home Assistant, Then its friendly name is **Alarm Panel Connected** (not
“Panel Link”).

- **How we'll know:** unit test (discovery payload name assertion)

### AC5: Clean disconnect path still degrades then recovers

Given an obvious panel drop after a healthy session, When reconnect runs, Then
**Alarm Panel Connected** goes degraded and later returns to live after successful
recovery (no regression vs the existing clean-disconnect behaviour).

- **How we'll know:** end-to-end test (stand-in: FakePanel forced disconnect +
  reconnect)

---

## User Stories

- As Home Assistant automations, I want **Alarm Panel Connected** to mean the
  panel path is truly live, so I only treat zone/alarm state as current when that
  signal is on.
- As the household operator, I want that same signal (and any alerts I wire to it)
  to tell me whether HA’s Texecom picture is trustworthy right now, without
  walking the house or restarting the add-on to check.

## Edge Cases

- Another client holds the panel connection indefinitely: connectivity stays
  degraded; zone/alarm entities remain available with last-known state; live
  monitoring is not promised until the slot is free.
- Connectivity already degraded from a clean disconnect when silence would also
  apply: still one degraded signal; no flapping between equivalent failure modes.
- MQTT broker down while the panel path dies: out of scope to redefine broker
  dependency; once MQTT is up, process availability / Last-Will rules from
  existing specs still apply.
- True process crash: process may exit; Supervisor Watchdog may restart — last
  resort, not the design for silent panel-path death.
- Stuck zone state left from before degradation (e.g. a sensor left “on”): after
  recovery, re-sync must correct MQTT to the panel’s current truth.

## Constraints

- Zone and alarm entity **availability** must remain governed solely by whether
  the app process is running (broker Last-Will / process-offline), never by
  panel-path health — already required by `spec-zone-monitoring` /
  `spec-alarm-control`.
- Connectivity / freshness remains a **separate** signal from entity availability.
- The panel accepts only one monitoring client connection at a time — recovery
  cannot assume a second simultaneous session.
- Degraded detection must be fast enough that automations gating on the signal are
  useful (order of tens of seconds), not reliant on human notice hours later.
- Friendly name **Alarm Panel Connected** is the household-facing label; changing
  Entity IDs is not required by this spec unless discovery already forces a rename
  for correctness (see Spike Candidates).

## Open Questions

- ~~Exact numeric bound for “tens of seconds” (e.g. 30 vs 60)~~ **Answered
  2026-08-09:** Lock **30 seconds** as the order-of-tens bound (matches shipping
  trust-poll / recover window). Friendly-name rename to **Alarm Panel Connection**
  (and related id clean-up) is owned by Accepted `spec-panel-session-heal.md` —
  run `/correction` so this spec’s **Alarm Panel Connected** wording aligns.

## Spike Candidates

- ~~How to detect silent panel-path death reliably…~~ **Covered:** ADR-010
  (command-reject + periodic house-state poll); SPIKE-008 Validated.
- ~~Whether renaming the friendly name alone is enough… vs `unique_id` / Entity ID~~
  **Answered 2026-08-09 (via `spec-panel-session-heal`):** Clean refactor — name
  **Alarm Panel Connection** and change ids as needed; no backwards-compat soft
  path. Align this spec via `/correction`.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-07 | Clear | — |
