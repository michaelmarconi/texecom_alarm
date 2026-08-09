# Spec: panel-session-heal

**Date:** 2026-08-09  
**State:** Accepted ✅

---

## Problem

The household and Home Assistant treat this add-on as the live bridge to the
panel. After a session that was already monitoring, the panel path can die (for
example the usual health check goes unanswered). Today the app notices enough to
mark the panel-connection freshness signal off, but then stops trying — so
monitoring stays dead until someone restarts the add-on, even though the process
is still running. Zone and alarm last-known state remain visible, but freshness
never returns on its own. The household-facing name of that signal is also wrong
for how people read it: it is labelled as if the panel were “connected” as a
boolean fact, when what matters is the **connection**’s trustworthiness.

## Goal

When a mid-run panel session dies or stays untrustworthy, the add-on keeps
running and restores live monitoring on its own: **Alarm Panel Connection** stays
off while recovery is in progress or still failing, then returns to live with
zone/alarm state re-synced from the panel — without a manual add-on restart and
without blanking zone/alarm entities solely because recovery is underway. That
freshness entity’s friendly name in Home Assistant is **Alarm Panel Connection**
(replacing **Alarm Panel Connected**). Household alerts stay in Home Assistant
(e.g. automate on that signal); this app only makes the signal honest,
recoverable, and clearly named.

## Scope

**In scope**

- After a mid-run death (including when the usual health check goes unanswered),
  keep running and keep trying until monitoring is live again — no operator
  restart required.
- Soft-zombie / trust-degraded cases too: when the connection signal is already
  off because the path was untrustworthy while the process stayed up, still
  recover to a trustworthy live session without an operator restart.
- Keep **Alarm Panel Connection** truthful: off while recovering or still
  failing; on only after state is re-synced from the panel.
- Present that connectivity entity in Home Assistant with the friendly name
  **Alarm Panel Connection** (replacing **Alarm Panel Connected**).
- Keep zone and alarm entities available with last-known state during recovery
  (not unavailable solely for panel recovery).
- Keep failure visible: recovery attempts and failures are clear in everyday logs
  (not only TRACE); the connection signal does not look live while recovery is
  still failing.
- Keep trying with a patient cadence (not a tight silent spin); if the panel never
  becomes free, stay degraded and visible indefinitely.

**Out of scope**

- Home Assistant automations, notifications, or dashboards that react to the
  connection signal (household can alert there; this app does not own those
  rules).
- Automatically retrying the arm/disarm command that failed — heal the session;
  do not silently re-fire the user’s tap.
- Startup first-login backoff / never-exit on first connect — owned by
  `spec-startup-login-backoff.md` / `spec-continuous-operation.md`.
- Marking zone or alarm entities unavailable to mean “stale” — freshness stays on
  the connection signal only (`spec-panel-link-liveness.md`).
- Guaranteeing a live session while another client permanently holds the single
  panel connection — stay degraded and visible; success is not promised until the
  slot is free.
- Redefining how silent death is **detected** — detection remains owned by
  `spec-panel-link-liveness.md`; this spec covers **healing** after degrade or
  mid-run death, plus the Connection naming correction above.

## Acceptance Criteria

### AC1: Dead mid-run session heals without restart

Given monitoring was live, When the panel stops answering the usual health check
(e.g. keepalive goes unanswered), Then the add-on keeps running, **Alarm Panel
Connection** stays off while recovering, and when the panel accepts again
Connection returns to live with zone/alarm state re-synced — without an operator
restarting the add-on.

- **How we'll know:** end-to-end test (stand-in: FakePanel that dies mid-session
  then accepts again; recording MQTT broker)

### AC2: Soft-zombie / trust-degraded session also heals without restart

Given **Alarm Panel Connection** is off because the path was untrustworthy while
the process stayed up, When recovery succeeds, Then monitoring is live again with
zone/alarm state re-synced from the panel — without an operator restarting the
add-on.

- **How we'll know:** end-to-end test (stand-in: FakePanel trust-fail then
  recover; recording MQTT broker)

### AC3: Entities not blanked during recovery

Given **Alarm Panel Connection** is off during recovery, When Home Assistant
inspects zone and alarm entities, Then they stay available with last-known state
(not marked unavailable solely because of panel recovery).

- **How we'll know:** end-to-end test (stand-in: FakePanel + recording MQTT
  broker)

### AC4: Failure stays visible (no silent thrash / fake healthy)

Given recovery is still failing or retrying, When the household or automations
look at **Alarm Panel Connection** and the add-on logs, Then Connection remains
off until monitoring is truly live again, and recovery attempts/failures are
visible at normal log levels (not TRACE-only).

- **How we'll know:** end-to-end test (stand-in: FakePanel that refuses recovery
  for N attempts; assert MQTT connection signal off + log lines); optional manual
  acceptance test on live corroboration if needed

### AC5: Connectivity entity is named Alarm Panel Connection

Given MQTT discovery for the connectivity entity, When the household views it in
Home Assistant, Then its friendly name is **Alarm Panel Connection** (not
**Alarm Panel Connected**).

- **How we'll know:** unit test (discovery payload name assertion)

---

## User Stories

- As the household, I want monitoring to come back by itself after a mid-run panel
  death, with last zone/alarm still visible and **Alarm Panel Connection** telling
  me when the picture is trustworthy again, so I do not have to restart the
  add-on.
- As Home Assistant automations, I want **Alarm Panel Connection** to stay off
  while recovery is failing and return to on only when live again, so I can gate
  on that signal (and raise my own alerts) without treating stale state as
  current.
- As the household, I want that freshness entity labelled **Alarm Panel
  Connection**, so the name matches “is the connection trustworthy?” rather than
  a one-shot “connected” reading.

## Edge Cases

- Another client holds ComIP indefinitely: Connection stays off; zone/alarm stay
  available with last-known; app keeps trying patiently; live monitoring is not
  promised until the slot is free.
- Recovery succeeds after many failures: Connection stays off throughout; only
  after re-sync does it return to live — no premature “healthy” flicker.
- Soft trust degrade that later self-clears via a successful corroboration without
  a full session reset: still ends with Connection live and state current; this
  spec does not forbid that path, but does require healing when sitting forever
  off would otherwise need a human restart.
- True process crash: Watchdog may restart — last resort; not the design for
  panel-path death while the process is up.
- Competing clean disconnect recovery already required by
  `spec-panel-link-liveness.md` / continuous-operation: no regression — mid-run
  death that today aborts the listen cycle must join the same “keep trying”
  expectation.
- Existing installs still showing **Alarm Panel Connected**: discovery must
  present **Alarm Panel Connection**; any stuck old friendly name on an existing
  entity is an install/rediscovery concern, not a reason to keep the old label in
  new discovery payloads.

## Constraints

- Zone and alarm **availability** remain governed solely by whether the app
  process is running (MQTT Last-Will), never by panel-connection health.
- Connectivity / freshness remains a **separate** signal from entity availability.
- The panel accepts only one monitoring client at a time — recovery cannot assume
  a second simultaneous session.
- Patient retry cadence is required; exact intervals are plan/architecture
  territory (may align with existing mid-run reconnect patience, including
  asymmetric trigger budgets where those already apply).
- Fulfilling AC2 (heal while the path was untrustworthy but the process stayed up)
  may need a formal architecture decision before build if the mechanism is not
  already settled; this spec states the household outcome, not the wire mechanism.
- Friendly name **Alarm Panel Connection** supersedes the prior **Alarm Panel
  Connected** label from `spec-panel-link-liveness.md` for new discovery; changing
  Entity IDs is not required unless discovery already forces a rename for
  correctness.

## Open Questions

- ~~Whether AC2 always needs an active fresh session, or whether some trust-degrade
  shapes may keep recovering via successful corroboration alone~~ **Answered
  2026-08-09:** Prefer corroboration first; tear down and re-login only if still
  stuck after a bounded fail window. Exact bound and mechanism → `/adr` then
  architecture (extends the open follow-on left by silent-death detection).

## Spike Candidates

- ~~How mid-run health-check timeout should join existing clean-disconnect
  recovery~~ **Answered 2026-08-09:** Yes — treat unanswered health-check as a
  dead session and use the same keep-trying reconnect heal as a clean disconnect
  (no manual restart). Feasibility under FakePanel is ordinary build/CI work, not
  a research spike.
- ~~Whether trust-degrade heal (AC2) requires session tear-down and re-login~~
  **Answered 2026-08-09:** Corroboration first; tear down / re-login only if still
  stuck after a bounded fail window. Record via `/adr` before architecture.
- ~~Whether renaming the friendly name alone is enough vs `unique_id` / Entity ID~~
  **Answered 2026-08-09:** Clean refactor — no backwards compatibility. Friendly
  name **Alarm Panel Connection** and change `unique_id` / Entity ID as needed so
  HA does not keep the old Connected / Panel Link identity.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-09 | Issues found | 1 |
| 2 | 2026-08-09 | Clear | — |
