# ADR-016: Use Keepalive Failure and Command-Reject Events for Panel-Connection Detection

**Status:** Accepted ✅
**Date:** 2026-08-25
**Spike:** [spike-011-panel-trust-signal-simplification/SPIKE.md](../spikes/spike-011-panel-trust-signal-simplification/SPIKE.md)
**Supersedes:** ADR-010

## Overview

**Background:** The panel-connection signal used to also depend on a periodic background health check. That check produced a false "disconnected" signal when it happened to be sent during a burst of ordinary panel activity, even though nothing was actually wrong — observed live on 2026-08-25.
**Decision:** The panel-connection signal now goes down only when routine check-ins stop succeeding (or the connection drops outright), or when an arm/disarm command is actually rejected or times out. The background health check no longer feeds this signal at all.
**Why this way:** A side-by-side comparison showed the background check's one unique benefit — catching a command that gets silently rejected — was already delivered just as well by watching command results directly. Keeping the background check wired into the connectivity decision added a real false-alarm risk with no offsetting protection, especially now that the panel connection runs on the correct dedicated hardware rather than the shared line this design was originally built around.
**What this constrains:**
- The connection signal must not depend on the background health check's success or failure.
- A rejected or timed-out arm/disarm command must still immediately mark the connection down.
- Missed routine check-ins or an outright disconnect must still mark the connection down, and it must recover automatically once check-ins resume — no manual restart required.
- The background health check keeps running for its separate job of correcting the alarm entity if it ever disagrees with the panel's last-known state; that job is not removed by this decision.
**Open follow-ons:**
- Whether the automatic "log back in" recovery path (used when the connection stays down too long) needs its timing re-checked now that fewer things can trigger the down state.
- Live confirmation of quiet-house and command-rejection behaviour on the simplified design remains open — inherited from the original detection work, not newly resolved here.
- The background health check's own interval and whether it should be configurable is a separate decision.

## Context

The panel-connection detection design (ADR-010, from a spike run 2026-08-08/09) combined two signals: an immediate flag on a rejected/timed-out arm or disarm command, and a periodic background poll of panel house/arm state. That design was built about two weeks before the household moved Home Assistant onto the dedicated local panel module (ADR-013/014); the original investigation's own notes describe contended traffic on the previous shared line as a real factor. A live incident on 2026-08-25 — about 24 hours into stable running on the corrected module — showed the background poll producing a ~27-second false "down" signal after one scheduled poll got no reply, while routine check-ins and live zone updates continued successfully throughout. SPIKE-011 re-ran the original design's five validated test scenarios, plus a new scenario matching this incident, against both the current design and a simplified design that drops the background poll from the connectivity decision.

## Decision drivers

- Must not reintroduce the failure modes the original design was built to solve: false "down" on a quiet house, and missing a command silently rejected while routine check-ins still succeed.
- Must detect real connection death and rejected commands within the same fast bound as today.
- Must not produce a false "down" signal from a single, isolated timeout on a non-critical background request while every other signal is healthy.
- Zone/alarm entity availability must remain governed only by whether the app process itself is running, unaffected by this decision.

## Options considered

- **Keep the background poll wired into the connectivity signal (status quo)** — Rejected because: SPIKE-011's new scenario reproduced the exact 2026-08-25 false-down blip with this design, and its one previously-cited unique benefit (catching a rejected command) was already delivered by the reject-event rule alone in the same comparison.
- **Simplified detection, and also stop running the background poll entirely** — Rejected as part of this decision because: it conflates two separable questions. The background poll's separate reconciliation role (correcting the alarm entity against the panel's last-known state) was not evaluated by this comparison and is not shown to be safe to remove.
- **Simplified detection: routine check-in failure/disconnect plus immediate command-reject, background poll kept running but not feeding this signal** — chosen.

## Decision

Chosen option: **Simplified detection (routine check-in + command-reject only)**

SPIKE-011 showed this option matches or exceeds the current design's detection and recovery speed on every one of the original validated test scenarios, and is the only one of the two compared that avoids the false-down shape observed live on 2026-08-25.

## Consequences

**Positive:** Removes the one demonstrated source of false "disconnected" signals seen on the live system; matches or improves detection/recovery speed on every previously-solved failure shape; fewer signals feed one decision, which is easier to reason about and to explain to the household.

**Negative:** Removes a layer of defence against a hypothetical failure mode — routine check-ins succeeding while a heavier background read silently fails for some other reason — that has never actually been observed or modelled as distinct from the already-covered command-rejection zombie.

**Follow-on:** The automatic "stayed down too long, log back in again" recovery path should be re-checked against this narrower set of degrade triggers as ordinary build follow-through, not re-decided here. The background poll's own interval and configurability is a separate decision.

**CI vs live:** A hermetic stand-in may claim all six comparison shapes exercised by SPIKE-011 (quiet house never degrades; silent death and clean disconnect degrade and recover; a rejected command degrades immediately and recovers after a clean window; a single isolated background-poll timeout with everything else healthy does not degrade) and regress them going forward. Live-only, unchanged from the original investigation: real overnight quiet-house false-positive rate, and real reproduction of a genuine command-rejection zombie on this simplified design.

## Confirmation

A hermetic/FakePanel suite reproduces all six SPIKE-011 scenarios against the shipped detector: never degrades on a quiet house with no activity; degrades within the fast bound on silent death, a rejected command, and a clean disconnect; degrades then auto-recovers after a single transient rejected command; and does **not** degrade when a single background reconciliation read times out in isolation (healthy check-ins throughout, no command in flight) — the exact shape of the 2026-08-25 incident.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-25 | Clear | — |
