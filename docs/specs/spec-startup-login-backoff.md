# Spec: startup-login-backoff

**Date:** 2026-08-07  
**State:** Accepted ✅

---

## Problem

When the add-on starts (or restarts) while the panel is still releasing a previous
session or is briefly unresponsive, the app retries login often enough that the
panel can look overwhelmed — long stretches of failed attempts, closed sockets,
and delayed recovery — even though the app correctly stays running and keeps
trying. Operators watching logs see rapid-fire failed attempts and cannot tell
whether the add-on is still making progress or stuck.

## Goal

After a failed panel connect or login at startup, the add-on waits progressively
longer before the next try (up to a documented maximum), so the panel is not
hammered while settling, while still recovering without a human restart once the
panel accepts the session again.

## Scope

**In scope**

- Startup (and first-login) recovery waits grow longer after repeated failures,
  instead of using one short fixed pause forever.
- A maximum wait between attempts so recovery does not become arbitrarily slow.
- Clear log lines that state how long the add-on will wait before the next try
  (so an operator reading logs can tell patience from a hang).
- Behaviour applies to the path that keeps the process alive while the first
  successful panel login has not yet happened (including after an add-on
  restart).

**Out of scope**

- Changing how the add-on recovers after a session that was already healthy and
  then dropped mid-run (that path already has its own patience rules; this spec
  does not redefine them).
- Fixing cases where the panel accepts arm/disarm but Home Assistant alarm state
  does not follow (separate reliability gap).
- Detecting “zombie” live sessions or renaming connectivity labels (owned by
  panel-link-liveness).
- Making TRACE dump every ignored panel event (diagnostics-logging / hunt
  tooling, not this backoff behaviour).

## Acceptance Criteria

### AC1: Waits grow after repeated startup login failures

Given the panel rejects or does not complete connect/login on startup, When the
add-on retries, Then the pause before each later attempt is longer than the pause
before the previous attempt (until the maximum wait is reached).

- **How we'll know:** integration test (stand-in: FakePanel that fails login for
  N attempts then succeeds; assert recorded wait intervals are strictly
  non-decreasing and increase at least once)

### AC2: Maximum wait is capped

Given many consecutive startup login failures, When the add-on continues
retrying, Then the pause between attempts does not exceed **30 seconds**, and
once that cap is reached further waits stay at 30 seconds (never longer).

- **How we'll know:** integration test (stand-in: FakePanel that fails login
  indefinitely for a fixed number of attempts; assert no recorded wait exceeds
  30 seconds and that waits remain at the cap after it is reached)

### AC3: Recovery still completes without a human restart

Given a stretch of failed startup logins under the backoff schedule, When the
panel later accepts login, Then the add-on proceeds into normal monitoring
(entities populated / panel path live) without the operator restarting the
add-on.

- **How we'll know:** integration test (stand-in: FakePanel fails login several
  times then succeeds; assert monitoring startup completes after success)

### AC4: Logs show the next wait

Given a failed startup login attempt, When the add-on schedules the next try,
Then the log includes the wait duration that will be used before the next try.

- **How we'll know:** integration test (stand-in: FakePanel + captured logs;
  assert the ERROR/INFO recovery line names the wait interval)

## User Stories

- As the household operator, I want the add-on to back off when the panel is
  busy at restart so recovery feels patient rather than aggressive.
- As someone reading add-on logs at TRACE/INFO, I want to see how long until the
  next login try so I can tell “waiting” from “stuck.”

## Edge Cases

- Panel never becomes free (another client holds it indefinitely): backoff still
  applies; the add-on keeps trying under the cap; success is not promised until
  the slot is free (same limit as continuous-operation).
- First attempt succeeds: no backoff delay is required before monitoring starts.
- Failure after a wait already at the maximum: keep using the maximum between
  further attempts until success.

## Constraints

- Must not defeat continuous-operation: the process must keep running and keep
  retrying; backoff changes timing only, not “give up and exit.”
- **Default wait schedule (documented):** after the *k*-th failed startup
  connect/login (`k = 1, 2, 3, …`), wait `min(5 × 2^(k-1), 30)` seconds before
  the next try — i.e. **5 s → 10 s → 20 s → 30 s**, then **30 s** forever until
  success. Cap is **30 seconds**; never wait longer; never give up.
- Schedule is soft-double then flat (not uncapped exponential): only a few
  increasing steps, then a steady patient interval.

## Cross-links

- Builds on Accepted [`spec-continuous-operation.md`](spec-continuous-operation.md)
  (keep trying; do not exit on first login failure).
- Distinct from Draft [`spec-panel-link-liveness.md`](spec-panel-link-liveness.md)
  (truthful connectivity after a session looked healthy).

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-07 | Issues found | 2 |
| 2 | 2026-08-07 | Clear | — |
| 3 | 2026-08-07 | Clear | — |
