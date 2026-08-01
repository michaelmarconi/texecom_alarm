# ADR-002: Use Frame Resync and Asymmetric Reconnect for Panel Protocol Collisions

**Status:** Accepted ✅
**Date:** 2026-08-01
**Spike:** [spike-002-arm-home-triggered-framing/SPIKE.md](../spikes/spike-002-arm-home-triggered-framing/SPIKE.md)

## Overview

**Background:** The current alarm-panel integration crashes whenever the panel is armed to Home mode or a real alarm is triggered, because the panel occasionally sends unexpected, non-alarm-protocol data over the same connection our integration uses, and the integration cannot handle it.
**Decision:** The client will skip over this unexpected data instead of crashing, and will wait longer and retry more patiently to reconnect after a real alarm trigger than after an ordinary arm or disarm.
**Why this way:** Asking the panel installer to rewire its reporting configuration might reduce how often this happens, but that is an installer-level change outside this project's control and is not guaranteed to eliminate the behaviour; making the client resilient by design works regardless, and the evidence shows this is normal, recurring panel behaviour rather than a one-off bug to route around.
**What this constrains:**
- The wire-protocol client must never treat an unrecognised or corrupted chunk of data as a fatal error; it must skip past it and keep listening for valid panel messages.
- Reconnection after a dropped connection must not use one fixed timeout/attempt budget for every situation — it must wait substantially longer and retry more times after a real alarm trigger than after an ordinary arm/disarm.
- The integration should show a "reconnecting" or degraded-connectivity status to the user during this recovery window rather than failing silently or crashing.
- The panel's reporting/Com-Port configuration should still be checked and recorded as a one-time, secondary mitigation, but the client's correctness cannot depend on that configuration being available or unchanged.
**Open follow-ons:**
- The exact wait times and retry counts for the reconnect schedule are not yet finalised — only one real data point exists (a ~50 second window that was insufficient after a real trigger).
- What "alarm reset" should mean as a signal the integration can act on is a separate, still-open decision (see the source spike's Decision required #5) — not resolved by this ADR.

## Context

The project's alarm-panel integration must issue `arm_home` and report a full triggered-alarm event over the panel's binary Connect protocol, but the current production add-on this project is replacing is known to crash during exactly these actions. [SPIKE-002](../spikes/spike-002-arm-home-triggered-framing/SPIKE.md) investigated this crash empirically against the live panel and found it is not a same-protocol send/receive timing race (that case is confirmed recoverable via ordinary timeout-and-retry). It is instead the panel's own SmartCom/ComIP hardware multiplexing a second, non-Connect-protocol byte stream — identified specifically as literal Hayes AT modem commands (`ATH0`, `ATZ`) from its dialer/reporting subsystem — onto the same TCP session around arm, disarm, and trigger events, including plain keypad-originated ones. The spike also confirmed the panel forcibly drops the TCP connection the instant a real alarm triggers, and that recovering from this specific disruption takes substantially longer than recovering from an ordinary arm/disarm collision.

## Decision drivers

- The client must not crash or require a manual restart when the panel emits unexpected, non-conforming bytes on the ComIP session.
- The client must reliably decode `arm_home` and a full trigger sequence (entry → alarm active → forced disconnect) without manual intervention.
- The client must recover connectivity after a forced disconnect within a bounded, event-appropriate time, rather than giving up immediately or retrying indefinitely with no visible status.
- The approach must not require guessing an undocumented command or taking an unverified action against a live, occupied household security system.
- The approach should not depend solely on a panel configuration change that is outside this codebase's control (an installer/engineer-level setting) and not guaranteed to be available on every installation.

## Options considered

- **Option A: Client-side resilience only** — scan forward past any unexpected frame byte and resume parsing, but keep a single, uniform reconnect policy for every disconnect. Rejected because: it addresses the byte-level corruption but not the empirically-measured fact that a full alarm trigger's disconnect takes much longer to recover from than an ordinary arm/disarm collision — a uniform reconnect budget would either give up too early after a trigger or be needlessly slow after routine arm/disarm activity.
- **Option B: Panel/network-side mitigation only** — isolate the panel's Com Port from ARC/remote-reporting traffic so the non-Connect-protocol bytes are never emitted in the first place, with no client-side changes. Rejected because: this is an installer/engineer-level panel setting outside this codebase's control, is not guaranteed to be available or effective on this specific installation, and does not address the confirmed forced-disconnect behaviour during a real trigger, which the spike showed occurs independently of Com Port assignment.
- **Option C: Defense in depth — client-side resync plus an asymmetric reconnect budget, with the Com Port check as a secondary mitigation.**

## Decision

Chosen option: **Option C.**

This is the only option that satisfies all the decision drivers together: frame resync (from Option A) directly stops the corruption from being fatal, the asymmetric reconnect budget directly reflects the spike's measured difference in disruption duration between arm/disarm and trigger events, and checking the panel's Com Port configuration (from Option B) is retained as a low-cost, no-downside secondary mitigation even though it cannot be relied upon alone.

## Consequences

**Positive:** The integration can decode `arm_home` and a full triggered-alarm sequence without crashing, matching this project's core requirement to replace the currently-crashing add-on. The client degrades gracefully (skips bad data, then reconnects with an appropriate wait) instead of failing hard, which was the original, unresolved crash symptom.

**Negative:** The wire-protocol client is more complex than a naive frame parser — it needs a byte-scanning resync loop and a way to distinguish "just armed/disarmed" from "a real trigger occurred" so it can pick the right reconnect budget, rather than a single fixed timeout. The exact reconnect budget is not yet backed by enough data to guarantee it is always sufficient (only one real trigger was observed); a production deployment may still occasionally need to show a "reconnecting" status for longer than expected.

**Follow-on:** The specific reconnect wait times/retry counts still need to be set (see Open follow-ons) — likely as a configurable default with room to tune once more real-world trigger events are observed. The panel's Com Port/UDL configuration should be checked and recorded as originally scoped in the spike, independent of this ADR's implementation work.

## Confirmation

This decision is correctly implemented when the production wire-protocol client, tested against the live panel (or a recorded replay of this spike's captured traffic), survives a keypad-driven `arm_home` and a full deliberate alarm trigger end-to-end without crashing: it decodes `Part Arm 2`/`part armed` and `Alarm Active`/`Bell Active`/`in alarm` events, resyncs past any corrupted bytes without raising, and successfully reconnects after the panel's forced disconnect within its configured post-trigger budget — with a visible "reconnecting" status shown for the duration.
