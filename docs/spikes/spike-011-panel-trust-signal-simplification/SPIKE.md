# Spike: panel-trust-signal-simplification

**Resolves:** unlisted (no matching RISK-NNN in analysis.md) / SPIKE-011
**Date:** 2026-08-25
**Type:** Comparison
**State:** Validated ✅

## Overview

**Question:** With about 24 hours of stable live running on the new dedicated panel connection, would a simpler detection design — treat the connection as down only after a couple of missed routine check-ins, plus immediately flag it if an actual arm/disarm command gets rejected — still catch real connection problems quickly, without producing false "disconnected" blips like today's (where a single background health-check got delayed during a burst of panel activity, even though nothing was actually wrong)?
**Answer:** Yes. The simpler design catches every failure shape the current design catches — often faster — and does not produce the false "down" blip seen in the 2026-08-25 live incident, because that blip came entirely from the background poll, which the simpler design no longer uses for this signal.
**Recommendation:** Simplify how the connectivity light decides "down": missed check-ins or a rejected arm/disarm command only. Keep the background poll running for its separate job (double-checking alarm state), just stop letting its result flip the connectivity light.
**Decisions this unlocks:**
- Whether to change how the connectivity light decides "down" (drop the background poll from that decision)
- Whether the background poll should keep running for its other job, or be removed entirely
- Whether the "still stuck, log back in" recovery path needs re-checking now that fewer things can flag the light as down

## Question

With about 24 hours of stable live running on the new dedicated panel connection, would a simpler detection design — treat the connection as down only after a couple of missed routine check-ins, plus immediately flag it if an actual arm/disarm command gets rejected — still catch real connection problems quickly, without producing false "disconnected" blips like today's (where a single background health-check got delayed during a burst of panel activity, even though nothing was actually wrong)?

## Hypothesis

We believe a simplified detector — degrade only after a couple of missed routine check-ins, or immediately on a rejected arm/disarm command — will pass every test case the current design passes (quiet house, total silence, command rejected while checks still pass, clean disconnect, one-off rejected command that clears itself) and will not falsely flag today's exact incident. This is because, looking back at the original comparison that justified today's design, the one failure case that background polling was supposedly needed for (commands getting silently rejected) was actually caught by the "immediately flag a rejected command" rule, not by the background polling itself.

## Research

The current design (ADR-010, from SPIKE-008, dated 2026-08-08/09) predates the
household's move to the dedicated local panel module (ADR-013/014, dated
2026-08-21) by about two weeks. SPIKE-008's own research notes from that
earlier period record "contended traffic can slow ACK or produce interleaved
frames" and a live command-path zombie (an arm command silently rejected
while routine check-ins kept succeeding) — observed on what later turned out
to be the wrong, shared module. SPIKE-008 compared four detection approaches
on five synthetic timelines (quiet house, silent death, command-path zombie,
clean disconnect, transient single reject) and its own results table shows
the periodic background poll's only unique win — catching the command-path
zombie — was actually delivered by the "reject a command → flag immediately"
rule, not by the poll itself: the poll-alone approach was explicitly rejected
in that spike as insufficient without the reject rule, and the reject rule
alone caught the zombie at the moment of rejection with no need for the
poll.

A live incident on 2026-08-25 (about 24 hours into stable running on the
dedicated module) showed the poll's remaining role: the connection was
flagged down for ~27 seconds after one scheduled background poll got no
reply, while routine check-ins succeeded throughout and zone updates kept
flowing live the entire time — evidence that the poll's failure did not
correspond to any actual loss of connectivity. Logs show the poll happened
to be sent right at the tail of a burst of panel-generated event traffic
(a keypad disarm), which plausibly delayed or dropped the panel's reply to
that one non-critical background request.

Together this suggests the periodic background poll may now be pure
downside for the connectivity signal specifically: its one validated unique
catch is already covered by the reject-a-command rule, and it is the only
piece that produced a false blip in the one live incident observed since the
module fix. It may still be useful for its secondary job (double-checking
alarm state against what was last announced), which is out of scope for this
spike — this spike is scoped to the connectivity signal only.

## Experiment Design

Comparison experiment, structured exactly like SPIKE-008's: a discrete-event
timeline simulator (1s resolution) run through two candidate detectors.

- **Combination** — the shipped design: a rejected/timed-out arm or disarm
  command flags down immediately; the periodic background poll also flags
  down on its own failure/timeout and is required to succeed (with no recent
  command failure) to recover. Reproduced faithfully from SPIKE-008 to serve
  as the control.
- **Simplified** (proposed) — a rejected/timed-out arm or disarm command
  still flags down immediately (unchanged); routine check-in (keepalive)
  failure or a clean disconnect also flags down; recovery needs a successful
  check-in with no recent command failure. The periodic background poll's
  own success/failure is not fed into this signal at all.

SPIKE-008's five original timelines (S1 quiet house, S2 silent death, S3
command-path zombie, S4 clean disconnect, S5 transient single reject) are
reused unchanged against both detectors, to confirm Simplified does not
regress anything Combination already caught. A sixth timeline, **S6**, is
added: routine check-ins succeed on every scheduled tick, no arm/disarm is
attempted, and exactly one scheduled background poll fails once (modelling
the panel being momentarily busy with unrelated event traffic) before the
next scheduled poll succeeds normally — the shape of the 2026-08-25 live
incident.

Throwaway code, `docs/spikes/spike-011-panel-trust-signal-simplification/experiment.py`.

### Decision Criteria

| Criterion | Target | Actual |
|-----------|--------|--------|
| S1 Quiet house: neither detector ever degrades | Combination and Simplified: `first_degraded=None` over 600s | **Met.** Both `first_degraded=None` |
| S2 Silent death: both detect within 30s of onset (t=75) | Combination and Simplified: degraded by t=105 | **Met.** Combination `first_degraded=90`; Simplified `first_degraded=75` (faster — reacts on the very next scheduled check-in) |
| S3 Command-path zombie: both detect by t=100 | Combination and Simplified: degraded by t=100 (first reject is at t=70) | **Met.** Both `first_degraded=70` (immediate, at the moment of the first reject) |
| S4 Clean disconnect: both detect by t=100 | Combination and Simplified: degraded by t=100 (drop at t=70) | **Met.** Both `first_degraded=70` |
| S5 Transient single reject: both degrade then recover by t=160 | Combination and Simplified: degraded ≥70, live again between 100 and 160 | **Met.** Combination `first_degraded=70 live_again=120`; Simplified `first_degraded=70 live_again=105` (faster — recovers on the next check-in past the recover window instead of waiting for the next 30s poll) |
| S6 Burst-starved single poll (2026-08-25 incident shape): Combination false-degrades, Simplified does not | Combination: `first_degraded` is set (reproduces the live false blip); Simplified: `first_degraded=None` | **Met.** Combination `first_degraded=90 live_again=120` (reproduces the false blip); Simplified `first_degraded=None` |
| Hypothesis overall | Simplified matches Combination on S1–S5 and avoids Combination's S6 false blip | **Met.** `simplified_matches_s1_s5=True combo_s6_false_blip=True simplified_s6_clean=True` — 13/13 checks passed |

*Actuals are populated from experiment output only — not from documentation, vendor claims, or community reports.*

## Results

Command (worktree):

```text
python3 docs/spikes/spike-011-panel-trust-signal-simplification/experiment.py
```

Raw output:

```text
SPIKE-011 detector comparison (hermetic simulator)
============================================================
[PASS] S1 Combination never degraded: first_degraded=None
[PASS] S1 Simplified never degraded: first_degraded=None
[PASS] S2 Combination degrade ≤30s after silence onset: first_degraded=90 onset=75
[PASS] S2 Simplified degrade ≤30s after silence onset: first_degraded=75 onset=75
[PASS] S3 Combination degraded by t=100: first_degraded=70
[PASS] S3 Simplified degraded by t=100: first_degraded=70
[PASS] S4 Combination degraded by t=100: first_degraded=70
[PASS] S4 Simplified degraded by t=100: first_degraded=70
[PASS] S5 Combination degrades then live again by t=160: first_degraded=70 live_again=120
[PASS] S5 Simplified degrades then live again by t=160: first_degraded=70 live_again=105
[PASS] S6 Combination false-degrades on the one-off starved poll (expected fail of the shipped design — reproduces the live incident): first_degraded=90 live_again=120
[PASS] S6 Simplified never degrades (no keepalive fail, no command in flight): first_degraded=None
[PASS] Hypothesis overall (Simplified matches Combination on S1-S5; avoids Combination's S6 false blip): simplified_matches_s1_s5=True combo_s6_false_blip=True simplified_s6_clean=True
============================================================
13/13 checks passed
```

## Conclusion

**Hypothesis supported** — 13/13 checks passed. Simplified matched Combination on every one of SPIKE-008's original five timelines (S1–S5), in two cases recovering *faster* than Combination (S2 silent death: `first_degraded=75` vs `90`; S5 transient reject: `live_again=105` vs `120`), because it no longer waits for the next 30-second background poll to notice or clear a problem — a routine check-in happens more often. On the new S6 timeline (the shape of the 2026-08-25 live incident), Combination reproduced the false blip (`first_degraded=90`) while Simplified stayed live throughout (`first_degraded=None`), because Simplified's degrade rule never looks at the background poll's outcome at all.

**CI vs live:** A hermetic simulator (and later FakePanel scenarios of the same shapes) may claim this detector-selection comparison and regress it going forward, exactly as SPIKE-008's comparison already does for the shipped design. Live-only, unchanged from SPIKE-008 and not newly resolved by this spike: real overnight quiet-house false-positive rate, and real command-path zombie reproduction. Also live-only and specific to this spike: whether the burst-starved-poll failure mode seen on 2026-08-25 recurs — this spike is grounded in one real incident plus the reused SPIKE-008 timelines, not a large sample of live starvation events.

## Options

### Option A: Keep Combination (status quo)

Leave the background poll wired into the connectivity signal as it is today. Pros: no change, no new risk. Cons: Actual S6 shows this design will keep producing false "down" blips whenever a routine background poll happens to land inside a burst of panel activity (a keypad arm/disarm, in particular) — exactly what triggered this investigation. Fit: matches today's code, does not address the reported problem.

### Option B: Simplified — drop the background poll from the connectivity signal (Recommended)

Keep immediate degrade on a rejected/timed-out arm or disarm command (unchanged — this is what actually catches a command-path zombie, per both this spike's and SPIKE-008's Actuals). Degrade on a missed routine check-in or a clean disconnect (unchanged in spirit from SPIKE-008's plain check-in-only detector, which already passed the silent-death and clean-disconnect cases on its own). Stop using the background poll's success or failure to flip the connectivity signal at all — it may keep running for its separate job of double-checking alarm state, which this spike did not test. Pros: matches every SPIKE-008 case (often faster), removes the one thing that produced the live false blip, fewer moving parts feeding one signal. Cons: removes a layer of defence against a *hypothetical* "check-ins succeed but heavier reads silently fail" zombie that neither this spike nor SPIKE-008 ever actually observed or modelled as a distinct failure mode. Fit: strong — directly matches the Actuals.

### Option C: Simplified, and also stop running the background poll altogether

As Option B, but remove the periodic poll entirely rather than leaving it running for its own resync purpose. Pros: simplest of all, fewest round trips on the single panel session. Cons: this spike only tested the *connectivity signal* — it did not test or model the poll's separate role of catching a missed alarm-state push, so removing the poll outright is not backed by this spike's Actuals. Fit: plausible follow-on, not something this spike can recommend on its own evidence.

## Recommendation

**Option B.** The Actuals show Simplified matches or beats Combination on every SPIKE-008 case and is the only one of the two that does not reproduce the 2026-08-25 false blip (S6). Option C is not rejected, but it is a separate question this spike did not test — the background poll's resync role is out of scope here.

Assumptions: SPIKE-008's five synthetic timelines still represent the failure modes that matter; the 2026-08-25 incident is representative of "poll starved by a burst of panel traffic" rather than a one-off; live quiet-house and live zombie corroboration remain open exactly as SPIKE-008 left them — this spike did not add new live evidence for those, only for the burst-starvation shape.

## Decisions required

- Should the panel-connection signal stop using the periodic background poll as a degrade trigger, keeping only missed check-ins/disconnect and immediate command-reject (this supersedes ADR-010's explicit requirement that the poll drives the signal)?
- Should the periodic background poll keep running for its separate alarm-state double-check job, or be removed entirely now that its connectivity role is gone (Option B vs Option C above) — not settled by this spike?
- Does ADR-011's "stayed down too long → tear down and log in again" path still make sense unchanged now that fewer things can flag the signal down, or does its timing need re-checking?

## Open questions

- Live overnight quiet-house false-positive rate for Simplified — unresolved, exactly as SPIKE-008 left it for Combination.
- Live command-path zombie reproduction for Simplified — unresolved, exactly as SPIKE-008 left it for Combination.
- Whether the burst-starved-poll shape (S6) recurs on further live running, or was specific to this one keypad-disarm event — only one live incident informed this scenario.
- The background poll's separate alarm-state resync role (Option B vs C) needs its own follow-on look; this spike deliberately left it running unchanged.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| — | — | Not yet reviewed | — |
