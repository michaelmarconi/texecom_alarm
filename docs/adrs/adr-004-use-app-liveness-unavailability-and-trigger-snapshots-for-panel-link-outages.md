# ADR-004: Use App-Liveness Unavailability and Trigger Snapshots for Panel-Link Outages

**Status:** Accepted ✅
**Date:** 2026-08-03

## Overview

**Background:** When the panel genuinely triggers, it also force-drops the very
connection this app depends on to report anything at all (confirmed empirically in
SPIKE-002). The project's specs, as originally written, said the resulting outage
should show up to the household as the alarm system going "unavailable" — right at
the one moment they most need to see it.
**Decision:** The app never marks its alarm or zone entities unavailable because of a
panel-connection problem — only if the app itself stops running. A separate signal
tells the household when the panel link itself is degraded, and the app keeps a short
memory of the events leading up to a trigger so there's still an immediate, if not
live, picture of what happened.
**Why this way:** Auto-hiding the display after a timeout still fails at exactly the
moment that matters most, since the one real trigger observed so far already outlasted
what would be a reasonable timeout. Keeping the last-known state visible
unconditionally, and giving the outage its own honest, separate signal instead, avoids
ever hiding the most safety-critical information at the worst possible time.
**What this constrains:**
- The app's alarm and zone entities must never be marked unavailable because the panel
  connection dropped — only the app process itself being down can do that.
- The app must publish a separate, dedicated signal for panel-link health, distinct
  from the entities' own state, so the household and its automations can tell live
  data from stale data.
- The app must keep a short rolling memory of recent zone/panel activity so it can
  produce a "what happened right before this trigger" snapshot that survives a
  subsequent outage.
**Open follow-ons:**
- Whether reducing what else shares the panel's Com Port also shortens the
  trigger-time outage itself is still open — tracked as a new spike candidate.
- Whether extremely long-lived staleness should still eventually escalate to
  unavailable, and after how long, is left as an implementation detail, not fixed
  here.

## Context

The project's alarm-control and zone-monitoring specs originally required panel/network
connection drops to mark the affected entities "unavailable," specifically to avoid
"silently freezing on a stale value." Separately, `spec-alarm-control.md`'s own
Acceptance Criterion required the `alarm_control_panel` entity to report `triggered`
"throughout" a real trigger event — already in quiet tension with the unavailable
requirement, since SPIKE-002 confirmed the panel forces a TCP disconnect at the exact
moment a real trigger occurs, with the observed recovery window (~50s in the one
captured case) long enough that "unavailable" would be the dominant visible state for
the household during precisely the event they most need visibility into. A `/correction`
pass preceding this ADR already updated both specs' Edge Cases, Scope, and Acceptance
Criteria to reflect the resolution recorded here.

## Decision drivers

- The household must retain the alarm's last known state — especially `triggered` —
  at the exact moment they need it most, not lose it to a generic "unavailable" state.
- Entity availability must reflect whether the app itself is running, not be conflated
  with transient upstream panel-link health, since SPIKE-002 confirmed the panel forces
  a disconnect specifically at trigger time — the worst possible moment to also blank
  the primary entities.
- Panel-link health must still be surfaced somehow, so the household and its
  automations can distinguish live data from stale-but-last-known data, rather than
  degraded connectivity being silently hidden.
- The design must not require guessing at new panel-side behaviour or protocol
  commands — it only changes how already-decoded state is surfaced to Home Assistant.

## Options considered

- **Status quo — mark entities "unavailable" immediately on any panel connection
  drop.** Rejected because: it blanks the single most safety-critical piece of
  information (the `triggered` state) at precisely the moment SPIKE-002 confirmed the
  panel forces a disconnect — during a real alarm — directly against the driver that
  the household must retain visibility exactly then.
- **Tiered timeout — keep last-known state initially, but auto-escalate to
  "unavailable" if the outage exceeds a configured bound.** Rejected because it
  reintroduces the same problem on a delay: SPIKE-002 measured a real trigger's
  disruption window at ~50s and still climbing, so any reasonably short timeout would
  still blank the display at exactly the scenario that matters most, only slightly
  later.
- **App-liveness-only availability, plus a dedicated connectivity/freshness signal and
  a persisted trigger snapshot.**

## Decision

Chosen option: **App-liveness-only availability, plus a dedicated connectivity/freshness signal and a persisted trigger snapshot.**

This is the only option that keeps the alarm/zone entities' last-known state visible
unconditionally through any panel-link outage (satisfying the primary driver), while
still honestly surfacing degraded connectivity through a separate signal (satisfying
the "don't silently hide degraded link" driver) and giving the household immediate
context about what caused a trigger via the persisted snapshot — all without touching
panel-side protocol behaviour, since app-offline detection continues to rely on MQTT's
own standard availability/Last-Will mechanism (satisfying the "no guessing at new
panel behaviour" driver).

## Consequences

**Positive:** The household never loses sight of the alarm/zone entities' last known
state, including through the exact disruption event that matters most. The
"reconnecting" signal survives as its own honest, separate indicator rather than being
conflated with entity state. The trigger snapshot gives immediate context ("what set
it off") even if reconnection takes the full observed window to complete. Using MQTT's
own Last-Will mechanism for "is the app itself alive" is the standard, idiomatic
approach, so this doesn't require inventing new plumbing.

**Negative:** Home Assistant can show a stale value for as long as an outage lasts,
with currency communicated only via the separate connectivity `binary_sensor` —
anyone not watching that secondary entity could reasonably, if incorrectly, assume the
primary state is current. The app must maintain a small in-memory rolling buffer of
recent zone/log activity solely to produce the trigger snapshot, adding a little state
and complexity beyond an otherwise-stateless decode/publish loop. This decision doesn't
shorten the underlying outage itself, only changes its visible consequence.

**Follow-on:** Whether isolating the panel's Com Port from ARC/reporting traffic
(ADR-002's Option B) also shortens the trigger-time outage itself remains open —
tracked as a new Spike Candidate in `spec-alarm-control.md`. The exact bound (if any)
past which extremely stale data should still escalate to "unavailable" is not fixed by
this decision — left as an implementation-level tuning parameter, not a hard
architectural requirement.

## Confirmation

The built app's `alarm_control_panel` entity and every zone `binary_sensor` entity
must: (a) never transition to `unavailable` due to panel-link/reconnect activity —
verified by observing their last known state hold steady through a full deliberate
disconnect/reconnect cycle while the app process itself keeps running; (b) transition
to `unavailable` only when the app process itself stops or its MQTT connection drops
(verified via its Last-Will payload firing); (c) publish a distinct
connectivity/freshness `binary_sensor` that flips to degraded during a panel-link
outage and back on reconnect; and (d) publish a "last trigger" snapshot attribute
(initiating zone + timestamp) immediately on detecting an `in alarm`/`Alarm Active`
transition, remaining readable throughout a subsequent reconnect window.
