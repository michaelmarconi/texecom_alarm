# ADR-021: Use One Busy-Versus-Dead Session Model for Panel Connection Health

**Status:** ~~Accepted~~ Superseded by [ADR-022](adr-022-use-one-busy-versus-dead-session-model-including-late-command-replies-for-panel-connection-health.md)
**Date:** 2026-08-30
**Supersedes:** ADR-011, ADR-016, ADR-018, ADR-019, ADR-020

## Overview

**Background:** The add-on has been accumulating a new recovery rule after every live
incident — one for a refused check-in during a busy spell, one for odd bytes on the
wrong module, one for a follow-up read after arm or disarm. Those rules now disagree:
the same panel being busy is treated as harmless for check-ins and as a lost
connection for a housekeeping read. On 2026-08-30 a garage-return disarm succeeded,
then Alarm Panel Connection went off for about nine seconds because a follow-up read
did not parse.
**Decision:** Use one model for the whole session: the panel being busy is not the
same as the panel being gone. Alarm Panel Connection means we cannot talk to the
panel. It does not mean we stubbed our toe while it was still talking.
**Why this way:** Patching only the last command that failed will mint the next
incident. Restoring “skip junk on the wire” would bring back the old modem-line
workaround, which this household is not on. One model covers check-ins, arm and
disarm, follow-up reads, and reconnect without a new special case each time.
**What this constrains:**
- Alarm Panel Connection goes off only when we cannot talk: the panel hung up, it
  signalled the end of the session, check-ins have failed for the whole patience
  window, or an arm or disarm was rejected or timed out.
- A command that already succeeded must not be recorded as a connection failure if a
  later housekeeping read then misparses.
- While the panel is sending events, do not pile on extra questions whose answer
  already arrived as a live update. Required check-ins still go out on their clock
  even when the line is busy.
- After login, and again after a reconnect login, still re-read current zone and
  alarm state before trusting entity state.
- Never skip unexpected bytes hoping to find the next valid message. If the stream
  is unusable, close it cleanly and log in again — do not scan forward.
- Reconnect uses one wait interval, keeps trying with no attempt cap, and must
  release the old connection within a bounded time so this app cannot sit on the
  panel’s single slot.
- A refused arm or disarm still turns Connection off immediately and still has its
  own countdown to a fresh login. That clock must not be merged into check-in
  patience.
- Check-in timing must not be tied to the background state-reconciliation poll.
- Zone and alarm entities stay visible during all of this; only the app process
  dying can mark them unavailable.
- Recovery must not silently re-issue an arm or disarm the household already saw
  fail.
- When a read does not parse, log why and enough of the arriving bytes to tell a
  torn message from a hung-up connection.
**Open follow-ons:**
- Whether a refused check-in ever starts succeeding again if the session is left
  open (patience has not been observed live for that).
- Whether a competing client on the same module caused the long outages seen during
  earlier investigation — an install question, not a new recovery rule.
- The exact bytes from the 2026-08-30 parse miss were not logged; the first live
  miss after this diagnostic lands should confirm a torn message versus something
  else. That does not block this decision.

## Context

Five accepted ADRs currently describe pieces of the same job: recover mid-run
without a human restart (ADR-011), decide when Alarm Panel Connection goes off
(ADR-016), retry forever on one wait interval with no fake “attempts” knob
(ADR-018 / ADR-019), never skip non-protocol bytes (ADR-019), and ride out a
refused check-in for a patience window rather than tearing down in about a second
(ADR-020). Each was a correct answer to the incident in front of it. Together they
are hard to apply, and they conflict on what “the panel sent something we did not
expect” means.

Live evidence already separates three situations this app had been collapsing:

1. **Dead session** — TCP close, the panel’s end-of-session marker (`+++`), or
   check-ins refused/unanswered for the whole patience window. SPIKE-010 showed the
   dedicated local module staying up through Home arm, disarm, and a real trigger;
   an outright close is still possible and must still recover by itself.
2. **Busy panel** — unsolicited event frames (`M`) and occasional NAK on a
   check-in (`GETDATETIME`) while the socket is fine. SPIKE-012 and the 2026-08-28
   capture showed a busy spell is not a broken link. ADR-020 already treats that
   as “not death” for check-ins only.
3. **Follow-up we chose to send** — after a successful `SETAREADISARM` ACK on
   2026-08-30 12:27 BST, the add-on immediately issued `GetAreaFlags`. The panel
   had already pushed AREA disarmed and a disarm LOG marker. The next read failed
   `try_decode_frame` with no `panel_rx` line. That was mapped to
   `disarm_disconnect` and Connection went off for ~9 seconds. Keepalives
   immediately before were healthy. Reconnect succeeded on attempt 1. The
   household is on the dedicated local module (ADR-013), not the installer
   signalling module, so this was not Hayes modem text on a shared line.

ADR-009 still requires a flags snapshot after login and after reconnect login.
It does not require an immediate flags read in the same breath as a successful
arm or disarm when live AREA/LOG already published the new alarm state. ADR-004,
ADR-013, and ADR-017 are not replaced: entities stay available; the local module
is still required; the reconciliation poll still does not feed Connection.

## Decision drivers

- One session-health story must cover check-ins, arm/disarm, housekeeping reads,
  parse failures, and reconnect — not a new exception per incident.
- Alarm Panel Connection must mean “we cannot talk to the panel,” with a false
  off after a successful disarm treated as a failure of this decision.
- A busy panel (events in flight, a single refused check-in) must not be handled
  as a dead session.
- A dead session must still recover without a manual add-on restart, and must
  still turn Connection off while it is actually gone.
- Arm or disarm that is rejected or times out must still be visible immediately
  on Connection, and must not be swallowed by check-in patience (a panel can
  answer check-ins while refusing commands).
- The parser must not skip unexpected bytes. Dedicated-module installs must not
  re-acquire the old shared-module line-noise workaround.
- Reconnect must keep trying indefinitely on one wait interval, and must not
  hold the panel’s single connection slot on a socket already given up.
- Zone and alarm last-known state stay visible; freshness is Connection, not
  entity availability.
- CI may prove the state machine against FakePanel; live walks remain the proof
  that a real busy disarm does not flap Connection.

## Options considered

- **Option A: Keep ADR-011/016/018/019/020 and patch the last command only**
  (skip post-disarm `GetAreaFlags` when AREA already arrived, maybe add hex
  logs). Rejected because: fails the one-story driver; the next extra command
  into a burst becomes the next “disconnect.”
- **Option B: Restore skip-and-resync (ADR-002 / ADR-014)** — scan forward past
  non-conforming bytes and keep parsing. Rejected because: that defence existed
  for Hayes text on the signalling module; this household is on the dedicated
  module; skipping junk hides a torn Connect frame instead of resetting the
  stream.
- **Option C: Treat every parse miss as a check-in miss and fold it into the
  patience window** — one clock for NAK, timeout, and bad bytes. Rejected
  because: a panel that answers check-ins while refusing arm/disarm would keep
  resetting a shared clock, so the automatic fresh login would never fire
  (the reason ADR-020 kept two clocks).
- **Option D: One busy-versus-dead session model** — Connection off only when
  we cannot talk; no extra commands into a burst when live events already
  answered; parse miss after a successful command is a collision to resync,
  not that command failing; check-in patience and the command-reject watchdog
  stay as two clocks; never skip bytes; one reconnect interval, indefinite
  retry, bounded release.

## Decision

Chosen option: **Option D — one busy-versus-dead session model**

This is the only option that stops minting per-incident rules (driver 1), makes
Connection match “cannot talk” (driver 2), and still keeps busy-panel patience,
immediate command-reject, no byte-skip, and keep-trying reconnect (drivers 3–7).

### What “cannot talk” means (Connection off)

Publish Alarm Panel Connection **off**, then recover, when any of these hold:

- The panel closed the TCP connection, or a read returns no data because the
  peer went away.
- The panel sent the end-of-session marker `+++`.
- Check-ins (`GETDATETIME`) have been refused (`NAK`) or unanswered
  continuously for longer than the configured patience period.
- An arm or disarm command (`SETAREAARM` / `SETAREADISARM`) was NAK’d or timed
  out. Connection goes off **immediately**. A separate watchdog still counts
  down to a fresh login if that failure stays stuck; that countdown must not
  share the check-in patience clock.

Connection stays **on** while the app is being patient with check-ins, and
through a **collision resync** (below) that re-logs in successfully on the
first attempt. Connection returns to on after a real dead-session recovery
only once login has succeeded and zone plus area snapshots have been
re-read (ADR-006 / ADR-009 — those ADRs remain in force).

The background reconciliation poll (ADR-017) still must not feed Connection.

### Busy is not dead — commands during chatter

Check-ins stay on a **fixed elapsed-time schedule**. Inbound event traffic
must not skip, delay, or starve them. Unprompted traffic is not proof the
session will accept commands. The check-in interval must stay independent of
the reconciliation poll interval, and comfortably shorter than the panel’s
own idle drop, so check-ins alone keep the session alive.

After a successful arm or disarm ACK, do **not** immediately send a
housekeeping read (`GetAreaFlags` today) when live AREA/LOG (or equivalent)
has already published the new alarm MQTT state. The Home-disarm case where
the panel omits an AREA push still needs a flags read — that is the exception,
not the default timing. Snapshots after login and after reconnect login
remain mandatory (ADR-009 / ADR-006).

Recovery must not automatically re-send an arm or disarm that already failed.

### Parse miss — collision versus hung up

Do **not** skip non-conforming bytes and continue parsing. `try_decode_frame`
returning no frame with a positive consume count is never a licence to delete
one byte and hunt for `'t'`.

Classify instead:

- **Hung up:** peer close, empty read, or `+++` → dead session; Connection
  off; bounded release; reconnect.
- **Collision:** TCP still open; decode failed (bad start byte, illegal
  length, bad CRC, unknown type) during or immediately after a command that
  **already ACK’d**, or during a housekeeping read. Treat as an unusable
  stream: bounded release, log in again, re-read state. Do **not** record
  that as arm/disarm command failure (`disarm_disconnect` / `arm_disconnect`
  or equivalent). If the new login succeeds on attempt 1, Connection stays
  on through that resync. If attempt 1 fails, Connection goes off and the
  ordinary keep-trying reconnect path runs.

On decode failure, log the reason (not `'t'` / bad length / bad CRC /
unknown type / `+++`) and the leading buffer bytes as hex, at a level that
ships in normal add-on logs, not only TRACE.

### Reconnect mechanics (carried forward)

One configured reconnect-wait interval for every disconnect cause. No second
“trigger” interval. No attempt-count setting; retry indefinitely. Before any
reconnect, release the app’s own socket within a bounded time and abandon it
if it will not close, so this client cannot occupy the panel’s single slot.
Login’s own retry budget stays; it must not be removed because check-ins no
longer burst-retry. Patience period, check-in cadence, and reconnect wait
remain install-time settings.

## Consequences

**Positive:** Session health is one story instead of five overlapping ADRs.
Successful disarm during a busy arrival should not look like a panel outage.
Check-in patience, command-reject immediacy, no byte-skip, and keep-trying
reconnect stay, just aligned.

**Negative:** A collision resync that succeeds on attempt 1 does not turn
Connection off, so a torn frame is not visible on that entity — only in
logs. That is deliberate (false offs were the harm) and means anyone
debugging a parse miss must use logs, not Connection history. Detection of
a session that only refuses check-ins still waits the patience window, with
entities and Connection looking healthy for that window (same trade as
ADR-020). Households still on a shared signalling module get no skip-and-
resync; that remains an install violation of ADR-013, not something this
app papers over.

**Follow-on:** `/constitute` then `/architecture` Update should replace the
layered reconnect/Connection chapter with this model, not append another
incident note. Implementation: gate post-ACK flags refresh on whether live
state already moved; stop mapping housekeeping `ForcedDisconnect` onto
command-failure reasons; keep two clocks; add decode-fail hex logging.
FakePanel cannot prove that a real refusing session starts answering again
without re-login. Command-reject fail-window length stays a live-tuning
value, not newly merged into patience.

**CI vs live:** FakePanel / hermetic tests **may** claim: check-ins fire on
schedule under sustained inbound `M` traffic and are independent of the
reconciliation poll interval; a refused check-in inside patience changes
neither session nor Connection; continuous refusal past patience → bounded
release → reconnect → state re-read → Connection off then on; peer close /
`+++` end the session immediately and turn Connection off; injected
non-Connect bytes are not skipped (session is reset, not parsed-through);
arm/disarm NAK or timeout turns Connection off immediately and the
command-reject watchdog still escalates on its own timer; a successful
disarm (or arm) ACK plus a following decode miss on a housekeeping read
does **not** record a command-failure reason and does **not** publish
Connection off if re-login succeeds on attempt 1; post-ACK flags refresh
is omitted when live AREA has already published the new alarm state, and
still runs when it has not; reconnect retries indefinitely at one interval
with no attempt cap; a failed arm/disarm is not re-issued by heal; decode
failure logs reason and leading hex. They **may not** claim: that patience
recovers a refusing session (refusal is sticky on the stand-in until
re-login); that a real Premier Elite torn-frame during garage disarm stays
quiet on Connection; that the phone app is or is not on the same module.

## Confirmation

Hermetic FakePanel tests cover the CI list above, including the 2026-08-30
shape (disarm ACK + interleaved AREA/LOG + housekeeping decode miss must not
be `disarm_disconnect` / Connection off when first re-login succeeds) and
the ADR-019 regression (garbage bytes are not skipped). `/accept` live walks
remain: garage-return (or equivalent) auto-disarm with Connection staying on;
a refused check-in during a PIR/zone burst not flickering Connection inside
patience; a genuine arm/disarm reject still turning Connection off at once;
reconnect after an actual drop without a human restart.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-30 | Clear | — |
