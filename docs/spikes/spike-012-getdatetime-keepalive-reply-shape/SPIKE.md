# Spike: GETDATETIME keepalive reply shape

**Resolves:** 2026-08-28 disconnect report (no matching RISK/SPIKE entry in `docs/analysis.md` — new production unknown; assigned SPIKE-012 as next available number)
**Date:** 2026-08-28
**Type:** Feasibility
**State:** Draft 📝

## Overview

**Question:** pending experiment
**Answer:** pending experiment
**Recommendation:** —
**Decisions this unlocks:**
—

## Question

When the panel replies to a `GETDATETIME` keepalive with a short (2-byte) `'R'` frame instead of the expected 7 bytes — identically and at normal round-trip speed across all 3 same-sequence retry attempts — what does that reply actually contain (byte value), and does it correlate with recent zone/panel activity?

## Hypothesis

We believe an extended live capture of the panel connection (with payload hex logging added to keepalive replies) run for several hours against the real household panel will show that the 2-byte `GETDATETIME` reply is consistently a specific byte value (most likely ACK `0x06`, per the existing FakePanel test-double model and `docs/protocol-reference.md`'s prior-art note), and will show whether these events correlate with immediately-preceding zone/`M`-frame activity or occur independently of it — providing enough evidence to decide whether a keepalive policy that treats an ACK-shaped reply as a successful check-in would eliminate the 2026-08-28 reconnect-storm pattern without masking a genuine dead-session (NAK) case.

## Research

**Trace evidence from the 2026-08-28 household report** (see `docs/protocol-reference.md` §Behavioural constraints, and the raw add-on log excerpts supplied with the report): a captured full-budget failure (07:29:22 BST) shows all 3 same-sequence keepalive attempts returning a CRC-valid 2-byte `'R'` frame body (1-byte payload after stripping the echoed command byte) at normal round-trip latency (~300ms — indistinguishable from a healthy 7-byte reply's latency). This is not the "panel briefly busy, reply deferred" shape the existing bounded-retry fix (`TASK-47`, shipped 0.2.2) was built for; it is a fast, deterministic, identically-wrong reply on every attempt.

**Existing code assumption:** `PanelClient.keepalive()` (`texecom_alarm/src/texecom_alarm/protocol/client.py:197-224`) requires exactly 6 payload bytes (`_GETDATETIME_REPLY_LENGTH = 6`); anything else exhausts a 3-attempt same-sequence retry budget (`keepalive_retries=2`) and then raises `ProtocolError`, which `app.py`'s `_listen_panel_messages` converts to `ForcedDisconnect` → full session teardown + reconnect (`texecom_alarm/src/texecom_alarm/app.py:567-585`).

**Test double's model of this exact shape** (`texecom_alarm/tests/fake_panel.py:319-322`, `wrong_shape_keepalive_replies` scenario): reproduces it as `bytes([CMD_GETDATETIME, ACK])` — i.e. the team's working hypothesis, carried into `docs/protocol-reference.md:64,169`, is that this reply is an **ACK** (`0x06`), not a NAK or corruption. This hypothesis has never been confirmed against real wire bytes — production TRACE logging only records frame *length* (`panel_rx type=%r seq=%s %s bytes`, `client.py:498-504`), never payload content.

**External prior art** (already cited in `docs/protocol-reference.md`'s Design alternatives table): `davidMbrooke/texecom-connect`'s code comments cite the panel protocol spec §5.5 — the panel "sometimes... sends an event at the same time we send a command" — and that project mitigates with 3 same-command retries, not a different reply-shape policy. This corroborates the *shape* of the problem (collision with unsolicited traffic) but that project's fix does not by itself explain a reply that is fast and repeatable across retries rather than delayed/eaten.

**Open gap this spike addresses:** none of the above confirms (a) the actual byte value the panel sends, or (b) whether short-reply events correlate with recent zone/`M`-frame activity (the "panel busy" theory) or occur independently of it (which would point toward something else — e.g. a stateful quirk tied to the sequence number or session age).

## Experiment Design

**Type:** Feasibility — live capture against the real household panel (192.168.1.51:10001), run from this environment now that the production `ebb3b885_texecom_alarm` add-on is confirmed stopped/disconnected, so this capture session is the panel's sole Connect client (ADR-001: single login).

**What is built:** `experiment.py` reuses the **actual production protocol code** unmodified (`texecom_alarm.protocol.client.PanelClient`, `texecom_alarm.protocol.frame`) — imported directly via `PYTHONPATH`, no reimplementation — so the capture faithfully reproduces production's real retry/teardown/reconnect behaviour. It adds exactly one diagnostic-only extension: a `PanelClient` subclass that overrides `_recv_frame` to additionally log the full response payload as hex (`body.hex()`) alongside the existing length, for every frame received. No production source file is modified.

**Loop shape** mirrors `app.py`'s `_listen_panel_messages` (`app.py:547-610`) directly: `connect()` → `login()` → `set_event_messages()` (read-only subscribe, matches production) → loop `recv_message(timeout=15s)`; on `TimeoutError`, call `keepalive()`. Startup zone/area snapshot reads are skipped (unrelated to steady-state keepalive behaviour, and skipping avoids extra load on the panel for a diagnostic-only run).

**Instrumentation, written as structured JSON-lines to `docs/spikes/spike-012-getdatetime-keepalive-reply-shape/capture.jsonl`:**
- Every received frame: timestamp, type, sequence, length, hex.
- Every keepalive attempt: timestamp, attempt number, latency, resulting classification (ok / short-reply / NAK / timeout), payload hex.
- Every session-end event: reason, and the timestamps + hex of the last 10 frames received before it (covers the "recent zone/M-frame activity" correlation question without needing a separate buffer design).
- On session end: automatic reconnect (`close()` → `connect()` → `login()` → `set_event_messages()`), then resume the loop — matching production's indefinite-retry behaviour (ADR-018), so the capture runs unattended for the full window.

**Run window:** a few hours (3–6h), backgrounded; checked periodically rather than held open synchronously.

**Safety:** read-only panel commands only (`LOGIN`, `GETDATETIME`, `SETEVENTMESSAGES`, passive message receipt) — no arm/disarm/write commands are sent. UDL password is read from the existing on-disk add-on config (`/mnt/supervisor/apps/data/local_texecom_alarm/options.json`, already present on this host) rather than being pasted into chat.

### Decision Criteria

| Criterion | Target | Actual (interim, run in progress) |
|-----------|--------|--------|
| Payload byte value of short (2-byte body) `GETDATETIME` replies | Identify the actual byte(s) observed (e.g. confirm/refute `0x06` ACK vs `0x15` NAK vs other) | **`0x15` (NAK) — refutes the ACK hypothesis.** First full-budget failure at 10:55:19 (session 1, ~69 min in): all 3 same-sequence attempts returned identical hex `1715` (echoed `CMD_GETDATETIME` byte `0x17` + `0x15` NAK). This contradicts `fake_panel.py`'s `wrong_shape_keepalive_replies` model and `docs/protocol-reference.md`'s ACK note — the panel is genuinely rejecting the keepalive, not sending a benign ACK-shaped shortcut. |
| Round-trip latency of short replies vs. normal 7-byte replies | Confirm whether short replies are fast/indistinguishable (as in the 07:29:22 sample) or occasionally deferred | Fast/indistinguishable, matching the report: ~297ms, ~359ms, ~342ms for the 3 attempts vs. ~250–400ms typical for healthy 7-byte replies. |
| Correlation with recent zone/`M`-frame activity | Determine whether short-reply events are preceded by recent panel traffic (supports "busy panel" theory) or occur in quiet periods (points elsewhere) | Consistent with "busy panel": a dense burst of `M`-frame traffic (10:54:08–10:55:03, ~15 frames in under a minute) immediately preceded the 10:55:18 keepalive that got NAK'd. |
| Frequency of short-reply / session-teardown events over the capture window | Measured count, compared against the report's ~1 event per 1–2h cadence | 1 event in the first ~69 minutes so far (run still in progress) — roughly in line with the report's cadence. |
| Whether same-sequence retries return an identical wrong reply, or occasionally recover | Confirm/refute the report's observation that all 3 attempts fail identically when the budget is exhausted | Confirmed for this event: all 3 attempts returned identical `1715`. |

*Actuals are populated from experiment output only — not from documentation, vendor claims, or community reports. Table will be finalised once the full capture window completes.*

**Experiment-script caveat (not a panel finding):** the post-NAK reconnect in event 1 took 77s (14 `ECONNREFUSED` attempts) vs. the report's typical ~7s. Production's `reconnect_after_disconnect` (`texecom_alarm/src/texecom_alarm/reconnect.py:79`) calls `panel.close()` before reconnecting; `experiment.py`'s equivalent path did not (fixed post-event-1, not yet live in the process that hit event 2). Any reconnect-latency data from this run should be disregarded in favour of the report's own figures.

**Event 2 (12:22:24) and the ~55-minute stuck reconnect:** same `1715`×3 NAK signature, again preceded by a burst of `M`-frame traffic in the prior ~50s — reproduces the byte-value and busy-panel-correlation findings from event 1. But the reconnect this time did not recover on its own: for ~55 minutes the capture cycled every ~5s through a mix of `ECONNREFUSED`, "sent data outside the Connect protocol" (mid-LOGIN), "closed the network connection", "did not answer LOGIN in time", and one "ended the session (sent `+++`)". The household confirmed the Texecom iOS app was open in the background throughout (on the same local-module IP this capture targets) and closed it once noticed; that alone didn't immediately clear the stuck state. Ruled out as causes: no other local process or leaked socket on the capture side (`ps`/`ss` showed only the capture's own single connection attempt, no accumulation). The practitioner then had the capture process killed outright, waited 60s with no client attempting to connect at all, and restarted it — it logged in successfully on the very first attempt. This points to the panel's local module needing a clean quiet window (no client hammering it every 5s) to recover from whatever state the NAK/forced-disconnect sequence left it in, rather than resolving through continued same-cadence retries alone.

**Event 3 (13:22:23) — likely root cause identified:** after the clean 60s-quiet restart (13:18:58, immediate `panel_login_ok`), a third NAK (`1715`×3, same signature) hit at 13:22:23, again preceded by an `M`-frame burst. The household reported opening the Texecom iOS app at almost exactly this moment, and seeing the app itself show the same connect-fail/retry pattern this capture was showing. This is strong evidence that the iOS app and this capture (and, in production, the add-on) are contending for the **same single ComIP connection slot on the same local-module IP** (192.168.1.51) — i.e. for this household, the phone app is not actually isolated on a separate installer module the way ADR-013 assumed; opening it appears to be sufficient to trigger the NAK/forced-disconnect pattern in whichever client already held the connection. If confirmed, this would be a strong root-cause candidate for the original 2026-08-28 disconnect report, independent of any keepalive-retry-policy question.

**Confirmed:** the household re-opened the Texecom app and it connected/worked perfectly (it evidently takes the ComIP slot cleanly) while this capture stayed stuck in the same connect-fail loop. Force-killing the app again did not immediately clear the capture's stuck state (consistent with event 2). Repeating the event-2 fix — kill the capture process, brief quiet window with no client attempting a connection (this time only ~20s, shorter than event 2's 60s), restart — again produced an immediate `panel_login_ok` on the first attempt. This is now a repeated (2×) pattern: once a competing client (this capture or the phone app) has taken and then released the connection, the *other* client cannot reliably get back in just by continuing same-cadence retries; a clean restart after a short quiet gap does.

## Sub-experiment: minimum quiet-wait to reconnect after a clean release

**Question:** is the extended stuck-reconnect state (events 2 & 3) caused by a fixed panel-side cooldown, or by a third party continuing to hold/retake the connection?

**Design** (`wait_threshold_experiment.py`, self-contained — no phone app needed): per trial, Client A logs in, Client B then attempts to log in (testing whether the panel's single-connection limit displaces A or refuses B outright), both are closed cleanly, then a fresh login is attempted at increasing wait checkpoints after release (0, 2, 5, 10, 15, 20, 30, 45, 60s), stopping at the first success. 3 trials run (main capture paused for the duration).

**Result — clean and highly consistent across all 3 trials:**
- Client B's `connect()` was refused outright (`ECONNREFUSED`) every time while A was still logged in — the panel won't even accept a second TCP connection while one is active, not just reject a second login (confirms ADR-001 at the TCP level, not only the protocol level).
- After A's own clean `close()`, an *immediate* (0s) reconnect attempt always failed the same way: `ForcedDisconnect` — panel actively sent `+++` to end it.
- Waiting to the 2s checkpoint always succeeded, first attempt, all 3 trials (`success_waits_s: [2.0, 2.01, 2.0]`).

**Conclusion for this sub-experiment:** the panel itself recovers fast (threshold is somewhere between 0s and 2s) once a session is cleanly released by its own client. This means the ~55-minute (event 2) and ~50-minute (event 3) stuck-reconnect states are **not** explained by a fixed panel-side cooldown — a well-behaved release/reconnect cycle clears in ~2s. Those extended outages are better explained by a third party (the Texecom app, confirmed contending in event 3; unconfirmed but suspected in event 2) continuing to actively hold or re-take the connection throughout that whole window, not by the panel being slow to let go.

## Event 4 (13:41:33) and the kill-and-restart-beats-in-place-retry pattern

Same `1715`×3 NAK signature, again preceded by an `M`-frame burst (13:40:28–13:41:18, ~50s, matching the app's own login/activity) — reproduces the byte-value and busy-panel-correlation findings for a 4th time. The household confirmed the Texecom app was open and connected successfully at this point (i.e. the app displaced the capture's session this time, the reverse of the brief window right after event 4 where the capture still held the connection and the app would have been the one refused, per the wait-threshold sub-experiment's exclusivity finding).

After the household force-closed the app (marked 13:42:37), the capture's *existing* process kept cycling through the same in-place retry loop (`ECONNREFUSED`, unexpected-data, connection-closed, LOGIN-timeout, `+++`) for at least another ~70s with no recovery — consistent with events 2 & 3, and inconsistent with the ~2s clean-release threshold measured above. Killing that process (13:43:55) and immediately starting a **brand-new** process (13:44:03.8) succeeded on its very first login attempt (13:44:04.6, well under 1s) — no quiet gap needed this time, unlike the ~20–60s gaps used for events 2 & 3's fix.

**This is now a 3-for-3 pattern:** an existing process stuck in the post-NAK/post-displacement retry loop does not reliably recover by continuing to retry in place, no matter how long it's given (tens of minutes, observed) — but killing it and starting a fresh process recovers near-instantly. Combined with the wait-threshold sub-experiment (clean release + fresh client also recovers in ~2s), this points at something in the *existing degraded client/process's own state* (not a panel-side lockout, and not simply elapsed time) as the reason in-place retry keeps failing. Candidate mechanisms not yet isolated: stale asyncio transport/queue state surviving across the same `PanelClient`/event-loop instance's repeated connect/close cycles, or some other process-lifetime state — worth a follow-up spike/code read of `reconnect_after_disconnect` and `PanelClient.connect()`/`close()` if a production fix is pursued.

**Important caveat on that "3-for-3" reading, found on re-reading the code rather than from new capture data:** `experiment.py`'s in-place retry (`reconnect_with_backoff` → `new_session`) already constructs a **brand-new `CapturingPanelClient` instance every attempt**, in the same process — it is *not* the same object being reused. Yet that fresh-instance-same-process retry still got stuck for 50+ minutes in events 2 and 3. This means "construct a fresh instance" is demonstrably **not sufficient** by itself; whatever the kill-and-restart fix is doing, it is doing something beyond what already happens on every retry attempt today. Separately, production's actual `reconnect_after_disconnect` (`texecom_alarm/src/texecom_alarm/reconnect.py:79-116`) does something different again: it calls `close()` then `connect()`/`login()` on the **same** `PanelClient` instance repeatedly, and it sleeps `reconnect_delay_seconds` **before every attempt including the first** — unlike `experiment.py`'s immediate first try. Production's exact reconnect pattern has never been put through a stuck-reconnect scenario at all in this spike. There are now three distinct, never-directly-compared reconnect shapes in play (see Open Questions below).

## Additional finding: retry-recovery outcome differs by trigger signature

Mining `capture.jsonl` for every short (2-byte) `'R'` frame across the full run confirms, with certainty, that **all four** NAK events (10:55:19, 12:22:23-24, 13:22:22-23, 13:41:33) show the *identical* `1715` hex on *all three* same-sequence retry attempts — zero exceptions, zero mid-budget recoveries. (The other 2-byte `'R'` frames in the capture, `0106`/`2506` at sequence 0/1 of every session, are the expected LOGIN-reply ACK shape, not a keepalive retry — a different, non-anomalous code path.)

This is worth contrasting with the *other* existing retry trigger in the same code path, `panel_interleaved_message` (an unsolicited `M`-frame arrives instead of the keepalive's `R`-frame reply — the scenario `TASK-47`/0.2.2's bounded retry was originally built for). The household's own original report (Research, not this capture's Actuals) contains examples of **both** outcomes for that trigger: a same-day case where the retry recovered cleanly (`attempt=1` got a proper 7-byte reply, session continued) and a case where it did not (two consecutive interleaved `M`-frames ate both budgeted attempts, forcing a disconnect anyway). So the interleaved-message trigger is not reliably self-healing either — but the wrong-shape/NAK trigger (`1715`, fast, deterministic, identical every attempt) has, in every one of the 4 instances captured live today, **never once** recovered within the existing 3-attempt budget. That is a narrower, more specific case for skipping the same-sequence retry *for this exact signature* than for the interleaved-message trigger generally (see `## Open questions`, OQ3).

## Follow-up sub-experiments (designed, not yet run)

Two more open questions surfaced by the events above are decisively testable rather than left as speculation. Both scripts are written and compile-checked; neither has been executed against the live panel yet — that needs the same pre-run confirmation (and the production add-on confirmed stopped) as every other live experiment in this spike.

**`contention_experiment.py`** (targets OQ1): self-contained, no phone app needed. Client A holds a real session on production's ~15s idle/keepalive cadence; concurrently Client B persistently retries `connect()`+`login()` every 1.5s, and on success holds the session for a 12s dwell (sending its own keepalives, mirroring active app use) before releasing and resuming retries. Every attempt/result from both clients is written to a shared, timestamped `contention.jsonl` so a rival success can be correlated against the incumbent's very next keepalive outcome. Ends early (before the configured window) the moment the incumbent is displaced or fails — that event *is* the finding.

| Criterion | Target | Actual |
|-----------|--------|--------|
| Can persistent (not single-shot) rival login contention be shown to displace the incumbent and trigger its NAK, reproducing the bug on demand? | Observe at least one incumbent-displacement event correlated with a rival success, or confirm it does not happen even under sustained contention | — (not yet run) |

**`reconnect_race_experiment.py`** + **`_reconnect_probe.py`** (targets OQ2): runs the same production-faithful monitor loop as `experiment.py`, but the moment a forced disconnect fires, races three recovery strategies concurrently from the same instant — `instance_fresh` (this capture's existing pattern: new `PanelClient` instance every attempt, immediate first try), `instance_reused` (production's exact `reconnect_after_disconnect` pattern: same instance, `close()`+`connect()`/`login()`, delay before every attempt including the first), and `fresh_process` (an independent OS subprocess retrying on its own 2s cadence via `_reconnect_probe.py`). Whichever wins resumes monitoring; the losers are cancelled/killed immediately so only one client ever holds the panel's single connection slot. Logs every attempt and the winning margin to `race.jsonl`, and repeats on every subsequent natural forced-disconnect for the run's duration — no human needs to notice and intervene.

| Criterion | Target | Actual |
|-----------|--------|--------|
| Which reconnect strategy (if any) recovers fastest after a real forced disconnect, and by how much? | Measured elapsed-time-to-success for all three strategies, raced from the same starting instant, across multiple natural events | — (not yet run) |
| Do all three strategies converge to roughly the same recovery time (supporting "it was just elapsed contention, not the client")? | Compare winning margins across events | — (not yet run) |

## Results

<!-- State: Draft — leave blank -->

## Conclusion

<!-- State: Draft — leave blank -->

## Options

### Option A: {name}

<!-- Description. Pros. Cons. Fit with project context. -->

### Option B: {name}

<!-- Description. Pros. Cons. Fit with project context. -->

## Recommendation

<!-- populated in Phase 4 -->

## Decisions required

<!-- populated in Phase 4 -->

## Open questions

The capture answered the original question (the 2-byte reply is `0x15` NAK, not `0x06` ACK) but the investigation it triggered surfaced several new, more consequential unknowns that remain open. None of these has an experiment result yet; each names what would resolve it and, where a follow-up experiment has been designed (`## Follow-up sub-experiments`), the script that targets it.

**OQ1 — Does *persistent* rival contention (not a single attempt) induce the incumbent's NAK, and can the bug be reproduced on demand?** The wait-threshold sub-experiment showed a *single* rival `connect()` is refused outright at the TCP level while a session is active — the panel won't even accept the second socket. But the real-world events (3 and 4) showed the opposite outcome: the Texecom app *displaced* the incumbent, which then saw the `1715` NAK. Those two observations are in tension. The unexplored variable is persistence: a phone app plausibly keeps retrying after a refusal rather than giving up after one attempt, and/or interleaves its own login bytes with the incumbent's in-flight keepalive in a way a single clean `connect()`+`close()` never would. Targeted by `contention_experiment.py` — if it reproduces a displacement on demand, that would be the first on-demand repro of the household's bug.

**OQ2 — Is "kill the process and restart" causally necessary, or a timing coincidence?** Every kill-and-restart in events 2-4 happened after (and shortly after) a real-world signal that the competing contention had plausibly cleared (the household closing the app). It's possible the in-place retry loop would have *also* succeeded at roughly the same moment if left alone, and the restart's apparent effect is confounded by that timing rather than causal. Since `experiment.py`'s existing in-place retry already builds a fresh `PanelClient` instance every attempt (same process) and still got stuck, "fresh instance" alone is ruled out as the explanation — leaving "fresh OS process" and "just needed to wait for real contention to clear" as the two live hypotheses, plus production's actual same-instance-reused pattern (`reconnect_after_disconnect`) as a third, entirely untested shape. Targeted by `reconnect_race_experiment.py`, which races all three from the same forced-disconnect instant.

**OQ3 — Should the bounded same-sequence retry be skipped for the wrong-shape/NAK signature specifically?** Per `## Additional finding` above, the NAK signature (`1715`, fast, identical every attempt) has never once recovered within budget across 4 live instances, while the interleaved-message signature (the `TASK-47` scenario) has a mixed record — sometimes recovers, sometimes doesn't, per the household's own report. This suggests a signature-specific policy (skip the retry budget only for the recognisable NAK shape; keep it for interleaved-message, where it has demonstrated value) rather than a uniform "drop everything immediately" rule. Answerable from data already gathered — no new capture needed — but not yet through a design/decision pass. Its benefit is bounded: it saves ~600ms per event, not the extended (tens-of-minutes) outages that OQ1/OQ2 are about.

**OQ4 — Is the household's Texecom app actually configured against the *same* local-control module this add-on uses?** ADR-013 assumes a household has two separate IP modules — one dedicated to Home Assistant/local control, one for the phone app and monitoring station — precisely so Home Assistant doesn't contend with the phone app. Event 3's direct observation (opening the app displaced this capture) is hard to reconcile with that assumption holding for this household. **Not resolvable by more protocol captures** — it requires checking the Texecom app's own connection settings (which IP/port it dials) and/or the panel's engineer menu for how many IP modules are fitted and which address each answers on. If the app is pointed at the *same* module as this add-on, that is a simpler, more actionable root cause than any protocol-level fix — worth checking before investing further in reconnect-policy changes. This is a question for the household/installer, not a script.

A follow-up spike-continuation session (running `contention_experiment.py` and `reconnect_race_experiment.py` live, plus the household checking OQ4) is needed before this spike can move to `Validated ✅` — the original question is answered, but the investigation it opened is not yet closed.
