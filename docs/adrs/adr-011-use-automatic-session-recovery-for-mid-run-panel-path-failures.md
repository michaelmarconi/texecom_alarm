# ADR-011: Use Automatic Session Recovery for Mid-Run Panel Path Failures

**Status:** ~~Accepted~~ Superseded by [ADR-021](adr-021-use-one-busy-versus-dead-session-model-for-panel-connection-health.md)  
**Date:** 2026-08-09  

## Overview

**Background:** After the add-on is already monitoring, the panel path can die or
go untrustworthy. Detection can mark the connection signal off, but tonight a
dead health-check stopped the listen loop entirely — so monitoring sat broken
until a human restarted the add-on, even though the process was still running.
**Decision:** Use automatic session recovery after mid-run panel failure —
reconnect when the health check dies, and open a fresh login only when trust
stays broken after a short corroboration window.
**Why this way:** Doing nothing after OFF leaves the house on stale data forever.
Re-logging in on every brief trust glitch is heavier than needed when the next
check can clear it. Never re-logging in leaves true stuck sessions needing a
human again.
**What this constrains:**
- An unanswered mid-run health check must enter the same keep-trying recovery
  path as a clean panel drop — connection signal off while recovering; live again
  with state re-synced when the panel accepts — without a manual add-on restart.
- Soft trust failures may try corroboration first; if still stuck after a bounded
  fail window, the app must tear down and log in again (still no manual restart).
- Zone and alarm entities must not be blanked solely because recovery is running;
  freshness stays on the connection signal.
- A failed arm/disarm tap must not be automatically re-fired as part of heal.
**Open follow-ons:**
- Exact length of the “still stuck” fail window before tear-down/re-login (settle
  at plan time unless live walks force a change).
- Exact patient retry cadence may align with existing mid-run reconnect budgets;
  do not treat those budgets as newly finalised here.

## Context

Silent-death detection already tells the household when the panel path is
untrustworthy while the app process stays up. That does not by itself restore
monitoring. Live observation showed two shapes: a brief trust-poll timeout that
cleared on the next successful check, and a health-check timeout that marked the
connection off then aborted the listen cycle with no further recovery. The
household outcome required by session-heal is continuity without an operator
restart; ADR-010 left automatic tear-down/re-login and in-tap command retry
explicitly open. This ADR settles recovery behaviour for those mid-run failures
(not detection, and not startup first-login backoff).

## Decision drivers

- After a session that was already monitoring, mid-run panel death or stuck
  untrustworthiness must not require a manual add-on restart to restore live
  monitoring.
- Brief, self-clearing trust glitches should not force a full session tear-down
  when corroboration can restore trust.
- True stuck sessions must not sit forever OFF with no further attempt beyond
  waiting for a human.
- Zone/alarm last-known state must remain visible during recovery; freshness is
  communicated only via the connection signal.
- Recovery must not silently re-issue a user arm/disarm that already failed.
- CI must be able to prove heal shapes with a panel stand-in; live corroboration
  remains separate.

## Options considered

- **Option A: Detection only (mark OFF and stop trying)** — surface untrustworthy
  path; leave recovery to a human restart. Rejected because: violates the
  continuity driver; live health-check death already left monitoring stuck until
  restart.
- **Option B: Always tear down and re-login on any trust failure** — every failed
  poll or command-path reject immediately opens a fresh session. Rejected because:
  heavier than needed for brief glitches that clear on the next corroboration
  (observed live).
- **Option C: Corroboration forever, never re-login** — keep asking for house/arm
  state; never tear down the session. Rejected because: true stuck zombies can
  remain broken while the process stays up, still needing a human restart.
- **Option D: Automatic session recovery — reconnect on health-check death;
  corroboration first on soft trust-fail, then bounded tear-down/re-login if still
  stuck; no arm/disarm auto-retry.**

## Decision

Chosen option: **Option D**

When mid-run health-check traffic goes unanswered, treat the session as dead and
enter the same keep-trying reconnect recovery used after a clean panel drop:
connection signal stays off while recovering; when the panel accepts again,
re-sync zone/alarm state and return the signal to live — without a manual restart.
When the path is untrustworthy but not necessarily fully dead, prefer trust
corroboration first; if still stuck after a bounded fail window, tear down and
log in again. Do not automatically retry the failed arm/disarm command. This
satisfies continuity without over-reacting to brief glitches and without leaving
zombies forever.

## Consequences

**Positive:** Mid-run panel death and stuck trust-degrade heal without an operator
restart; brief glitches can clear lightly; connection signal stays honest while
recovery runs; zone/alarm last-known remains visible for dashboards and gating.

**Negative:** Bounded re-login adds session churn when trust stays bad; wrong fail
window can either thrash (too short) or leave OFF longer than ideal (too long);
implementers must wire health-check timeout into reconnect rather than aborting
the listen loop.

**Follow-on:** Exact fail-window length and how patient retry cadence lines up with
existing mid-run reconnect budgets remain plan-time (and may need live tuning).
In-tap auto-retry of a failed arm/disarm remains out of scope. Naming the
connection entity **Alarm Panel Connection** is a separate product rename, not
decided by this ADR’s recovery mechanism.

**CI vs live:** FakePanel may claim health-check-timeout → reconnect-heal,
trust-fail → corroboration recover, and trust-fail → bounded re-login after stuck
window. Live quiet-house / zombie / ComIP-contention heal behaviour remains
`/accept` corroboration — green CI is not product accept.

## Confirmation

This decision is correctly implemented when:

- A FakePanel (or equivalent stand-in) that answers monitoring then stops answering
  the mid-run health check causes keep-trying recovery and returns to live with
  re-synced state without process exit or manual restart.
- A stand-in trust-fail that later corroborates successfully returns to live
  without an unnecessary full re-login when corroboration alone suffices.
- A stand-in that stays untrustworthy past the fail window performs tear-down and
  re-login and returns to live without a manual restart.
- Zone/alarm entities are not marked unavailable solely during recovery; the
  connection signal stays off until live again.
- Failed arm/disarm is not auto-retried as part of heal.
- Live household corroboration of heal under real ComIP remains optional
  accept-walk, not a CI dependency.
