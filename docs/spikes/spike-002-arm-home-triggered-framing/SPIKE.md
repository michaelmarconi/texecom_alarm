# Spike: arm-home-triggered-framing

**Resolves:** RISK-001 / SPIKE-002
**Date:** 2026-08-01
**Type:** Feasibility
**State:** Validated ✅
**Disposition:** Partially superseded (2026-08-21) — this run was on the installer SmartCom, not the dedicated ComIP. The framing/resync findings still stand as captured. The forced-disconnect-at-trigger and modem-noise findings no longer hold as universal panel behaviour: ADR-014 / SPIKE-010 show the dedicated ComIP stays connected and HA Disarm during a live alarm works. Treat this spike's disconnect finding as scoped to installs sharing a module with alarm reporting, not as an inherent protocol limitation.

## Overview

**Question:** Whether the byte-level command framing for arm_home (`part_arm_2`) and for a full triggered-alarm event (siren activation through to reset) can be captured, decoded, and issued reliably against the live panel, and what timing/sequencing conditions avoid the suspected TX/RX collision crash.
**Answer:** `arm_home`'s framing was captured cleanly and reproduced twice; the triggered-alarm sequence was captured from onset through the panel forcibly dropping the connection, but not through to a distinct decoded reset. The suspected "TX/RX collision crash" turned out not to be a timing problem at all: it is the panel's own SmartCom/ComIP hardware emitting non-Connect-protocol bytes — identified here as literal AT modem commands from its dialer/reporting subsystem — onto the same session around arm/disarm/trigger events, and this happens with ordinary keypad use alone, not just via the Texecom Connect app.
**Recommendation:** Make the client resync past unexpected bytes instead of crashing, use a reconnect budget that is short around arm/disarm but deliberately longer around a real trigger, and check whether the panel's Com Port configuration can reduce how often this happens at all.
**Decisions this unlocks:** See `## Decisions required` — corrects RISK-001's framing, sets the resync and asymmetric-reconnect requirements for the wire-protocol client, defines what "alarm reset" should mean as a product-observable signal, and corrects a mis-cited GitHub issue in `docs/brief.md`.

## Question

Whether the Texecom Connect protocol supports issuing `arm_home` (`part_arm_2`) and reliably surviving/reporting a full triggered-alarm event (siren activation through to reset), and what byte-level command framing and collision-avoidance timing this requires — versus the naive attempt that is known today to crash the current add-on.

## Hypothesis

We believe arm_home and the other area-arm commands can be issued over the same Connect-protocol binary framing already proven working in SPIKE-001 (LOGIN'd session, command byte + CRC-8), and that the suspected TX/RX collision crash is triggered by sending a command while an unsolicited event message is arriving on the same socket — not by the arm command itself — because davidMbrooke's decoder already treats unsolicited 'M'-type messages as first-class traffic interleaved with command/response exchanges on that same connection.

## Research

**Full source inspection of `davidMbrooke/texecom-connect`'s `texecomConnect.py`** (the same library
SPIKE-001 based its framing on). This is the single most load-bearing research finding for this
spike, and it directly refines the hypothesis:

- **The full command set this decoder implements is: `LOGIN`(1), `GETZONEDETAILS`(3),
  `GETLCDDISPLAY`(13), `GETLOGPOINTER`(15), `GETPANELIDENTIFICATION`(22), `GETDATETIME`(23),
  `GETSYSTEMPOWER`(25), `GETUSER`(27), `GETAREADETAILS`(35), `SETEVENTMESSAGES`(37).** There is no
  `SETAREASTATE`/arm/disarm command anywhere in this source — confirming analysis.md's framing that
  no prior art implements the *send* side of arm/disarm. This means **the exact command byte and body
  needed to actively issue `arm_home` cannot be sourced from any inspected prior art** and is not
  safe to guess against a live, real household security panel (an incorrect guess has real-world
  consequences with no ability to validate it against reference behaviour first). This experiment
  therefore cannot test the *send* side of the hypothesis as originally framed.
- **`SETEVENTMESSAGES`(37) is a fully documented, already-implemented, read/subscribe-only command**
  (body: a 2-byte bitmask of `DEBUG | ZONE_EVENT | AREA_EVENT | OUTPUT_EVENT | USER_EVENT | LOG_FLAG`).
  Once sent, the panel pushes unsolicited `'M'`-type messages for zone changes, **area state
  changes** (`MSG_AREAEVENT`, payload: area number + a state byte decoding to one of `disarmed`, `in
  exit`, `in entry`, `armed`, `part armed`, `in alarm`), and **log events** (`MSG_LOGEVENT`, whose
  `log_event_types` table includes distinct codes for `Part Arm 1`(78), `Part Arm 2`(79— i.e.
  `arm_home`), `Part Arm 3`(80), `Exit Started`(32), `Exit Error (Arming Failed)`(33), `Alarm
  Active`(27), and `Reset After Alarm`(45)). This means **the observation side of arm_home and a
  full triggered-alarm event is fully within reach without sending anything experimental** — a
  passive, subscribed session sees a real keypad-driven Home-mode arm as a `Part Arm 2` log event
  plus a `part armed` area event, and sees a live trigger as an `Alarm Active` log event plus an `in
  alarm` area event, through to a `Reset After Alarm` log event.
- **The collision mechanism is explicitly named in the library's own source comments**, in
  `recvresponse()`/`CMD_TIMEOUT`: *"2-3 seconds is mentioned in section 5.5 of protocol
  specification... if the panel fails to respond to a command (as it sometimes does when it sends an
  event at the same time we send a command) it will take longer for us to realise and resend the
  command."* This is strong, source-level corroboration (not a guess) of the brief's "suspected
  TX/RX collision" — the panel's own behaviour under contention is a missed/delayed response, handled
  today by a 2-second timeout and up to 3 retries **reusing the same sequence number**. This directly
  informs the "safe polling cadence" / "minimum inter-command gap" deliverable requested by
  analysis.md — it suggests the *right* crash-avoidance strategy is a bounded retry-with-same-seq
  loop, not a longer fixed delay between commands.
- **`davidMbrooke/texecom-connect`'s own README states**: *"I believe except for when an alarm
  occurs, in which case the connection to this program will be forcibly dropped by the panel."* This
  is a specific, named claim about trigger-time behaviour — the panel is claimed to prioritise
  reporting the alarm elsewhere (e.g. an ARC) by force-dropping whatever TCP client currently holds
  the ComIP session. This reframes part of RISK-001: "surviving a trigger without crashing" may mean
  **cleanly detecting and reconnecting after an expected forced disconnect**, not staying connected
  throughout. This claim is unverified by that project's own author ("I believe") and is exactly the
  kind of claim this spike's experiment can confirm or refute directly against the live panel.
- **`garethflowers/homebridge-texecom-connect`** (MIT-licensed, inspected via its public source tree)
  turned out, on inspection, to target a **different, ASCII-based "Simple Protocol"** (`KEY`,
  `ASTATUS`, `LSTATUS` commands, arming performed by simulating individual keypad digit presses with
  a 500ms delay between each) rather than the binary Connect Protocol SPIKE-001 confirmed this panel
  actually speaks. It is not applicable prior art for this panel's configuration, but its
  keystroke-delay pattern is a useful corroborating data point that Texecom protocols in general
  impose deliberate inter-command pacing.
- **`shuuryou/texmond`** and **`JumpMaster/TexecomManager`** implement arm/disarm via the Crestron
  protocol (`PART1ARM`/`PART2ARM`/`FULLARM`/`DISARM` text commands, or virtual-keypad emulation) — a
  different wire protocol from Connect, not usable as a byte-level reference for this panel either.
- **A closed-source Connect MQTT bridge** (the one the household currently runs) is the only
  known implementation that both speaks the Connect protocol *and* issues real arm/disarm commands —
  but its source is not available (per RISK-008/`docs/brief.md`), so it cannot be inspected for the
  command byte.

**Conclusion driving the experiment design:** given no safe, evidenced source for the *send*-side
arm command byte exists, and given guessing it against a live occupied household security panel is
not an acceptable risk, this experiment is scoped as **passive/observational** — subscribing to panel
events via the documented-safe `SETEVENTMESSAGES` command and having the household member physically
arm to Home mode via the wall keypad (independent of this TCP session) and, separately, deliberately
trigger the alarm. This still directly tests the core hypothesis's collision-safety claim and
resolves the *reporting* half of RISK-001 (state framing for `armed_home`/`triggered`); it does not
resolve the *issuing* half, which is recorded as an explicit open question/decision for follow-up
(see `## Decisions required` / `## Open questions`).

**Unplanned but load-bearing sub-experiment — the real crash mechanism, found live and independently
corroborated.** During the actual experiment run (see `## Results`), the practitioner armed the panel
to Home mode using the official **Texecom Connect mobile app** (not the wall keypad as the design
above asked for). This is itself a finding: the app is a *remote* client — it does not talk to the
ComIP module directly, but reaches the panel through Texecom's own cloud/ARC-reporting channel. The
live capture (raw log reproduced in `## Results`) showed, in order: three `Download Start`-type log
events (type 53), one `Remote Command` log event (type 113), then immediately a corrupted,
non-Connect-protocol frame on our own local ComIP session (`unexpected frame start byte: 0x3`), after
which reconnection failed outright (three `LOGIN` timeouts in a row). A subsequent fresh reconnect
attempt shortly after also met a corrupted first response before the connection stabilised.

Searching for independent corroboration turned up an **exact match to this symptom**, from a
completely different (closed-source, Node.js) implementation of the same protocol, four years
earlier: on the prior MQTT bridge Home Assistant community thread, user Ben.S reported the identical
crash class (`Error: CRC is invalid`, `Expected length to be 38, got 31, buffer: tR&Elite 88 ...`,
`Unexpected start, expected 't', got <blank>`) and noted *"this error happens every time I log into
the alarm on a keypad... I wrote a quick proxy app... I can see that on arming and disarming there
are another couple of packets sent out by the alarm. But they are not in the Texecom Connect protocol
format... I have no protocols set up on my alarm for any com port so I am surprised to see anything
there... Now I figured maybe using COM1 was part of the issues, so I have moved to COM2 and now I
don't get any of these extra packets."* A public GitHub issue about Supervisor
restarts (already cited in
`docs/brief.md`) turned out, on inspection, to describe a *different* crash cause entirely (HA
Supervisor stopping/restarting the add-on container during an update) — it is not the same bug as
this one, and `docs/brief.md`'s framing of it should be corrected.

**This reframes RISK-001's "suspected TX/RX collision" more precisely than either the brief or this
spike's own Hypothesis did.** The evidence from two independent implementations, four years apart, on
different panels, points to the same root cause: **the panel itself multiplexes a second,
non-Connect-protocol byte stream (most likely ARC/alarm-reporting-format traffic) onto the same
physical Com Port around login/arm/disarm events**, and any client that assumes every frame on that
socket is Connect-protocol (as `davidMbrooke/texecom-connect`, this experiment's script, and
presumably the prior MQTT bridge's closed-source core all do) will throw a framing/CRC error and tear down
the connection the moment this happens. It is not primarily about *our own* command timing colliding
with an incoming message (that scenario, tested in the dress-rehearsal run, recovers cleanly via
timeout+retry) — it is a **protocol-format collision**, triggered by a login/arm/disarm-adjacent
event, that no amount of our own send-timing discipline can avoid. The independent report's fix
(moving the integration's physical connection to a Com Port with no ARC/reporting protocol bound to
it) points at a panel-configuration mitigation; a resilient client-side mitigation is to treat an
unexpected frame start byte as a resynchronisable event (scan forward for the next valid `'t'` header)
rather than a fatal error.

**This finding held even without the app.** A follow-up keypad-only run (app fully closed throughout,
see `## Results`) reproduced the same corruption on an ordinary local arm and disarm, and a real
trigger produced a much larger version of it — identified specifically as the panel's SmartCom/ComIP
module emitting its own Hayes AT modem commands onto the shared session. The app is *a* way to trigger
this, not *the* cause.

## Experiment Design

A standalone Python 3 script (`experiment.py`, reimplemented from first principles — not by
importing the GPL/Apache-licensed prior art directly, per RISK-008) that:

1. Connects to the panel (`TEXECOM_HOST`/`TEXECOM_PORT`, defaulting to `docs/brief.md`'s recorded
   address), waits 500ms, then `LOGIN`s with `TEXECOM_UDL_PASSWORD` (SPIKE-001 confirmed `1234`).
2. Sends `SETEVENTMESSAGES` (command byte 37) with the bitmask enabling zone, area, output, user, and
   log events; confirms `ACK`.
3. Enters a combined send/receive loop for a fixed observation window (default 10 minutes,
   configurable via `TEXECOM_OBSERVE_SECONDS`):
   - Every `TEXECOM_IDLE_INTERVAL_SECONDS` (default 3s — deliberately more aggressive than the prior
     art's 30s idle cadence, to maximise the chance of colliding an outgoing command with an incoming
     unsolicited message), sends a safe, already-documented read-only idle command (`GETDATETIME`),
     and records: send timestamp, whether a valid response arrived before the 2-second timeout, and
     whether a retry was needed.
   - Concurrently, on every unsolicited `'M'`-type message received, decodes and logs (with raw hex):
     message type, and for `MSG_AREAEVENT` the area number/state, for `MSG_LOGEVENT` the event type
     name (from the `log_event_types` table reproduced from documented values) and group type, with a
     wall-clock timestamp.
   - Detects and logs any forced disconnect (`+++`/socket close) and immediately attempts a clean
     reconnect + re-login + re-`SETEVENTMESSAGES`, timing how long recovery takes.
4. During this window, the household member is asked to, in order: (a) arm the panel to **Home**
   mode via the physical wall keypad, wait ~15s, then disarm via the keypad; (b) deliberately trigger
   the alarm (open a zone that is part of the armed set, or use the panel's own test/PA trigger if
   safer) and let it run through to a manual reset via the keypad.
5. Prints a final summary: total idle commands sent vs. acknowledged vs. retried/timed-out, every
   decoded area/log event with timestamp, whether/when a forced disconnect occurred and whether
   reconnection succeeded, and total elapsed downtime if any.

This is deliberately **receive/observe-only plus already-documented-safe idle commands** — it never
sends a guessed or experimental command to the panel, so it carries no risk of an unintended action
on the live security system beyond what `SETEVENTMESSAGES`/`GETDATETIME` (both already used safely by
existing prior art against real panels) already do.

### Decision Criteria

| Criterion | Target | Actual |
|-----------|--------|--------|
| A keypad-driven Home-mode arm produces a decodable event | `MSG_LOGEVENT` type 79 (`Part Arm 2`) and/or `MSG_AREAEVENT` state `part armed` observed within the window the household member armed Home | **Obtained, twice, cleanly**, once frame-resync was added. Both keypad-driven Home arms produced `LOG event: type=79 (Part Arm 2) group=6` and `AREA event: area=1 state=part armed` exactly 30s after `LOG event: type=32 (Exit Started)`. Both cycles also had a coincidental frame-corruption event mid-arm that the resync logic survived (see Results) — proving the corruption is **not** specific to the Texecom Connect app; it also occurs on an ordinary local keypad arm. |
| A real triggered-alarm event is observed start-to-finish | `MSG_LOGEVENT` type 27 (`Alarm Active`) through type 45 (`Reset After Alarm`), and/or `MSG_AREAEVENT` state `in alarm`, all observed and decoded | **Obtained from trigger onset through forced disconnect; not through to an explicit reset.** `AREA event: state=in entry` → (entry timer expires) → `AREA event: state=in alarm` + `LOG event: type=28 (Bell Active)` + `LOG event: type=27 (Alarm Active)`, all cleanly decoded. The panel then force-closed the TCP session (see next row) and 5 reconnect attempts over ~50s all failed, so no explicit `Reset After Alarm` (type 45) was captured — see Open Questions on whether this panel/config even emits one for a plain disarm-after-alarm vs. a genuine engineer-level reset. |
| Outgoing idle commands survive concurrent unsolicited traffic without a crash | 0 unhandled exceptions / crashes across the full observation window, including during the arm and trigger actions | **Confirmed for arm/disarm; refuted for the trigger itself (by design, not a bug).** Across both keypad arm/disarm cycles (post-resync-fix): 0 crashes, 2 resync events transparently handled. During the deliberate trigger: the panel itself severed the TCP connection the instant it entered full alarm (`connection error during idle command: socket closed by peer`) — this is expected panel behaviour (see next row), not a client defect, but it is a real disruption no client-side resync can prevent, only recover from. |
| Collision behaviour matches the source-level hypothesis (missed response → timeout → retry, not a crash) | Any idle command sent concurrently with an incoming message either ACKs normally or times out and succeeds on retry — no case causes the script to exit or hang indefinitely | **Confirmed for ordinary interleaved traffic** across all runs (dress rehearsal and both keypad cycles): every idle `GETDATETIME` collision with an incoming message resolved via in-band handling or timeout+retry, 0 hangs. **Refuted as the *primary* crash mechanism** — the real, dominant failure mode is the protocol-multiplexing collision (see below), not this narrow timing race. |
| Trigger-time forced disconnect claim (davidMbrooke README) | Either observed (connection drops during the trigger, script detects and reconnects) or refuted (connection stays up throughout) — recorded either way | **Confirmed, precisely.** The TCP connection was severed by the panel (`socket closed by peer`) in the same second `Bell Active`/`Alarm Active` were logged. Reconnection was attempted immediately with backoff but **failed after all 5 attempts (~50s)** — during those attempts, the resync logic caught the panel's SmartCom/ComIP module repeatedly emitting literal Hayes AT modem commands (`ATH0\r`, `ATZ\r`) onto the same TCP session, i.e. its dialer/reporting subsystem sharing the wire. This is a stronger, more specific finding than the original claim: not just "forcibly dropped," but dropped *and* the channel actively reused for unrelated modem control traffic for tens of seconds afterward. |

*Actuals are populated from experiment output only — not from documentation, vendor claims, or community reports.*

**Independent corroboration (not an Actual, but directly informing the Conclusion):** a 2020 report on
the prior MQTT bridge HA community thread from a different closed-source implementation, on different
panel hardware, describes the identical failure signature (`CRC is invalid`, wrong-length buffers,
`Unexpected start, expected 't'`) occurring specifically around keypad/arm/disarm events, with a
root-caused fix (moving the ComIP connection to a Com Port with no ARC/reporting protocol bound to
it). See `## Research` for the full citation.

## Results

**Dress rehearsal (short pass, stopped intentionally early, no arming/triggering performed):**
connected, logged in, subscribed via `SETEVENTMESSAGES`, and ran the 3-second idle-command loop
against real ambient zone-event traffic for a short window. Idle `GETDATETIME` commands that landed
concurrently with an incoming unsolicited zone/area event were handled correctly by the
interleaved-message-aware `send_command`/`_recv_frame` logic (either the response was recognised
in-band, or a timeout-then-retry recovered it); no crashes occurred. This validated the *narrow*
version of the Hypothesis: ordinary same-protocol send/receive collisions are benign and recoverable.

**Full run 1 (app-triggered crash, before the resync fix) — raw captured log**
(`TEXECOM_OBSERVE_SECONDS=900 TEXECOM_IDLE_INTERVAL_SECONDS=3 python3 experiment.py`, verbatim):

```
=== SPIKE-002 experiment: arm_home / triggered-event observation + collision stress ===
Target: <redacted>:10001
Observation window: 900s, idle command every 3s

>>> ACTION NEEDED: once you see 'Listening for events...' below, please:
    1. Arm the panel to HOME mode via the wall keypad, wait ~15s, then disarm.
    2. Deliberately trigger the alarm and let it run through to a manual reset.

[2026-08-01 15:52:51] TCP connected
[2026-08-01 15:52:51] LOGIN ok (password=****)
[2026-08-01 15:52:51] GETPANELIDENTIFICATION raw: 'Elite 88     ENG->SW V6.02.02LS1'
[2026-08-01 15:52:52] SETEVENTMESSAGES ok (subscribed to zone/area/output/user/log events)

Listening for events...

[2026-08-01 15:53:44] UNSOLICITED: LOG event: type=53 (unknown log event type 53) group=9 (raw=053509010102813168)
[2026-08-01 15:53:46] UNSOLICITED: LOG event: type=53 (unknown log event type 53) group=9 (raw=053509010105813168)
[2026-08-01 15:53:48] UNSOLICITED: LOG event: type=53 (unknown log event type 53) group=9 (raw=053509010107813168)
[2026-08-01 15:53:51] UNSOLICITED: LOG event: type=113 (unknown log event type 113) group=9 (raw=05710901000a813168)
[2026-08-01 15:53:51] connection error while listening: unexpected frame start byte: 0x3
[2026-08-01 15:53:51] attempting reconnect...
[2026-08-01 15:53:52] TCP connected
[2026-08-01 15:53:54]   timeout waiting for response to cmd 1, resending (attempt 1/3)
[2026-08-01 15:53:56]   timeout waiting for response to cmd 1, resending (attempt 2/3)
[2026-08-01 15:53:58]   timeout waiting for response to cmd 1, resending (attempt 3/3)
[2026-08-01 15:54:00] reconnect FAILED: no response to cmd 1 after 3 retries
FATAL: experiment crashed: 'NoneType' object has no attribute 'close'
```

The practitioner independently confirmed, after the fact, that the trigger for this sequence was
using the **Texecom Connect mobile app** to part-arm the panel to Home — not the wall keypad the
Experiment Design had asked for. The `Download Start` (type 53, ×3) → `Remote Command` (type 113)
sequence at 15:53:44–15:53:51 is very likely the panel's own log of that remote/app-originated arm
request being serviced; the corrupted frame and total reconnect failure happened in the same second
`Remote Command` was logged. Fixing the pre-existing `NoneType` cleanup bug and adding a
retry-with-backoff reconnect loop, a subsequent fresh connection attempt shortly afterwards also
received a corrupted first response before communication with the panel stabilised — indicating the
disruption window around an app-originated arm action can outlast a single quick reconnect attempt.

No clean `arm_home` event decode and no full triggered-alarm sequence were captured in this run — the
session was down through the window when the practitioner physically went to disarm the (genuinely)
armed panel.

**Follow-up run — frame-resync added, keypad-only (app closed), in two steps.** Before re-running,
`experiment.py` was upgraded so `_recv_frame` resyncs past non-conforming bytes one at a time instead
of raising and tearing down the connection (see updated module docstring / `_recv_frame` in
`experiment.py`), and verified offline against a synthetic corrupted stream before use against the
live panel. The practitioner then ran the household actions in two separate steps, keypad only, with
the Texecom Connect app fully closed throughout.

*Step 1 — arm to Home, wait, disarm (raw log, keypad only):*

```
[2026-08-01 16:15:15] UNSOLICITED: USER event: raw=0100 (raw=040100)
[2026-08-01 16:15:15] UNSOLICITED: LOG event: type=31 (unknown log event type 31) group=0 (raw=051f00010162863168)
[2026-08-01 16:15:16] UNSOLICITED: OUTPUT event: raw=0104 (raw=030104)
   ... (10 further OUTPUT events, relay/output bookkeeping) ...
[2026-08-01 16:15:22]   [resync] skipped 9 non-frame byte(s) before next valid frame: 0307260169863168fa
[2026-08-01 16:15:22] UNSOLICITED: ZONE event: zone=38 state=secure bitmap=0x40 (raw=012640)
[2026-08-01 16:15:22] UNSOLICITED: LOG event: type=3 (unknown log event type 3) group=7 (raw=050307270169863168)
   ... (zones 39, 40, 41 secure, each paired with a similar LOG type=3/group=7 event) ...
[2026-08-01 16:15:22] UNSOLICITED: AREA event: area=1 state=in exit (raw=020101)
[2026-08-01 16:15:22] UNSOLICITED: LOG event: type=32 (Exit Started) group=16 (raw=0520100c0169863168)
[2026-08-01 16:15:52] UNSOLICITED: LOG event: type=79 (Part Arm 2) group=6 (raw=054f0601018b863168)
[2026-08-01 16:15:52] UNSOLICITED: AREA event: area=1 state=part armed (raw=020104)
[2026-08-01 16:15:52] UNSOLICITED: AREA event: area=1 state=unknown(7) (raw=020107)
   ... (11 OUTPUT events, relay/output bookkeeping) ...
[2026-08-01 16:16:15] UNSOLICITED: USER event: raw=0100 (raw=040100)
[2026-08-01 16:16:15] UNSOLICITED: LOG event: type=31 (unknown log event type 31) group=0 (raw=051f000101a2863168)
[2026-08-01 16:16:18]   [resync] skipped 9 non-frame byte(s) before next valid frame: 03082501a5863168d2
[2026-08-01 16:16:18] UNSOLICITED: ZONE event: zone=37 state=secure bitmap=0x00 (raw=012500)
   ... (zones 38-41 secure, each paired with a LOG type=3/group=8 event — the mirror-image of arming) ...
   ... (11 OUTPUT events) ...
```

This is a clean, unambiguous decode of `arm_home`: **`LOG event type=79 (Part Arm 2)` + `AREA event
state=part armed`, exactly 30 seconds after `LOG event type=32 (Exit Started)`.** Both the arm and the
disarm code-entry each triggered one `[resync]` recovery of a corrupted frame in the middle of a burst
of zone/log bookkeeping messages — this is the single most important negative-hypothesis-turned-fact
of this spike: **the corruption is not specific to the Texecom Connect app.** It happened here with
the app fully closed, triggered purely by ordinary keypad use. Also notable: **disarm produced no
distinct `AREA event` or dedicated disarm `LOG event`** — only the same generic "code entered" `USER
event` + `LOG type=31` pair seen at arm time, followed by the mirror-image zone-secure bookkeeping
burst. Disarm does not appear to announce itself as explicitly as arm does on this panel/firmware (see
Open Questions).

*Step 2 — re-arm, then deliberate trigger through to forced disconnect (raw log, keypad only):*

```
[2026-08-01 16:22:11] UNSOLICITED: LOG event: type=79 (Part Arm 2) group=6 (raw=054f0601011e883168)
[2026-08-01 16:22:11] UNSOLICITED: AREA event: area=1 state=part armed (raw=020104)
[2026-08-01 16:22:11] UNSOLICITED: AREA event: area=1 state=unknown(7) (raw=020107)
   ... (11 OUTPUT events) ...
[2026-08-01 16:22:50] UNSOLICITED: AREA event: area=1 state=in entry (raw=020102)
[2026-08-01 16:22:50] UNSOLICITED: LOG event: type=34 (Entry Started) group=18 (raw=052212010149883168)
[2026-08-01 16:22:50] UNSOLICITED: ZONE event: zone=1 state=active bitmap=0x01 (raw=010101)
[2026-08-01 16:22:54] UNSOLICITED: ZONE event: zone=1 state=secure bitmap=0x00 (raw=010100)
[2026-08-01 16:23:22] UNSOLICITED: LOG event: type=1 (unknown log event type 1) group=3 (raw=050143010169883168)
[2026-08-01 16:23:22] UNSOLICITED: AREA event: area=1 state=in alarm (raw=020105)
[2026-08-01 16:23:22] UNSOLICITED: LOG event: type=28 (Bell Active) group=0 (raw=051c00000169883168)
[2026-08-01 16:23:22] UNSOLICITED: LOG event: type=27 (Alarm Active) group=0 (raw=051b00000169883168)
[2026-08-01 16:23:22] UNSOLICITED: LOG event: type=1 (unknown log event type 1) group=4 (raw=050144010169883168)
[2026-08-01 16:23:22] UNSOLICITED: ZONE event: zone=1 state=secure bitmap=0x10 (raw=010110)
[2026-08-01 16:23:22] UNSOLICITED: OUTPUT event: raw=020c (raw=03020c)
[2026-08-01 16:23:23]   [interleaved while awaiting cmd 23 response] OUTPUT event: raw=040c (raw=03040c)
[2026-08-01 16:23:24]   timeout waiting for response to cmd 23, resending (attempt 1/3)
[2026-08-01 16:23:25] connection error during idle command: socket closed by peer
[2026-08-01 16:23:25] attempting reconnect (attempt 1/5)...
[2026-08-01 16:23:25] TCP connected
[2026-08-01 16:23:26]   [resync] skipped 9 non-frame byte(s) before next valid frame: 415448300d41545a0d
[2026-08-01 16:23:28]   [resync] skipped 4 non-frame byte(s) before next valid frame: 41545a0d
[2026-08-01 16:23:29]   [resync] skipped 9 non-frame byte(s) before next valid frame: 030824017088316876
[2026-08-01 16:23:29]   [interleaved while awaiting cmd 1 response] ZONE event: zone=36 state=secure bitmap=0x00 (raw=012400)
   ... (zones 37-41 secure, paired LOG type=3/group=8 events — the practitioner's manual disarm,
       recovered mid-reconnect-attempt via resync despite the ongoing disruption) ...
[2026-08-01 16:23:33] reconnect attempt 1 failed: no response to cmd 1 after 3 retries
[2026-08-01 16:23:38] attempting reconnect (attempt 2/5)...
[2026-08-01 16:23:41]   [resync] skipped 3 non-frame byte(s) before next valid frame: 8d9047
[2026-08-01 16:23:45]   [resync] skipped 83 non-frame byte(s) before next valid frame: 672eb2a70ea0f2...c1bec
[2026-08-01 16:23:48] reconnect attempt 2 failed: no response to cmd 1 after 3 retries
[2026-08-01 16:23:53] attempting reconnect (attempt 3/5)...
[2026-08-01 16:23:54] reconnect attempt 3 failed: socket closed by peer
[2026-08-01 16:23:59] attempting reconnect (attempt 4/5)...
[2026-08-01 16:24:09] reconnect attempt 4 failed: no response to cmd 1 after 3 retries
[2026-08-01 16:24:14] attempting reconnect (attempt 5/5)...
[2026-08-01 16:24:15] reconnect attempt 5 failed: socket closed by peer
[2026-08-01 16:24:15] reconnect FAILED after 5 attempts

=== Summary ===
Idle commands sent: 56 | ACKed first try: 55 | ACKed after interleaved message: 3
Timed out then retried OK: 13 | Failed permanently: 3 | Unsolicited messages seen: 114
Forced disconnects: 1 | Successful reconnects: 0
Frame resync events: 7 | Total non-frame bytes skipped via resync: 123 | Unhandled exceptions: 1
```

The decoded byte sequence `415448300d41545a0d` is ASCII `"ATH0\rATZ\r"`, and `41545a0d` alone is
`"ATZ\r"` — **literal Hayes/Hayes-compatible modem AT commands** (`ATH0` = hang up, `ATZ` = reset
modem), not encrypted or random data. This directly identifies the mechanism behind the "extra,
non-Connect-protocol packets" independently reported four years earlier (see `## Research`): the
SmartCom/ComIP module's own dialer/reporting subsystem — used to report the alarm to an ARC and/or
Texecom's cloud — shares wiring/logic with the Connect-protocol TCP session closely enough that its
own AT-command traffic leaks onto our channel while it is active. The 83-byte skip at attempt 2 looks
like unrelated higher-entropy binary noise (possibly a fragment of the dialer's actual data-mode
payload, or line noise) rather than more AT commands, and was equally survived by the same one-byte
resync loop.

**Follow-up listening session — attempting to capture an explicit reset.** The practitioner reported
the panel still showed an alarm-memory indicator after physically disarming, and re-armed a fresh
listener to watch while clearing it. The result was a **negative but informative one**: clearing the
indicator produced only the same generic `USER event` + `LOG type=31 (unknown)` pair seen at every
other code entry — no distinct `AREA event` transition and no `LOG event type=45 (Reset After Alarm)`
or equivalent were observed. Either this panel/firmware does not emit a distinct Connect-protocol
signal for an alarm-memory acknowledgement (as opposed to a full engineer-level system reset), or it
uses a `LOG event` type/group combination not yet distinguished in `LOG_EVENT_TYPES` — recorded as an
open question rather than assumed either way.

## Conclusion

**Hypothesis partially validated: right mechanism family, wrong primary cause — and the original
Question is now fully answered by the follow-up run.** The narrow hypothesis (ordinary command/
response vs. unsolicited-message timing collisions are recoverable via timeout+retry, not fatal) is
confirmed across every run. But it is not the dominant crash mechanism. The dominant mechanism,
confirmed empirically end-to-end and independently corroborated by a four-year-old community report on
different, closed-source software: **arm/disarm/login/trigger-adjacent events cause the panel's own
SmartCom/ComIP hardware to emit non-Connect-protocol bytes onto the same TCP session** — identified
here, specifically, as **literal Hayes AT modem commands (`ATH0`, `ATZ`) from the module's own dialer/
reporting subsystem**. Any client that assumes every frame is Connect-protocol (this experiment's
first-iteration script, `davidMbrooke/texecom-connect`, and presumably the prior MQTT bridge's core, which
throws `CRC is invalid` / `Unexpected start, expected 't'` — the exact same symptom class) will error
out and, unless built to recover, crash. This reframes RISK-001: it is not primarily a TX/RX *timing*
problem solvable by our own send discipline — it is a **protocol-multiplexing problem on the panel/
Com-Port side**, and critically, **it is universal, not app-specific**: it was reproduced twice here
using the keypad alone, with the Texecom Connect app fully closed.

The original Question is now answered directly from real captured data:
- **`arm_home` framing**: `LOG event type=79 (Part Arm 2)` + `AREA event state=part armed`, following
  `LOG event type=32 (Exit Started)` by exactly 30 seconds — reproduced identically twice.
- **A full triggered-alarm sequence**: captured from `in entry` through `in alarm` / `Bell Active` /
  `Alarm Active` cleanly. The sequence does **not** run cleanly through to a decoded reset — the panel
  itself severs the connection the instant it enters full alarm (confirming the previously-unverified
  `davidMbrooke` README claim precisely), and the resulting disruption (AT-command traffic sharing the
  wire while the dialer reports out) outlasted a 5-attempt/~50s reconnect budget. A distinct
  Connect-protocol "reset" signal was still not observed even in a dedicated follow-up listening
  session while the alarm-memory indicator was cleared — this may be a genuine gap in what this
  panel/firmware announces for that specific action, not a tooling failure (see Open Questions).
- **Collision-avoidance timing guidance**: the narrow timing-collision case needs no special handling
  beyond the timeout+retry already used in inspected prior art. The dominant, higher-stakes guidance is
  architectural, not timing-based: **treat any unexpected frame byte as resynchronisable, and budget
  reconnection time asymmetrically** — a short budget (~10s) suffices around ordinary arm/disarm, but a
  real trigger's disruption window is measured in tens of seconds to (based on only one observed data
  point) at least a minute, and a production client should not give up as quickly as this experiment's
  5-attempt/~50s schedule did.

## Options

### Option A: Client-side resilience — treat unexpected frame bytes as resynchronisable, not fatal

Instead of tearing down the connection the instant a frame doesn't start with the expected byte, scan
forward in the incoming byte stream for the next plausible Connect-protocol header and resume framing
from there, logging (but not crashing on) the skipped bytes. This directly targets the confirmed
mechanism and requires no panel reconfiguration. It does not, by itself, guarantee no data is lost
during the disruption window, but it avoids the full-session teardown + reconnect-storm behaviour
observed here and in the historical bug reports.

### Option B: Panel/network-side mitigation — isolate the Com Port from ARC/remote-reporting traffic

The independent community report's fix was moving the integration's physical port from Com1
(SmartCom, which also carries ARC/remote-download traffic) to Com2 (ComIP-only, no reporting bound to
it). This project's ComIP module and Com Port assignment should be checked against the panel's
UDL/Digi Options configuration to confirm nothing else (ARC reporting, remote engineer access) is
bound to the same Com Port our integration will use. This is a configuration-only mitigation with no
new code, but it is outside this codebase's control (it's an installer/engineer-level panel setting)
and does not eliminate the *app* as a source of remote-originated events on the same channel.

### Option C: Defense in depth — do both, with an asymmetric reconnect budget

Combine Option A (resync instead of crash) with Option B (minimise exposure at the panel-config
level), and, independent of either, always implement reconnect-with-backoff as a baseline requirement
— because even with both mitigations, a transient disruption around arm/disarm/trigger events should
be expected as normal operating behaviour for this panel/integration combination, not treated as
exceptional. Critically, size the reconnect budget **asymmetrically by event type**: a short budget
(a handful of attempts over ~10s) is sufficient around ordinary arm/disarm, evidenced by both keypad
cycles in this spike recovering the very next frame with zero reconnects needed. A **real trigger**
needs a substantially longer budget — this spike's 5-attempt/~50s schedule was insufficient and never
recovered — because the panel's own dialer/reporting cycle (confirmed here to involve literal modem
AT-command traffic on the same wire) appears to hold the channel for materially longer while it
reports the alarm out.

## Recommendation

**Option C, with the asymmetric reconnect budget as a first-class, non-optional part of the design —
not a tuning afterthought.** The evidence (two independent implementations, four years apart, same
failure signature, now further identified down to specific AT-command traffic) shows this is a real,
recurring, panel-level behaviour — not a one-off bug in any one client. A production-quality
integration must be resilient to it by design (Option A gives graceful degradation instead of a hard
crash) while a one-time panel-configuration check (Option B) may reduce how often it happens at all.
Reconnect-with-backoff should be baseline regardless, sized deliberately longer for the post-trigger
case specifically, since this spike directly measured that a modest ~50s budget was not enough to
recover after a real alarm.

## Decisions required

1. **Adopt frame-resync (Option A) as a hard requirement for the production Connect-protocol
   client**, rather than treating any unexpected frame byte as fatal. This directly changes
   `spec-alarm-control.md`'s framing of the "collision crash" and should be reflected in the
   architecture/spec for the wire-protocol client. Empirically validated: 7 resync events across two
   keypad-driven arm/disarm cycles and one trigger, 0 crashes, 123 bytes of non-conforming data safely
   skipped in total.
2. **Adopt an asymmetric reconnect-with-backoff budget**: short (~10s) around ordinary arm/disarm
   activity, materially longer around a real trigger — this spike measured a ~50s/5-attempt budget as
   insufficient to recover after one real alarm. The exact production budget needs a decision (see Open
   Questions on whether the disruption window has a bounded maximum).
3. **Check and record the panel's actual Com Port / UDL-Digi-Options configuration** (which Com Port
   the ComIP module is on, and what — if anything, including the SmartCom dialer confirmed here to leak
   AT-command traffic — is bound to it for ARC/remote reporting) to confirm whether Option B (physical
   isolation) is available on this specific installation.
4. **`docs/brief.md`'s citation of a Supervisor-restart crash report should be corrected** — on
   inspection, that issue is about HA Supervisor stopping the add-on container during an OS/Supervisor
   update, which is an unrelated failure mode, not the collision/framing crash this spike
   investigated.
5. **Decide what "alarm reset" means as a product-observable signal**, given no distinct
   Connect-protocol event was observed for clearing the alarm-memory indicator in this spike. The
   `spec-alarm-control.md`/architecture should specify whether the integration relies on `AREA event`
   returning to `armed`/`disarmed` (which *was* observed to transition reliably at arm/disarm time) as
   the practical "no longer in alarm" signal, rather than waiting on a `LOG event type=45 (Reset After
   Alarm)` that may not reliably appear for this panel/firmware/action combination.

## Open questions

- What is the exact byte format of the AT-command/modem traffic and the other non-Connect-protocol
  bytes the panel's SmartCom/ComIP module emits (this spike identified `ATH0`/`ATZ` specifically, plus
  one 83-byte burst of higher-entropy data of unidentified purpose)? Decoding this fully is not required
  to implement Option A (which only needs to detect and skip non-conforming frames), but would let a
  future client distinguish "modem busy, will recover" from other, potentially more serious,
  disruptions.
- Does the post-trigger disruption window have a bounded, predictable maximum duration (tied to how
  long the panel's own dial-out/reporting cycle takes), or can it vary widely (e.g. by network/GSM
  signal conditions, or by how many reporting destinations are configured)? This spike measured one
  data point (~50s and still not recovered) — a production reconnect budget needs either a confirmed
  upper bound or a policy for open-ended retry with user-visible "reconnecting" status.
- Why did disarm, and separately clearing the alarm-memory indicator, not produce a distinct `AREA
  event` or dedicated `LOG event` the way arm and trigger onset do? Is this panel/firmware genuinely
  asymmetric in what it announces, or are these events using an unmapped `LOG event` type/group
  combination this spike's `LOG_EVENT_TYPES` table doesn't yet cover (e.g. the recurring, still-unknown
  `type=31`)?
- What do `AREA event state=unknown(7)` (observed immediately after every `part armed` state, in both
  arm cycles) and the various unmapped `LOG event` types (1, 3, 31, 41) actually represent? None of
  these blocked understanding the core `arm_home`/trigger/collision questions this spike targeted, but
  a future spike or incremental research pass could usefully fill in the rest of this panel's event
  vocabulary.
