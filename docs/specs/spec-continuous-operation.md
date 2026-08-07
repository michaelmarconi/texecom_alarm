# Spec: continuous-operation

**Date:** 2026-08-07  
**State:** Accepted ✅

---

## Problem

Home Assistant automations and the household trust this app’s zone and alarm
entities as the live view of the panel. Today, if the panel drops or rejects the
**first** connect/login (for example ComIP contention or a forced disconnect
mid-LOGIN), the app process exits, Supervisor can sit in `error`, MQTT
availability goes offline, and entities become unavailable until a human
restarts the add-on — leaving the house effectively unmonitored even though the
failure was transient.

## Goal

Home Assistant can treat this app as a continuously running monitoring bridge:
transient panel connect/login failures (including at startup) self-heal without
an operator restart, without flapping zone/alarm entities to unavailable solely
because the panel link is recovering.

## Scope

**In scope**

- After any panel connect/login failure — including the very first start — the
  app keeps running and keeps retrying until monitoring is restored; it does not
  remain dead waiting for a manual restart.
- While the panel link is recovering, zone and alarm entities stay available
  (app process is up); the separate panel-link / freshness signal reports
  degraded, consistent with existing zone-monitoring and alarm-control specs.
- When the panel becomes reachable again, monitoring resumes (state re-synced,
  panel-link live) without an operator restarting the add-on.
- Supervisor **Watchdog** remains a last-resort safety net for true process
  crashes — not the primary recovery path for transient panel failures.

**Out of scope**

- Guaranteeing a successful panel session while another client permanently holds
  the single ComIP connection — the app must keep retrying; it cannot share or
  preempt that slot.
- Household automations, dashboards, or notifications that react to degraded
  panel-link — those stay in the Home Assistant config layer.

## Acceptance Criteria

### AC1: Startup panel failure does not leave the app dead

Given the panel rejects or drops the first connect/login, When the app has been
started, Then it keeps running and retries until login succeeds (it does not sit
in a dead Supervisor `error` state waiting for a human).

- **How we'll know:** end-to-end test (stand-in: FakePanel that fails login N
  times then succeeds)

### AC2: Entities stay available while panel link is recovering

Given the app is up but the panel link is not yet live, When Home Assistant
inspects zone/alarm entities, Then they are not marked unavailable solely
because of the panel outage; the panel-link signal shows degraded.

- **How we'll know:** end-to-end test (stand-in: FakePanel + recording MQTT
  broker)

### AC3: Monitoring resumes without manual restart

Given a prolonged panel-unreachable period and then the panel becomes reachable,
When a retry succeeds, Then zone/alarm state is re-synced and panel-link returns
to live — without an operator restart.

- **How we'll know:** end-to-end test (stand-in: FakePanel); manual acceptance
  test on live ComIP contention if needed to corroborate

### AC4: Watchdog remains last resort only

Given a true process crash (unhandled bug), When Watchdog is enabled, Then
Supervisor may restart the app — but transient panel failures must not depend on
that path (they must not exit the process).

- **How we'll know:** unit test that startup panel failures do not exit the
  process; Watchdog behaviour itself is smoke / manual only

---

## User Stories

- As Home Assistant (automations and dashboards), I want the Texecom bridge to
  keep providing trustworthy entity availability and a clear degraded signal when
  the panel link is down, so that guard conditions and monitoring do not silently
  go dark after a transient panel failure.

## Edge Cases

- Another client holds ComIP indefinitely: app stays up, retries, panel-link
  stays degraded; zone/alarm entities remain available with last-known state —
  success is not promised until the slot is free.
- Panel accepts TCP then closes during LOGIN (`ForcedDisconnect` / timeout):
  treated as recoverable; process must not exit.
- Steady-state disconnect after a healthy start: existing continuous reconnect
  behaviour remains required; this spec extends the same “never stay dead”
  expectation to startup.
- MQTT broker unreachable at start: out of scope to redefine broker dependency;
  once MQTT is up, availability/LWT rules from existing specs still apply.
- True unhandled exception / bug: process may exit; Watchdog may restart — that
  path is last resort, not the design for panel failures.

## Constraints

- Zone and alarm entity **availability** must remain governed solely by whether
  the app process is running (broker Last-Will / process-offline signal), never by
  panel-link health — already required by `spec-zone-monitoring` /
  `spec-alarm-control`.
- Panel-link / freshness remains a **separate** signal from entity availability.
- The panel accepts only one monitoring client connection at a time — retry cannot
  assume a second simultaneous session.
- Reconnect patience after real alarm triggers vs ordinary disconnects remains
  asymmetric for post-start recovery (longer/more patient after a trigger);
  startup recovery must be at least as persistent (keep trying; do not give up and
  exit).

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-07 | Issues found | 2 |
| 2 | 2026-08-07 | Clear | — |

