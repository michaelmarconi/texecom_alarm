# ADR-010: Use Command-Reject Events and Periodic House-State Polling for Silent Panel-Path Death Detection

**Status:** ~~Accepted~~ Superseded by [ADR-016](adr-016-use-keepalive-failure-and-command-reject-events-for-panel-connection-detection.md)
**Date:** 2026-08-08  
**Spike:** [spike-008-silent-panel-path-death-detection/SPIKE.md](../spikes/spike-008-silent-panel-path-death-detection/SPIKE.md)

## Overview

**Background:** The household can see “Alarm Panel Connected” while arm or disarm
quietly fails and the app looks stuck — the idle heartbeat can still succeed, so a
clean disconnect is not the only failure mode that matters.
**Decision:** Treat a rejected or timed-out arm/disarm as an immediate signal that the
panel link may be untrustworthy, and separately poll the panel for current house/arm
state on a bounded interval as a trust check — alongside the existing idle heartbeat,
not instead of it. Do not judge freshness from “zones went quiet” alone.
**Why this way:** Quiet houses falsely look dead if silence is the only signal; a
heartbeat-only check misses the case where the link answers keepalives but rejects
commands. The combination was the only approach that caught both silent stalls and
command-path zombies in SPIKE-008 without quiet-house false alarms in the comparison.
**What this constrains:**
- Alarm Panel Connected must go degraded on arm/disarm reject or timeout even when the
  idle heartbeat still succeeds.
- The app must periodically ask the panel for current house/arm state as a
  corroboration poll; that poll must not replace the idle heartbeat.
- Missing zone push traffic alone must not be the sole reason to mark the link
  degraded.
- After a brief reject, the link may return to live automatically once corroboration
  succeeds and no recent command failure remains — without requiring a manual add-on
  restart.
- Zone and alarm entities stay available with last-known state while the link is
  degraded (unchanged from the earlier availability decision).
**Open follow-ons:**
- Exact poll interval, recover window, and “tens of seconds” bound — settle at plan
  time unless live walks force a change.
- Whether session tear-down and re-login run automatically on degrade, and whether the
  failed command is auto-retried inside one user tap (explicitly not decided here).
- Narrower classification of honest panel rejects vs zombie rejects before aggressive
  auto-retry.
- Live quiet-house and live zombie corroboration after implementation.

## Context

Accepted panel-link liveness requires a truthful live-vs-degraded connectivity signal
when a previously healthy panel session stops delivering trustworthy updates — including
silent failure, not only clean disconnects — without blanking zone/alarm entities
(ADR-004). Today connectivity flips degraded mainly on forced disconnect/reconnect;
idle heartbeat success still reports live. Live walks showed arm rejects while
keepalives continued (“command-path zombie”), and showed that the official smartphone
app does not monopolise the local session once this app holds it. SPIKE-008 compared
detection approaches on hermetic timelines matching quiet house, silent death,
command-path zombie, clean disconnect, and transient single reject.

## Decision drivers

- Detect command-path zombies (rejects while heartbeat still succeeds) within tens of
  seconds so automations do not trust a lying “connected” signal.
- Detect silent stalls / failed trust checks within tens of seconds after a session
  looked healthy.
- Avoid false degraded on a quiet house with no zone activity for long periods.
- Preserve ADR-004: zone/alarm availability stays app-process-based; freshness is only
  the separate connectivity signal.
- Prefer mechanisms FakePanel / hermetic tests can regress; leave live-only what only a
  real house can prove.
- Keep the existing idle heartbeat for session keep-alive; do not invent a
  traffic-silence-only detector as the product answer.

## Options considered

- **Traffic-absence alone** — degrade when zone/area/log pushes are quiet for N
  seconds. Rejected because: SPIKE-008 quiet-house timeline false-degraded with no zone
  activity, and the command-path zombie stayed “live” while non-zone traffic continued —
  against drivers for quiet-house false positives and zombie detection.
- **Idle-probe failure alone** — degrade only when the idle heartbeat fails. Rejected
  because: SPIKE-008 command-path zombie stayed live through repeated arm rejects with
  successful keepalives — against the zombie-detection driver.
- **Periodic house-state corroboration alone** — timed panel state reads; degrade on
  poll failure. Rejected as a *sole* mechanism because: without a command-reject signal
  it still misses “reads OK, arm reject” zombies — against the zombie-detection driver
  (retained as a *component* of the chosen option).
- **Combination (command-reject event + periodic house-state poll)** — immediate
  degraded on arm/disarm reject or timeout; periodic house/arm state poll alongside the
  idle heartbeat; recover after successful poll with no recent command failure.

## Decision

Chosen option: **Combination (command-reject event + periodic house-state poll)**

Arm/disarm reject or command timeout is an immediate degrade *event* even when the idle
heartbeat still succeeds. Separately, the app periodically polls panel house/arm state
as a trust check (alongside, not replacing, the idle heartbeat) and degrades on poll
failure. Traffic silence alone is not a sole degrade criterion. Return to live after
successful corroboration once the recent-command-failure window has cleared, without
requiring a manual add-on restart. Numeric intervals settle at plan/build time.

## Consequences

**Positive:** Alarm Panel Connected can tell the truth for both silent stalls and
command-path zombies; quiet houses need not look degraded merely from inactivity;
hermetic comparison scenarios are regressible in CI once wired to FakePanel.

**Negative:** A legitimate single panel reject can briefly mark the link degraded until
corroboration recovers; periodic polls add round-trips on the single panel session;
implementers must not confuse heartbeat keep-alive with trust corroboration.

**Follow-on:** Plan/build implements Combination under `spec-panel-link-liveness` /
DRAFT-1. Session tear-down/re-login on degrade and in-tap command auto-retry remain open
product choices (not fixed here). Exact poll/recover bounds and live corroboration walks
remain open.

**CI vs live (when this decision is about an outside system / protocol):** Hermetic
simulator / FakePanel may claim detector behaviour for quiet-house false degrade,
command-path zombie, silent death, clean disconnect, and transient-reject recovery
shapes from SPIKE-008. Live-only: real quiet-house overnight false-positive rate, real
zombie reproduction, and reconnect UX after degrade on the household panel.

## Confirmation

- Hermetic or FakePanel tests: Combination degrades on arm/disarm reject while heartbeat
  still succeeds; degrades on failed house-state poll / silent-death shape; does not
  degrade on quiet-house (no zone traffic) alone; recovers after transient reject once
  corroboration succeeds past the recover window — without marking zone/alarm entities
  unavailable solely for panel-path degrade.
- Live `/accept`: optional quiet-house and zombie walks corroborate; they are not
  required for CI to claim the detector shapes above.
