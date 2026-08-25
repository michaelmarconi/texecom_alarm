# ADR-017: Use a Configurable 5-Minute Interval for the Panel Reconciliation Poll

**Status:** Accepted ✅
**Date:** 2026-08-25

## Overview

**Background:** Now that the connection signal no longer depends on the panel reconciliation poll (ADR-016), that poll's fixed 30-second cadence no longer serves any purpose — it was only ever set that tight to double as a fast connectivity check. Running it that often was also suspected (unconfirmed) of contributing to occasional audible pips from the physical panel.
**Decision:** Slow the reconciliation poll to run every 5 minutes by default, and let the household change that interval through add-on settings.
**Why this way:** The reconciliation poll is now a rare-case safety net rather than a fast health check, so a much longer interval is safe. Making it a setting rather than a fixed number lets a household trade off reconciliation freshness against panel noise or traffic on their own install, without needing a code change.
**What this constrains:**
- The reconciliation poll's timing must not be tied to any connectivity-detection bound.
- The interval must be an add-on setting, not a hardcoded value, shipping with 5 minutes as the default.
- A missed live update can now sit uncorrected for up to one full interval (5 minutes by default) instead of 30 seconds; this is not a safety-relevant delay — no siren or lockout behaviour depends on this poll (unchanged from ADR-016).
**Open follow-ons:**
- Whether the panel pips the household hears are actually caused by this poll is still unconfirmed. If a household later finds a different cause, that does not change the correctness of this decision — the interval was already free to change once ADR-016 decoupled it from connectivity.
- Sensible minimum/maximum bounds on the configurable value are ordinary build validation, not decided here.

## Context

ADR-016 removed the connectivity signal's dependence on the panel reconciliation poll, which removed the reason its interval was locked at 30 seconds. Separately, the household reported occasional audible pips from the physical panel and wondered whether this poll caused them. Regardless of that unconfirmed cause, decoupling the poll from connectivity already freed its interval to be tuned as a product choice rather than a detection-latency requirement.

## Decision drivers

- The interval no longer needs to satisfy any fast-detection bound — that responsibility moved to ADR-016's check-in/command-reject signals.
- Reconciliation staleness after a rare missed live update should stay bounded and known, not open-ended.
- The household should be able to tune this without a code change, since the right trade-off (noise sensitivity vs. freshness) may differ by install.

## Options considered

- **Keep the fixed 30-second interval** — Rejected because: it was only ever chosen to satisfy the now-removed connectivity requirement; keeping it provides no remaining benefit and may be contributing to unwanted panel noise.
- **Configurable with a much longer or no default (e.g. 30 minutes, or manual-only)** — Rejected because: leaves reconciliation staleness too open-ended for a household that hasn't tuned the setting; a deliberate default is preferable to an unbounded one.
- **Configurable, default 5 minutes** — chosen.

## Decision

Chosen option: **Configurable, default 5 minutes**

This bounds reconciliation staleness at a level the household considers acceptable out of the box, while giving them a documented setting to change it instead of a hardcoded value they'd need a code change to adjust.

## Consequences

**Positive:** Removes an artificial tie to a now-irrelevant fast-detection number; gives the household direct control over reconciliation frequency; may reduce the suspected panel noise (pending confirmation).

**Negative:** A missed live update can now sit uncorrected for up to 5 minutes (or longer, if configured higher) instead of 30 seconds, before the reconciliation poll catches it — a real, if narrow, increase in worst-case staleness for an already-rare failure mode.

**Follow-on:** Confirming the actual cause of the panel pips remains open and does not affect the correctness of this decision either way. Input validation on the configurable value is ordinary build work, not decided here.

**CI vs live:** A hermetic/FakePanel test may claim the poll fires on the configured interval (5 minutes by default) and that changing the setting changes that interval, without affecting the connection signal at all. Whether this measurably changes the household's audible pips remains live-only and unconfirmed.

## Confirmation

A test confirms the reconciliation poll fires on the configured interval (defaulting to 5 minutes when unset), that changing the add-on setting changes the fired interval, and that neither firing nor failing to fire this poll affects the connection signal (ADR-016).

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-25 | Clear | — |
