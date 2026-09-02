# ADR-022: Use One Busy-Versus-Dead Session Model Including Late Command Replies for Panel Connection Health

**Status:** Accepted ✅
**Date:** 2026-09-01
**Supersedes:** ADR-021

## Overview

**Background:** We already treat “the panel is busy sending updates” as different
from “the panel is gone” — for periodic hellos, and for an extra status read
after a command that already succeeded. A live walk showed the leftover hole:
Disarm during a real alarm got no reply in time, so we marked the link dead
for about half a minute. The panel was still sending normal updates. A second
Disarm on the same connection worked almost immediately.
**Decision:** Keep one rule for the whole session: busy is not dead. The
Connection sensor means we cannot talk to the panel. If Arm or Disarm gets no
reply while ordinary updates are still arriving, retry the same tap as a
**new** request and leave Connection on. If the panel refuses, or if the wait
is completely silent, Connection goes off at once.
**Why this way:** Calling every late reply a lost panel recreates the false
“offline” we were trying to stop. Skipping junk bytes would not have produced
the missing reply — the updates we heard were already valid — and it would hide
a torn message. A longer wait only while the siren is sounding is another
one-off. Treating a chatty wait as busy is the same rule we already use for
hellos, applied to Arm and Disarm.
**What this constrains:**
- Connection goes off only when we cannot talk: the panel hung up, it ended the
  session, hellos have failed for the whole patience window, Arm or Disarm was
  refused, or Arm or Disarm timed out with **no** updates arriving during that
  wait.
- If Arm or Disarm times out while ordinary updates are still arriving, do not
  turn Connection off. Retry as a new request. If those retries still get no
  reply, then Connection goes off.
- A refused Arm or Disarm still turns Connection off immediately and still has
  its own countdown to a fresh login. That clock must not be merged into hello
  patience.
- Updates in general are not proof the session will accept commands. Updates
  **during this wait** only mean the line is not silent.
- A command that already succeeded must not be recorded as a connection failure
  if a later status read then fails to parse.
- Do not ask extra questions whose answer already arrived as a live update.
  After a successful Arm, do not ask for a full alarm-flags snapshot. After
  Disarm, ask only if Home Assistant still shows the house as set. Hellos still
  go out on their clock even when the line is busy.
- After login, and again after a reconnect login, re-read current zone and
  alarm state before trusting entity state.
- Never skip unexpected bytes hoping to find the next valid message. If the
  stream is unusable, close it and log in again.
- Reconnect uses one wait interval, keeps trying with no attempt cap, and must
  release the old connection quickly so we cannot sit on the panel’s only slot.
- Zone and alarm entities stay visible; only the app process dying can mark
  them unavailable.
- After we have told the household a tap failed, do not silently send it again.
  Retrying **before** we declare failure is required.
- When a message cannot be read, log why and enough of the arriving bytes to
  tell a torn message from a hang-up.
**Open follow-ons:**
- Whether a refused hello ever starts succeeding again if we leave the session
  open (not seen live).
- Whether a competing client on the same module caused older long outages — an
  install question, not a new recovery rule.
- How long we wait after a refused command before forcing a fresh login stays a
  live-tuning value, not merged into hello patience.

## Context

ADR-021 said: Connection means we cannot talk; a busy panel is not a lost
panel; do not scan the byte stream for the next valid message; hellos and
refused commands use two different clocks. It still treated **every** Arm or
Disarm timeout as “cannot talk” and turned Connection off immediately.

On 2026-09-01 a live Home arm succeeded without a follow-up flags read. The
alarm then triggered. The panel flooded unsolicited event messages (`M`
frames — zone, output, log). The first Disarm (`SETAREADISARM`, sequence 226,
two attempts **reusing** that sequence) saw only those `M` frames and timed
out after about four seconds. Connection went off (`disarm_timeout`).
Keepalives were still OK. A second Disarm (sequence 227) was acknowledged in
under a second on the **same** TCP connection. Connection came back about
thirty seconds later because a recover timer elapsed, not because we
reconnected.

The events during the wait were valid Connect frames. We were not looking at
line noise. We were looking at a missing command reply (`R`) while the panel
was busy. Scanning for the next start byte would not have invented that reply.
A longer timeout only while “in alarm” would be another special case.

Unchanged elsewhere: entities stay available (ADR-004); zone and alarm
snapshots after login and reconnect login (ADR-006, ADR-009); dedicated local
module (ADR-013); the five-minute reconciliation poll does not feed Connection
(ADR-017).

## Decision drivers

- One story for hellos, Arm/Disarm waits, extra status reads, parse failures,
  and reconnect — not a new exception per incident.
- Connection means “we cannot talk.” A false off after a tap that then
  succeeded on the same link fails this decision.
- Ordinary events during a command wait are busy, not dead.
- A refused command (NAK) still turns Connection off immediately and is not
  absorbed by hello patience (the panel can hello and emit events while
  refusing Arm/Disarm).
- A completely silent wait (no events, no reply) still turns Connection off
  immediately.
- A retry after a timeout that saw events must use a **new sequence number**,
  not the timed-out one. Live: same-sequence retry failed; next sequence
  succeeded.
- Retry count stays bounded (the existing command retry budget). Using up that
  budget with no ACK is cannot-talk even if events continue.
- Do not skip unexpected bytes. Do not bring back the old “scan for the next
  valid message” workaround.
- Reconnect keeps trying on one wait interval and must free the old socket
  quickly.
- Zone and alarm keep last-known state; Connection is freshness, not
  availability.
- FakePanel may prove the state machine in CI. A real siren-and-Disarm walk
  staying quiet on Connection remains live-only.

## Options considered

- **Option A: Keep ADR-021’s timeout rule** — any Arm/Disarm timeout turns
  Connection off immediately; maybe wait longer while the alarm is sounding.
  Rejected because: it fails the “false off after a later success on the same
  link” driver and the “one story, not a new exception” driver.
- **Option B: Scan past unexpected bytes and keep parsing** — the old
  skip-and-resync path. Rejected because: the 2026-09-01 wait already parsed
  valid `M` frames; skipping junk would not produce the missing command reply,
  and it violates the no-byte-skip driver.
- **Option C: Whenever an event arrives, keep waiting forever for the ACK** —
  treat any inbound traffic as “session is healthy.” Rejected because: traffic
  is not proof the panel will accept commands (a stuck session can emit events
  while refusing Arm/Disarm); that would hide a refused tap and violate the
  NAK-immediacy driver.
- **Option D: Apply busy-versus-dead to the command wait** — timeout while
  ordinary `M` arrived → retry with a new sequence, Connection stays on until
  the bounded budget is exhausted; NAK or silent timeout → Connection off
  immediately. Keep the rest of ADR-021 (hello patience, two clocks, no
  flags read after Arm, parse-miss reconnect, no byte-skip, one reconnect
  interval).

## Decision

Chosen option: **Option D — busy-versus-dead command waits**

This keeps Connection meaning “cannot talk,” puts Arm/Disarm waits in the same
story as hellos, still fails fast on NAK and on silence, and retries with a
new sequence — without scanning the stream for the next valid message.

### When Connection goes off

Publish Connection **off**, then recover, when any of these hold:

- TCP closed, or a read returns no data (peer gone).
- The panel sent the end-of-session marker `+++`.
- Hellos (`GETDATETIME`) have been refused (`NAK`) or unanswered for the whole
  configured patience period.
- Arm or Disarm (`SETAREAARM` / `SETAREADISARM`) was NAK’d. Connection off
  **immediately**. A separate watchdog still counts down to a fresh login if
  that stays stuck. That countdown must not share the hello-patience clock.
- Arm or Disarm timed out **and no well-formed `M` arrived during that wait**
  (silence). Same immediate off and the same watchdog as a NAK.
- Arm or Disarm timed out **while well-formed `M` frames were arriving**, and
  the bounded retry budget (new sequence each attempt) is then exhausted
  without an ACK. Off at **exhaustion**, not at the first late reply.

Connection stays **on** during hello patience, during busy Arm/Disarm retries,
and through a parse-miss reconnect that logs in successfully on attempt 1.
After a real dead-session recovery, Connection returns on only once login has
succeeded and zone plus alarm snapshots have been re-read (ADR-006 / ADR-009).

The reconciliation poll (ADR-017) still must not feed Connection.

### Commands while the panel is chatty

Hellos stay on a **fixed elapsed-time schedule**. Inbound events must not skip,
delay, or starve them. Events in general are not proof the session will accept
commands. Events **during this command’s wait** only mark that wait as busy
rather than silent; they do not extend the wait without bound (Option C).

When `SETAREAARM` / `SETAREADISARM` times out and at least one well-formed `M`
was queued during that attempt: retry with a **new sequence** (do not reuse the
timed-out sequence). Keep today’s retry count. Do not publish Connection off
between those attempts.

After a successful Arm ACK, do **not** send `GetAreaFlags`. Live area/log
events already carry exit and armed; asking during that burst collides. After
a successful Disarm ACK, send `GetAreaFlags` only if live events have not
already published unset (Home disarm sometimes omits an area push). Snapshots
after login and after reconnect login remain mandatory (ADR-009 / ADR-006).

Do not automatically re-send an Arm or Disarm that already failed (NAK, silent
timeout, or retries exhausted). New-sequence retries **before** that failure is
declared are required.

### When bytes do not form a message

Do **not** skip non-conforming bytes and continue parsing. If
`try_decode_frame` consumes bytes but returns no frame, that is never a licence
to delete one byte and hunt for `'t'`.

- **Hung up:** peer close, empty read, or `+++` → session dead; Connection off;
  release the socket; reconnect.
- **Collision:** TCP still open; decode failed (bad start byte, illegal length,
  bad CRC, unknown type) during or right after a command that **already
  ACK’d**, or during a status read. Close cleanly, log in again, re-read state.
  Do **not** record that as Arm/Disarm command failure (`disarm_disconnect` /
  `arm_disconnect` or equivalent). If the new login succeeds on attempt 1,
  Connection stays on. If attempt 1 fails, Connection goes off and the ordinary
  keep-trying reconnect path runs.

On decode failure, log the reason (not `'t'` / bad length / bad CRC / unknown
type / `+++`) and the leading buffer bytes as hex, in everyday add-on logs, not
only TRACE.

### Reconnect (unchanged from ADR-021)

One configured reconnect-wait interval for every disconnect cause. No second
“trigger” interval. No attempt-count setting; retry indefinitely. Before
reconnect, release our socket within a bounded time and abandon it if it will
not close, so we cannot occupy the panel’s only slot. Login keeps its own retry
budget. Patience period, hello cadence, and reconnect wait remain install-time
settings.

## Consequences

**Positive:** Connection stays on when a Disarm reply is late because the panel
is shouting events. Same model for hellos, command waits, extra reads, and
reconnect. Scanning the stream for the next valid message stays rejected.

**Negative:** A parse-miss reconnect that succeeds on attempt 1 does not turn
Connection off, so a torn frame is only visible in logs. A session that only
refuses hellos still looks healthy until patience expires. A command wait that
keeps seeing events can use the full retry budget before Connection goes off,
so a true refuse that never NAKs and only emits events is slower to surface
than a NAK. Installs that still share a module with alarm reporting get no
byte-skip workaround — that remains an ADR-013 install violation.

**Follow-on:** `/constitute` then `/architecture` Update should carry this
timeout split into the session-health chapter, not append another incident
note. Implementation: classify Arm/Disarm timeouts by whether well-formed `M`
arrived during the wait; new sequence on busy retry; Connection off only on
NAK, silent timeout, or exhausted busy retries. FakePanel cannot prove that a
real trigger event-flood stays quiet on Connection. The refused-command
fail-window length stays live-tuning, not merged into hello patience.

**CI vs live:** FakePanel tests **may** claim: hellos fire on schedule under
sustained inbound `M` and are independent of the reconciliation-poll interval;
a refused hello inside patience changes neither session nor Connection;
continuous refusal past patience → release socket → reconnect → re-read state
→ Connection off then on; peer close / `+++` end the session immediately and
turn Connection off; injected non-Connect bytes are not skipped; Arm/Disarm
NAK turns Connection off immediately and the refused-command watchdog still
escalates on its own timer; Arm/Disarm timeout with no `M` during the wait
turns Connection off immediately; Arm/Disarm timeout while `M` is arriving
does **not** turn Connection off if a new-sequence retry then ACKs; exhausting
the busy-retry budget without an ACK does turn Connection off; a successful
Arm/Disarm ACK plus a later decode miss on a status read is not a failed tap
and does not publish Connection off if re-login succeeds on attempt 1;
post-command flags read is omitted after Arm, and after Disarm when live
events already published unset, and still runs after Disarm when the card is
not yet unset; reconnect retries indefinitely at one interval; heal does not
re-issue a failed Arm/Disarm; decode failure logs reason and leading hex.
They **may not** claim: that patience recovers a refusing session (the
stand-in keeps refusing until re-login); that a real Premier Elite
trigger-then-Disarm under an event flood stays quiet on Connection; that the
phone app is or is not on the same module.

## Confirmation

Hermetic FakePanel tests cover the CI list above, including: Disarm (or Arm)
while a burst of unsolicited `M` eats the first sequence’s ACK, a new-sequence
retry succeeds, Connection stays on; NAK still turns Connection off at once; a
silent timeout (no `M`) still turns Connection off; garbage bytes are not
skipped. `/accept` live walks remain: a real trigger then Disarm under an event
flood with Connection staying on; a genuine NAK still turning Connection off at
once; reconnect after an actual drop without a human restart; a refused hello
during a zone burst not flickering Connection inside patience.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-09-01 | Clear | — |
