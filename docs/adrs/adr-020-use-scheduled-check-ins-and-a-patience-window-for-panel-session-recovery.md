# ADR-020: Use Scheduled Check-Ins and a Patience Window for Panel Session Recovery

**Status:** ~~Accepted~~ Superseded by [ADR-021](adr-021-use-one-busy-versus-dead-session-model-for-panel-connection-health.md)
**Date:** 2026-08-28
**Spike:** [spike-012-getdatetime-keepalive-reply-shape/SPIKE.md](../spikes/spike-012-getdatetime-keepalive-reply-shape/SPIKE.md)

## Overview

**Background:** The app checks in with the panel periodically to confirm the connection is
alive. Today a single refused or unanswered check-in ends the session within about a
second, and the app immediately reconnects. Live capture showed the panel refusing
check-ins during its own busy spells — bursts of activity it was reporting unprompted —
which produced repeated short disconnects on a connection that was never actually
broken. The check-in is also only sent when the line has gone quiet, so a genuinely busy
panel can go minutes without being asked anything at all.

**Decision:** Send check-ins on a fixed schedule regardless of how busy the panel is, and
stop treating one refusal as death. The session is declared dead only when the panel has
refused or ignored check-ins continuously for a set period, at which point the app
releases its own connection — within a bounded time, abandoning it forcibly if it will not
close — and logs in again, retrying for as long as it takes.

**Why this way:** Reconnecting on the first refusal gives up the panel's single connection
slot every time the panel has a busy moment, and that slot can be taken by something else
for an unbounded time. Waiting a little proved the cheaper risk. Measuring patience against
scheduled check-ins rather than against any incoming data matters because the panel has
been seen answering routine check-ins perfectly while refusing every real command — so
"data is still arriving" is not evidence the panel will do anything it is asked.

**What this constrains:**
- Check-ins must be sent on a fixed schedule measured in elapsed time, and must not be
  skipped, delayed, or starved because the panel is sending a lot of unprompted activity.
- The check-in schedule must not be tied to the separate background reconciliation poll's
  timing, so that changing the poll interval can never change how quickly a dead session
  is detected.
- A refused or unanswered check-in must not end the session on its own. The session is
  declared dead only once the panel has failed to answer a check-in properly for longer
  than a configured patience period.
- The check-in schedule must stay comfortably shorter than the panel's own tolerance for a
  connection it has not heard from, so scheduled check-ins alone are always enough to keep
  the session alive without relying on the panel's unprompted activity.
- The patience period ships defaulting to roughly three consecutive missed check-ins —
  long enough to ride out an activity burst of the length observed, short enough that a
  dead session is recovered in well under a minute.
- A connection that ends outright — the panel closing it, the panel signalling the end of
  the session, or data arriving that does not conform to the expected format — must still
  end the session immediately. Patience applies only to a check-in that was refused or
  went unanswered.
- Before reconnecting, the app must release its own connection within a bounded time and
  abandon it forcibly if it does not close cleanly, so the app can never lock itself out
  of the panel's single connection slot while waiting on a connection it has already
  given up on.
- Reconnecting continues to use one configured wait interval and retries indefinitely; no
  attempt cap and no second interval may be introduced.
- The panel-connection signal must stay on while the app is being patient, and go off when
  the session is declared dead, returning only after the app has logged in again and
  re-read the panel's current state. Zone and alarm entities must not be marked
  unavailable at any point in this — that remains governed only by whether the app itself
  is running.
- The separate watchdog for refused arm and disarm commands must be left intact: a
  rejected or timed-out command still degrades the panel-connection signal immediately and
  still runs its own independent countdown to a fresh login. It must not be merged into,
  or replaced by, the check-in patience period.
- The patience period, the check-in schedule, and the reconnect wait must all be
  install-time settings, not fixed values in the code.

**Open follow-ons:**
- Whether a refusal ever clears while the session is left open is still unknown — no
  refusal has ever been observed surviving longer than the old one-second teardown,
  because the app always gave up first. The patience period's value should be revisited
  once real behaviour under patience has been observed.
- Whether the household's phone app is configured against the same panel module as the
  add-on is unresolved, and remains the most likely cause of the long outages seen during
  investigation. That is an install question, not something this decision addresses.

## Context

Live capture against the household panel on 2026-08-28 established that the short reply
the panel sends instead of a datetime is a NAK — an explicit refusal — not the ACK the
code's test double and protocol reference had assumed. Every observed refusal followed a
burst of unsolicited `M` traffic, and in all four events the bounded same-sequence retry
budget introduced in 0.2.2 fired all three attempts back-to-back inside roughly one
second and never recovered the session. So the retry budget provides no meaningful
patience, while the teardown it precedes produced the 0.2.1-era pattern of repeated short
reconnects correlated with panel activity.

Two structural problems surfaced alongside it. First, the check-in is sent only from the
listen loop's idle-timeout branch, so while frames keep arriving inside the wait window no
check-in is sent at all; the only thing that eventually forces one is the reconciliation
poll, which defaults to 300 seconds. Any patience period measured as "time since the last
good check-in" would therefore expire on a demonstrably healthy, busy connection — and
would be coupled to a poll interval that ADR-017 deliberately freed from any
connectivity bound. Second, `close()` awaits `wait_closed()` with no timeout, so a
half-dead connection can stall the release step indefinitely; a diagnostic script that
failed to release its connection at all could not reconnect for 55 minutes, which is the
same shape that stall would produce in production.

This decision narrows ADR-016 rather than replacing it. ADR-016's trigger set stands
unchanged — failed check-ins and rejected commands degrade the panel-connection signal,
and the reconciliation poll still never feeds it. What changes is the bound: a refused or
unanswered check-in now takes the patience period to reach "down" instead of about a
second. ADR-016's separate requirement that the signal recovers automatically once
check-ins resume is strengthened, not weakened, since a refusal that clears within the
window now never shows as down at all.

It also closes an item ADR-011 left open — the trust-degrade fail window and heal cadence
being plan-time values — for the check-in path only, by requiring them to be settings. The
command-rejection path's own fail window is deliberately untouched.

## Decision drivers

- A busy panel refusing one check-in must not be treated as a dead session; the observed
  refusals correlate with the panel's own activity bursts, not with a broken connection.
- A genuinely dead or persistently refusing session must still be detected and recovered
  automatically with no manual restart, and must be acted on before the panel's own
  tolerance for an un-exercised connection expires.
- Liveness must be measured by the panel answering when asked, not by the panel sending
  data unprompted — a session has been observed answering check-ins while refusing every
  real command.
- The check-in schedule must not be starvable by heavy inbound traffic, and must not be
  coupled to the reconciliation poll's interval (ADR-017).
- The app must never hold a connection it has given up on, because the panel accepts only
  one at a time and losing that slot to another client is unbounded in duration.
- The household must not see the panel-connection signal flicker during short outages; a
  signal that flaps on momentary refusals will be ignored when it reports a real one.
- No attempt cap on reconnects (ADR-018) and no second reconnect interval (ADR-019).
- The tuning values must be install-time settings, not constants in the code (an item
  ADR-011 left open).
- The existing escalation from a refused arm or disarm command to a fresh login must
  survive this change intact (ADR-011).

## Options considered

- **Option A: Keep the current behaviour** — bounded same-sequence retries, then tear down
  on the first unrecovered refusal. Rejected because: the retries fire inside roughly one
  second and recovered nothing in 4 of 4 observed events, so they deliver no patience,
  while the teardown that follows makes a momentary refusal indistinguishable from death
  and gives up the single connection slot each time.
- **Option B: Tear down immediately on any refusal, with no retries at all** — reconnect
  as fast as possible on the theory that a degraded session should be abandoned at once.
  Rejected because: it maximises how often the app surrenders the panel's single
  connection slot, which another client can then hold for an unbounded period, and it
  guarantees the flickering connection signal the household explicitly does not want.
- **Option C (chosen): Scheduled check-ins with a patience window, bounded release before
  reconnect, and the command-rejection watchdog kept separate.**
- **Option D: One unified timer covering both refused check-ins and rejected commands.**
  Rejected because: the two failure shapes have opposite symptoms — a panel refusing every
  command typically answers check-ins perfectly — so a shared clock measuring check-in
  success would reset indefinitely in that case and the automatic fresh login would never
  fire, reintroducing the manual restart ADR-011 exists to remove.
- **Option E: Measure liveness as time since any valid frame arrived**, treating unprompted
  panel traffic as proof of health. Rejected because: it reproduces the 0.2.0 zombie, where
  the connection carried traffic all day while every command was refused, so it fails the
  driver that liveness must mean the panel answering when asked.

## Decision

Chosen option: **Option C.**

Scheduling the check-in is what makes the patience period mean anything: measured against
an idle-triggered check-in it would expire on a healthy busy connection, and measured
against inbound traffic it would never expire on a zombie. Sizing the window at a few
consecutive missed check-ins satisfies both the "don't treat a busy moment as death" and
"still detect real death" drivers without introducing a second reconnect interval or an
attempt cap. Bounding the release addresses the one failure
mode that can cost the connection slot indefinitely. Keeping the command-rejection watchdog
separate is what distinguishes this from Option D, and is required for ADR-011's
escalation to survive.

## Consequences

**Positive:** A refusal during a panel activity burst no longer ends the session, which
removes the repeated short-reconnect pattern the household reported and stops the app
surrendering its connection slot on every busy spell. The connection signal becomes
meaningful — it reports sustained trouble rather than momentary hiccups. The check-in
becomes independent of both inbound traffic volume and the reconciliation poll's interval,
so changing the poll setting can no longer affect how fast a dead session is detected. The
release path can no longer stall indefinitely, closing the self-lockout shape observed in
the diagnostic harness.

**Negative:** Detection of a genuinely refusing session widens from roughly a second to the
patience period. Throughout that period, per ADR-004, zone and alarm entities keep showing
their last-known values *and* the panel-connection signal reads healthy — so for the length
of the window the household has no indication at all that data may be stale. This is the
deliberate trade for not flickering, and it is a real erosion of the signal ADR-004 relies
on to make unconditional staleness safe. Anything that must not act on stale panel data
needs to tolerate a window of that length. The design also rests on an untested premise:
no refusal has ever been observed clearing while a session stayed open, because the app
always tore down first. If refusals never self-clear, the patience period buys nothing and
simply delays every recovery by its own length.

**Follow-on:** Implementation must move the check-in out of the listen loop's idle-timeout
branch onto its own schedule, replace the same-sequence retry burst with the patience
window, bound the release in the wire client, and add the three settings. The check-in
cadence and the retry budget are currently fixed values in the code, and the retry budget
is deliberately shared with login's own retry count — login's retries must be preserved
when the keepalive burst is removed, not dropped with it. `docs/architecture.md` cannot
correctly reflect this decision until updated via `/architecture` after this ADR is folded
into `AGENTS.md` via `/constitute`. The protocol reference's description of the check-in
reply and of the retry budget's purpose both need correcting for the NAK finding
independently of this decision.

**CI vs live:** A stand-in panel and hermetic tests may claim: that check-ins fire on
schedule under sustained inbound traffic and are not starved by it; that the schedule is
unaffected by the reconciliation poll interval; that a refused check-in inside the patience
period does not end the session and does not change the connection signal; that continuous
refusal past the window ends the session, releases the connection, publishes the signal
off, reconnects, and re-reads panel state; that an outright close or non-conforming data
still ends the session immediately; that release completes within its bound even when the
connection will not close cleanly; that the command-rejection watchdog still degrades
immediately and still escalates to a fresh login on its own timer; and that reconnect
still retries indefinitely at one interval per ADR-018/ADR-019. It may **not** claim that
patience recovers a refusing session: the stand-in models a refusal as sticky until
re-login by construction, so no hermetic test can demonstrate self-clearing. Whether real
refusals clear within the window, and whether the household's long outages were a
competing client rather than an app defect, remain live-only validation at `/accept`.

## Confirmation

This decision is correctly implemented when: (1) check-ins are sent on a fixed elapsed-time
schedule that heavy inbound panel traffic cannot starve and that does not depend on the
reconciliation poll interval; (2) a refused or unanswered check-in leaves the session and
the panel-connection signal untouched, and only continuous failure past the configured
patience period declares the session dead; (3) an outright disconnect, an end-of-session
signal from the panel, or non-conforming data still ends the session immediately; (4) the
release step before reconnect is bounded and forcibly abandons a connection that will not
close, with reconnect still retrying indefinitely at one interval; (5) the
panel-connection signal reads healthy throughout the patience period, goes off at
declare-dead, and returns only after re-login and state re-read, with zone and alarm
entities never marked unavailable by any of it; (6) the command-rejection watchdog retains
its own immediate degrade and its own independent countdown to a fresh login; and (7) the
patience period, check-in cadence, and reconnect wait are all install-time settings, with
login's retry budget preserved.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
