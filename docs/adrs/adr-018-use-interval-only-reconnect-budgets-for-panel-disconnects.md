# ADR-018: Use Interval-Only Reconnect Budgets for Panel Disconnects

**Status:** Accepted ✅
**Date:** 2026-08-26

## Overview

**Background:** The add-on's reconnect settings for an ordinary panel disconnect and a real-alarm-trigger disconnect each expose both an "attempts" count and a wait interval, implying a household can choose how many times the app tries before giving up. In practice the app never gives up — it keeps retrying forever at the chosen interval — so the attempts numbers never do anything beyond appearing in a log line.
**Decision:** Drop the attempts settings entirely. The only knob that still distinguishes an ordinary disconnect from a real-trigger disconnect is how long the app waits between retries; it always keeps retrying either way.
**Why this way:** Reinstating a real attempt limit was ruled out because the app already committed elsewhere to never giving up on reconnecting, so the household's alarm/zone display doesn't go blank during an outage. Keeping a non-functional "attempts" setting only adds a knob that looks like it controls something it doesn't.
**What this constrains:**
- The add-on's config schema must not expose settings that look like they bound behaviour but don't — a setting that is genuinely advisory/log-only should not be a schema-validated option at all.
- Reconnection after any panel disconnect keeps retrying indefinitely; the only thing a reconnect setting may still vary between disconnect types is the wait interval, never a stop condition.
- Anyone who previously set the attempts options (via add-on options or their environment-variable equivalents) will need those removed; they are dropped from the schema going forward, not silently ignored.
**Open follow-ons:**
- None.

## Context

The add-on's reconnect design distinguishes an ordinary panel disconnect from a real-alarm-trigger disconnect, waiting longer between retries after a trigger. That distinction originally also included a stated retry-count difference (wait "substantially longer and retry more times" after a trigger). Since then, the add-on separately settled on never giving up trying to reconnect at all, so the household's alarm/zone display never blanks just because the panel connection is slow to come back — the retry loop runs unconditionally until it succeeds. The retry-count settings were never removed once that indefinite-retry behaviour was in place; they still validate as add-on options and get threaded into the reconnect profile, but the retry loop itself only writes their value into a log line — it never uses them to decide whether to keep trying.

## Decision drivers

- Reconnection must keep retrying a dropped panel connection indefinitely, regardless of disconnect type — this is already settled, unconditional behaviour and is not being revisited here.
- The add-on's configuration surface should only expose settings that materially change behaviour — a household should be able to trust that changing a number changes something.
- Any change here must not alter the actual reconnect timing behaviour a household already relies on (the wait interval per disconnect type).

## Options considered

- **Keep the attempts settings, reword them as advisory/log-only.** Rejected because: it keeps a schema-validated setting a household can "tune" with zero effect on behaviour, which is worse for trust in the config surface than removing it outright.
- **Make the attempts settings real again (cap retries at the configured count).** Rejected because: this would mean giving up on reconnecting after a fixed number of tries, which conflicts with the add-on's settled requirement to never leave the household's alarm/zone display blank just because the panel link is slow to recover.
- **Remove the attempts settings; keep only the wait-interval settings, applied indefinitely.** Chosen.

## Decision

Chosen option: **Remove the attempts settings; keep only the wait-interval settings, applied indefinitely.**

This is the only option that keeps the existing, settled "never give up reconnecting" behaviour intact (driver 1) while not leaving a configuration option that implies control it doesn't have (driver 2), and it makes no change to the actual wait-interval behaviour a household already relies on (driver 3).

## Consequences

**Positive:** The add-on's config screen loses two settings that never did anything beyond appearing in a log line, moving toward a config surface where every remaining option is something a household can meaningfully change.

**Negative:** This is a config-schema change — any household or test fixture that set the attempts options (via the options file or their environment-variable equivalents) will need those removed; Supervisor may otherwise reject an options payload that still includes now-unknown keys.

**Follow-on:** None.

**CI vs live:** A hermetic test can fully verify this decision — that the reconnect loop still retries indefinitely using only the configured wait interval per disconnect type, and that the attempts settings no longer exist in the schema or the runtime settings object. Nothing here depends on live panel hardware.

## Confirmation

A test confirms that: (1) the attempts settings for both the normal and trigger reconnect profiles no longer appear in the add-on's config schema or the runtime settings object; (2) the reconnect loop for both an ordinary and a trigger disconnect still retries indefinitely, spaced by the configured wait interval, with no behavioural change to that timing.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-26 | Clear | — |
