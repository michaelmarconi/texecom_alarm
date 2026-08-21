# ADR-014: Use Host-Scoped Trigger-Disconnect Assumptions for Panel Reconnect Design

**Status:** Accepted ✅
**Date:** 2026-08-21
**Spike:** [spike-010-comip-stays-online/SPIKE.md](../spikes/spike-010-comip-stays-online/SPIKE.md)
**Supersedes:** ADR-002

## Overview

**Background:** This project's reconnect design was built on the belief that any real alarm always breaks Home Assistant's connection to the panel, and that belief was measured against the wrong household network address — the installer's signalling module, not the dedicated local-control module the homeowner added.
**Decision:** Treat the forced disconnect and wire noise around arm/disarm/trigger as expected mainly when Home Assistant shares a module with the panel's alarm-reporting path, not as universal panel behaviour. Keep every resilience mechanism in place unconditionally, but stop presenting the long, patient post-trigger reconnect wait as the normal, expected outcome for a correctly set-up install — it is now a safety net for misconfiguration, not the headline story.
**Why this way:** Leaving the old blanket claim in place would keep describing a correctly set-up household's normal behaviour as a known defect needing a workaround. Removing the resilience mechanisms instead would strip protection from every install that is still pointed at the wrong module, or where reporting is configured to go out through every module — and only one household's dedicated module has actually been proven not to need it.
**What this constrains:**
- Documentation and product messaging must not claim every alarm trigger disconnects Home Assistant from the panel; that is only expected when Home Assistant shares the module used for alarm reporting, or when the panel is configured to signal out through every fitted module.
- The app must keep its "skip unexpected data and reconnect" resilience unconditionally — it costs little and still protects installs that are on the wrong module or have not been checked.
- The long, patient post-trigger reconnect wait must remain available as a fallback, but must no longer be documented or coded as the expected outcome for someone who has followed the module-selection guidance.
- Any future claim that a correctly-configured install still drops at trigger needs its own new evidence — it cannot be inherited from the original spike, which ran on the wrong module.
**Open follow-ons:**
- Whether the command-path "zombie" detection behind other accepted decisions was also specific to the wrong module is not addressed by this ADR — that is a separate question for a future spike if pursued.
- The exact reconnect wait times and retry counts remain unset by this ADR (unchanged from the original open follow-on) — only the framing of when the long budget is expected to be exercised has changed.

## Context

The original decision recorded that a real alarm always forces the panel to drop Home Assistant's connection, and that unexpected non-protocol bytes appear routinely around arm, disarm, and trigger events. That record came from [SPIKE-002](../spikes/spike-002-arm-home-triggered-framing/SPIKE.md), run against `192.0.2.10:10001`. On 2026-08-21 that address was identified as the installer's SmartCom — the module the panel's alarm reporting and monitoring-station signalling actually use — not the dedicated local-control module the homeowner had separately installed for Home Assistant. [SPIKE-010](../spikes/spike-010-comip-stays-online/SPIKE.md) re-ran the same stress conditions (Home arm → disarm; arm → real trigger → Home Assistant disarm) against the correct dedicated module and found the connection stayed up throughout, including while the panel was simultaneously reporting the same alarm to the monitoring station and to the Texecom Connect phone app. The forced-disconnect behaviour SPIKE-002 measured did not reproduce on the correct module under the same real-world load.

## Decision drivers

- Must not describe a correctly-configured install's normal behaviour as a defect requiring a workaround, when live evidence on that configuration contradicts the claim.
- Must not remove protection for installs where Home Assistant is still pointed at the signalling module — confirmed as an easy, longstanding mistake to make, and not something this project can detect or prevent today.
- Must not generalise "unnecessary on this one household's install" into "unnecessary in general" — SPIKE-010 tested one household, one panel model, one walk-through; it did not test every install's reporting configuration.
- Must give implementers a clear, current rule for when the long trigger-reconnect budget is expected to actually be exercised in the field.
- Must preserve SPIKE-002's own record unedited — it accurately describes what was observed on the module it tested.

## Options considered

- **Option A: Leave ADR-002 unchanged.** Rejected because: it continues to assert as universal panel behaviour something SPIKE-010 has now contradicted on a correctly-configured install, and a future implementer reading ADR-002 alone would misdiagnose a household's module misconfiguration as an inherent protocol limitation.
- **Option B: Retire the frame-resync and asymmetric-reconnect mechanisms entirely**, on the grounds that the correctly-configured install did not need them. Rejected because: SPIKE-010 tested one install surviving specific stress walks — it did not prove the failure mode is impossible on every install. Removing the mechanisms would strip real protection from any household still on the wrong module, or one where the panel is configured to signal out through every fitted module ("Dial All Numbers"), neither of which this project can detect today.
- **Option C (chosen): Keep every resilience mechanism unconditionally, but supersede ADR-002's claim** that the forced disconnect and protocol noise are universal panel behaviour, replacing it with a host-scoped account: expected primarily when Home Assistant shares a module with alarm reporting, present as a safety net otherwise.

## Decision

Chosen option: **Option C.**

This is the only option that keeps the client working correctly for households still on the wrong module or an unverified reporting configuration (driver 2) while no longer misrepresenting a correctly-configured household's measured behaviour as a defect (driver 1). It also gives implementers a concrete, current rule — the long reconnect budget is a safety net, not the expected path — without requiring proof that no install anywhere could ever need it (driver 3), and it leaves SPIKE-002's own record untouched (driver 5).

## Consequences

**Positive:** Documentation and product messaging can now correctly tell a household that a correctly-wired install should not lose Home Assistant during a real alarm, and can point them at the module-selection guidance instead of asking them to accept a permanent limitation. The resilience code continues to protect every install that has not yet been corrected.

**Negative:** The codebase still carries the full complexity of frame resync and an asymmetric reconnect budget for a case that, on at least one install, no longer occurs — that cost is accepted because it remains the only known protection for a still-common, project-undetectable misconfiguration.

**Follow-on:** Add a `Disposition:` field to SPIKE-002 — its forced-disconnect-at-trigger finding is no longer actionable as universal panel behaviour; this decision answers, for correctly-configured installs, the question SPIKE-002's finding otherwise left standing unqualified. Whether the command-path "zombie" detection recorded elsewhere was also a wrong-module artifact is left open for a separate spike, not decided here. The specific reconnect wait times and retry counts remain unset, as they were before this ADR — only the expected frequency of exercising that budget has changed.

**CI vs live:** A stand-in panel may keep simulating a forced disconnect at trigger, and CI must keep proving the resync-and-reconnect path still works correctly when that disconnect happens — that protection must not regress. CI must not claim that a correctly-configured dedicated-module install will experience a forced disconnect at trigger; that remains a live-only finding, established for one household by SPIKE-010 and not yet corroborated across other installs.

## Confirmation

This decision is correctly implemented when: (1) user-facing documentation and in-code comments describing the trigger-reconnect budget no longer state or imply that every real alarm disconnects Home Assistant from the panel, and instead frame it as expected when the panel shares its reporting module with Home Assistant; (2) the frame-resync and reconnect-on-drop mechanisms remain enabled and covered by existing tests unconditionally, with no code path that disables them based on which module is configured; and (3) SPIKE-002's own file is left unedited, carrying only a `Disposition:` note that its trigger-always-drops finding is superseded by this ADR for correctly-configured installs.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-21 | Clear | — |
