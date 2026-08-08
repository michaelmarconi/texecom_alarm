# Spike: silent-panel-path-death-detection

**Resolves:** RISK-012 / SPIKE-008  
**Date:** 2026-08-08  
**Type:** Comparison  
**State:** Validated ✅  

## Overview

**Question:** When the panel connection still looks healthy but updates or commands are no longer trustworthy, which detection approach marks the link degraded quickly without false alarms on a quiet house?
**Answer:** Watching for missing zone traffic alone false-alarms on a quiet house and misses command rejects while keepalives still work. Watching only for failed keepalives also misses those command rejects. The winning approach has two parts: (1) a rejected arm/disarm is itself an event that the link may be untrustworthy — do not wait for the idle heartbeat to fail; (2) separately from that heartbeat, periodically ask the panel for current house/arm state as a poll, so silent stalls are caught even when nobody is pressing arm. Allow automatic recovery after a quiet window so one blip does not stick forever.
**Recommendation:** Adopt that combination — treat command rejects as a degrade signal, and add periodic house-state polling alongside (not instead of) the existing idle heartbeat; do not use traffic-absence alone; do not rely on heartbeat failure alone for command-path zombies.
**Decisions this unlocks:**
- Which silent-death detection mechanism the connectivity signal should implement
- Whether a single rejected arm/disarm may briefly mark the link degraded and how it returns to live
- What continuous-integration stand-ins may claim versus what still needs a live household walk

## Question

When a previously healthy panel session still looks live (connectivity on, keepalives succeeding) but the path is untrustworthy — especially arm/disarm NAK or “app stopped working” until restart — which detection approach marks degraded within tens of seconds without flapping on a quiet house, and without treating the official smartphone app as the cause?

## Hypothesis

We believe a combination of (1) treating arm/disarm NAK or command timeout on a session that still reports live as immediate degraded, plus (2) a bounded periodic panel-state corroboration probe, will detect both “command-path zombie” and silent push drought within tens of seconds, while traffic-absence alone will either miss the NAK zombie (keepalives still succeed) or false-degrade on a quiet house — because today’s live NAKs arrived on an otherwise healthy-looking session.

## Research

**Product requirement (Accepted `spec-panel-link-liveness`):** After a session looked live, silent untrustworthy path must set **Alarm Panel Connected** degraded within tens of seconds; zone/alarm entities stay available with last-known state (ADR-004); recovery re-syncs without a manual add-on restart. Exact numeric bound (30 vs 60s) left to plan time unless a protocol minimum appears.

**What ships today:** Connectivity is `ON` after successful login/snapshots and `OFF` only on the clean `ForcedDisconnect` reconnect path (`reconnect.py`). The listen loop uses a ~15s idle timeout then `GETDATETIME` keepalive (`app.py` / `PanelClient.keepalive`). Arm NAK is logged and MQTT state is republished (`arm_commands.py`) but **does not** flip connectivity. So a “zombie” session — keepalives OK, arm gets `SETAREAARM NAK` — still shows live to automations. Restart clears it (observed 2026-08-07/08); cause of the panel-side reject remains unknown.

**Live reframes (2026-08-08 walks):** Official smartphone app open does **not** monopolise the Connect login once this add-on holds the session (Away from HA while iOS open ACK’d; iOS disarm reflected via panel LOG). Contended traffic can slow ACK or produce interleaved frames; that is distinct from exclusive hogging. Command-path zombie (repeated Away NAK while session otherwise healthy, including with iOS already closed) is the household-facing failure mode this spike must catch.

**Candidate mechanisms (from analysis / spec):**

| Mechanism | Idea | Blind spot / risk |
|-----------|------|-------------------|
| A. Traffic-absence | Degrade if no ZONE/AREA (etc.) for N seconds | Quiet house with no zone activity for hours → false degraded; keepalive-only zombie with rejects still “has traffic” if LOG/OUTPUT continue |
| B. Idle-probe failure | Degrade when keepalive/GETDATETIME times out or fails | Misses command-path zombie where keepalive still succeeds |
| C. Periodic corroboration | Timed `GetAreaFlags` (and/or zone snapshot) vs last published state / hard fail on NAK/timeout | Extra round-trips; must not flap on benign NAK; still may miss “accepts reads, rejects arm” unless combined with command signals |
| D. Combination (hypothesis) | Immediate degraded on arm/disarm NAK or command timeout **plus** bounded periodic corroboration; **not** traffic-absence alone | Must define recover-to-live rules so a single transient NAK does not strand degraded forever |

**CI vs live already implied by architecture:** FakePanel can simulate silence-after-healthy, keepalive-OK+command-NAK, and quiet-no-pushes. Quiet-house false-positive rate on a real idle night remains `/accept` live corroboration.

**Out of scope for this spike’s decision:** Root-causing *why* the panel NAKs (engineer config, Soft ComIP hang, etc.); Com Port isolation (RISK-011); startup progressive login backoff (separate accepted spec).

## Experiment Design

Throwaway comparison harness in `experiment.py` (no production wiring): a discrete-event simulator of panel-session observations at 1s resolution, plus four detectors evaluated on the same scenario timelines. Uses no live ComIP and no MQTT — pure logic so CI can re-run the comparison later if desired; FakePanel integration is a follow-on build concern once a mechanism is chosen.

**Detectors under test**

1. **TrafficAbsence(N=60s)** — degrade when time since last ZONE/AREA/LOG event ≥ N (keepalive does not count as “trustworthy traffic”).
2. **IdleProbeFail** — degrade only when a keepalive attempt fails or times out (mirrors today’s probe semantics as a *sole* detector).
3. **PeriodicCorroboration(interval=30s)** — every 30s issue a synthetic `GetAreaFlags`; degrade on probe NAK/timeout; also degrade if returned flags disagree with last known arm snapshot after a commanded change window (simple mismatch flag in the scenario feed).
4. **Combination** — two cooperating signals, neither of which is “TCP/idle heartbeat alone”:
   - **Command reject as event:** arm/disarm NAK or command timeout immediately marks degraded (the heartbeat may still be succeeding — that is the zombie case).
   - **Periodic house-state poll:** same corroboration as (3) — ask the panel for current area/arm state on an interval; degrade on poll NAK/timeout/mismatch. This sits **alongside** the existing idle keepalive (`GETDATETIME`), not as a replacement for it.
   - Never degrade on traffic silence alone. Recover-to-live when the next corroboration succeeds *and* no command failure in the last recover window (30s) — so a single NAK does not require manual restart, but a NAK streak keeps degraded.

**Scenarios (shared clock)**

| ID | Name | Timeline (compressed) |
|----|------|------------------------|
| S1 | Quiet house | 600s healthy: keepalive OK every 15s; zero ZONE/AREA/LOG |
| S2 | Silent death | 60s healthy, then keepalive always timeout; no pushes |
| S3 | Command-path zombie | 60s healthy, then keepalive OK forever; Away arm at t=70,90,110 all NAK; LOG every 10s through the zombie window (no ZONE/AREA) so TrafficAbsence sees “traffic” and must miss |
| S4 | Clean disconnect | 60s healthy, then socket close / forced disconnect at t=70 (subsequent keepalives and corroboration probes fail/timeout) |
| S5 | Transient single NAK | Healthy; one Away NAK at t=70; successful Away ACK at t=100; corroboration OK thereafter |

**Pass bar (Decision Criteria targets)** — Comparison winner must satisfy all “must” rows; runners-up recorded for ADR trade-offs.

### Decision Criteria

| Criterion | Target | Actual |
|-----------|--------|--------|
| S1 Quiet house: false degrade | Combination and IdleProbeFail: never degraded over 600s; TrafficAbsence: expect fail (false degrade) | Combination first_degraded=None; IdleProbeFail first_degraded=None; TrafficAbsence first_degraded=60 (false degrade as expected) |
| S2 Silent death: detect ≤30s after first failed keepalive | Combination and IdleProbeFail and PeriodicCorroboration: degraded within 30s of silence onset; TrafficAbsence may also | Onset t=75: Combination first_degraded=90; IdleProbeFail=75; PeriodicCorroboration=90 (all ≤30s) |
| S3 Command zombie: detect ≤30s after first NAK | Combination: degraded at or before t=100 (≤30s after first NAK at t=70); IdleProbeFail: still live at t=120; TrafficAbsence: still live at t=120 (LOG feed) | Combination first_degraded=70; IdleProbeFail first_degraded=None; TrafficAbsence still live at t=120 (first_degraded=210 after feed ends) |
| S4 Clean disconnect | IdleProbeFail, PeriodicCorroboration, and Combination: each degraded by t=100 (≤30s after drop at t=70); TrafficAbsence: no required pass (may stay live until 60s silence) | IdleProbeFail=70; PeriodicCorroboration=70; Combination=70 |
| S5 Transient NAK | Combination: degraded at some t≥70; live again by t=160 (≤60s after successful arm at t=100) without manual restart | first_degraded=70; live_again=120 |
| Hypothesis overall | Combination meets S1–S5 targets; TrafficAbsence alone fails S1 and/or S3; IdleProbeFail alone fails S3 | 14/14 checks passed; Combination wins; TrafficAbsence fails S1; IdleProbeFail misses S3 |

*Actuals are populated from experiment output only — not from documentation, vendor claims, or community reports.*

## Results

Command (worktree):

```text
python3 docs/spikes/spike-008-silent-panel-path-death-detection/experiment.py
```

Raw output:

```text
SPIKE-008 detector comparison (hermetic simulator)
============================================================
[PASS] S1 Combination never degraded: first_degraded=None
[PASS] S1 IdleProbeFail never degraded: first_degraded=None
[PASS] S1 TrafficAbsence false-degrades (expected fail of that detector): first_degraded=60
[PASS] S2 Combination degrade ≤30s after silence onset: first_degraded=90 onset=75
[PASS] S2 IdleProbeFail degrade ≤30s after silence onset: first_degraded=75 onset=75
[PASS] S2 PeriodicCorroboration degrade ≤30s after silence onset: first_degraded=90 onset=75
[PASS] S3 Combination degraded by t=100: first_degraded=70
[PASS] S3 IdleProbeFail still live at t=120: first_degraded=None
[PASS] S3 TrafficAbsence still live at t=120 (LOG feed): first_degraded=210
[PASS] S4 IdleProbeFail degraded by t=100: first_degraded=70
[PASS] S4 PeriodicCorroboration degraded by t=100: first_degraded=70
[PASS] S4 Combination degraded by t=100: first_degraded=70
[PASS] S5 Combination degrades then live again by t=160: first_degraded=70 live_again=120
[PASS] Hypothesis overall (Combination wins; TA fails S1; Idle misses S3): combo_s1=True combo_s3=True combo_s5=True ta_false_s1=True idle_miss_s3=True ta_miss_s3=True
============================================================
14/14 checks passed
```

## Conclusion

**Hypothesis supported** — Combination met S1–S5 targets. In plain terms: a NAK is treated as a degrade *event*, and a periodic house-state poll runs in addition to the idle heartbeat — the heartbeat alone is not trusted as proof the path is good. TrafficAbsence alone false-degraded on the quiet-house timeline (S1) and missed the command-path zombie while LOG traffic continued (S3). IdleProbeFail alone caught silent death and clean disconnect (S2/S4) but stayed live through repeated arm NAKs with successful keepalives (S3). PeriodicCorroboration alone covered silence/disconnect but is insufficient without the command-failure signal for the NAK zombie. Combination recovered after a transient NAK once corroboration succeeded past the 30s recover window (S5: live_again=120).

**CI vs live:** A hermetic simulator (and later FakePanel scenarios of the same shapes) may claim detector-selection behaviour and regression of the comparison table. Live-only remain: real quiet-house false-positive rate, real zombie reproduction, whether every panel NAK should degrade vs only NAK-with-failed-corroboration, and reconnect UX after degrade. This experiment does **not** prove panel causation of zombies.

## Options

### Option A: Traffic-absence alone

Degrade when ZONE/AREA/LOG go quiet for N seconds. Pros: simple. Cons: experiment S1 false-degraded at t=60 with no zone activity; S3 missed zombie while LOG continued. Unfit as sole detector.

### Option B: Idle-probe failure alone

Degrade only when keepalive fails. Pros: matches today’s probe; catches S2/S4. Cons: experiment S3 stayed live through three Away NAKs. Does not address the household “app stopped working” zombie.

### Option C: Periodic corroboration alone

Timed state reads; degrade on probe fail. Pros: catches silent stalls even if keepalive is optimistic. Cons: without command-failure coupling, still misses “reads OK, arm NAK” zombies; extra round-trips always.

### Option D: Combination (NAK-as-event + periodic house-state poll)

- **NAK / command timeout** → immediate “may be degraded” (event), even if the idle heartbeat is still OK.
- **Periodic poll** of panel house/arm state → catch silent stalls; this is *not* the TCP/idle heartbeat — heartbeat stays for session keep-alive; the poll is a separate trust check.
- Recover after successful poll with no recent command failure.

Pros: only option that met all S1–S5 targets in the experiment. Cons: a legitimate single NAK briefly marks degraded (S5 recovered automatically); exact NAK classification and reconnect policy remain product decisions for ADR/plan.

## Recommendation

**Option D (Combination).** Criteria S1–S5 and the hypothesis overall check all passed in `experiment.py`. Reject A and B as sole mechanisms; treat C as a component of D, not a standalone winner.

Clarify for implementers: do **not** replace `GETDATETIME` keepalive with the state poll — keep both. NAK is a degrade *signal*; the poll is continuous corroboration.

Assumptions: synthetic scenarios match the failure modes we care about; live quiet-house and live zombie walks still corroborate after build. Do **not** equate “degrade on NAK” with “always auto-retry the same arm inside one tap” — recovery of the session and retry policy are separate follow-on decisions.

## Decisions required

- Should **Alarm Panel Connected** implement Combination: treat arm/disarm NAK/timeout as a degrade *event*, plus periodic house/arm-state polling alongside the existing idle keepalive (rejecting traffic-absence-alone and keepalive-alone as sufficient)?
- On a single arm/disarm NAK, should connectivity go degraded immediately (as in the winning detector), with automatic return to live after corroboration + recover window — accepting a brief degraded blip on legitimate rejects?
- After degraded, should the app automatically tear down and re-login (session recovery), and is auto-retry of the failed command in-scope or explicitly out of scope for the first ADR?
- What may CI / FakePanel claim for silent-death detection versus what remains `/accept` live corroboration (quiet house, real zombie)?

## Open questions

- Exact numeric bounds (corroboration interval, recover window, “tens of seconds”) — settle at plan time unless live walks force a change.
- Narrow NAK classification (zombie vs honest panel reject) before aggressive auto-retry.
- Whether periodic corroboration should be `GetAreaFlags` only or also zone snapshot.
- Live quiet-house overnight false-positive rate after implementation.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-08 | Design: Revise before running | 2 |
| 2 | 2026-08-08 | Design: Ready to run | — (S3 LOG feed + per-detector S4 targets applied) |
