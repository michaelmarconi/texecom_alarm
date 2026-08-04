# ADR-005: Use confirmed shared arm/disarm commands with configurable Part-Arm mapping for panel control

**Status:** Accepted ✅
**Date:** 2026-08-04
**Spike:** [spike-005-arm-disarm-command-framing/SPIKE.md](../spikes/spike-005-arm-disarm-command-framing/SPIKE.md)

## Overview

**Background:** The project could not yet actively arm or disarm the panel over the network — earlier work had decoded how the panel reports arm state, but not the exact commands a client must send. Without those commands, Home mode and the rest of alarm control could not be built.
**Decision:** Use the empirically confirmed shared arm and disarm commands for production, and treat which arm mode maps to which underlying Part-Arm slot as a per-installation configuration value rather than a hardcoded constant.
**Why this way:** A live investigation confirmed all four actions (Away, Night, Home, Disarm) with reproducible evidence, and separately established that Part-Arm slot roles are engineer-configured per panel — hardcoding this household's layout would silently fail on other Premier Elite installations the app is now intended to serve.
**What this constrains:**
- The app must issue arm and disarm using the confirmed shared command mechanism, not invent per-mode command families or leave Home unimplemented pending further capture work.
- The mapping from Home Assistant's Home/Night (and Away) labels to the panel's physical Part-Arm slots must be a documented, install-time configuration value — never baked to this household's own engineer layout.
- The app must not assume the panel can auto-report each Part-Arm slot's Night/Home role at startup via the area-details query already tested — that path was ruled out; mapping remains manual configuration unless a future decision finds another source.
- Disarm is mode-independent: one confirmed disarm command covers fully armed states and cancelling an in-progress exit for every arm mode.
**Open follow-ons:**
- Exact shape of the add-on configuration surface for the mode-to-slot mapping (e.g. three fields vs a single ordered list) is left to a later design choice; this ADR only requires that the mapping be configurable.
- Whether some other, still-unexercised panel command can auto-detect Part-Arm roles remains open; `GETAREADETAILS` specifically does not.

## Context

SPIKE-002 had decoded the panel's observation-side arm/trigger events and the collision/reconnect behaviour that crashes naive clients, but left the send-side commands unknown — RISK-001's remaining gap, and a hard blocker for `spec-alarm-control.md`'s arm/disarm acceptance criteria. SPIKE-005 closed that gap: Away and Night were confirmed by passively capturing a live local client's real traffic (reproduced multiple times); Home was confirmed by testing the one remaining value of that already-proven command structure against the live panel, corroborated by a clean acknowledgement, an event sequence matching SPIKE-002's independent prior Home-arm observation, and direct household confirmation via the vendor app. The same investigation found that Part-Arm slot assignment (which physical slot is Night vs Home) is engineer-configured per installation, not a protocol constant — already reflected as a constraint in `spec-alarm-control.md` after a follow-on `/correction`. A subsequent live probe of `GETAREADETAILS` (`cmd=35`) showed it returns area identity only (`HOUSE` / unused areas), not Part-Arm slot roles, so auto-detection via that command is not available.

## Decision drivers

- Must unblock Phase 2 arm/disarm build with concrete, empirically confirmed commands for Away, Night, Home, and Disarm — not a research writeup alone.
- Must not hardcode this household's Part-Arm slot layout, given the project's goal of public Add-on distribution to other Premier Elite installations.
- Must not leave Home blocked on an external capture dependency (phone/app Local Connection) when stronger corroborating evidence already exists.
- Must keep panel-universal protocol facts (shared arm command, mode-independent disarm) distinct from installation-specific facts (which mode byte means which HA arm mode).

## Options considered

- **Adopt confirmed shared arm/disarm commands with configurable mode-to-slot mapping** — issue the confirmed shared arm command with a configurable mode parameter (defaulting to this household's Away/Night/Home layout but overridable) and the confirmed mode-independent disarm command. Chosen.
- **Hardcode this household's specific mode-byte values** — ship Away/Night/Home as fixed constants matching only this panel's engineer layout. Rejected because: it directly violates the "must not hardcode this household's Part-Arm layout" driver and the public-distribution goal; silent wrongness on other installations recreates the same class of drift risk ADR-001 already rejected for zone inventories.
- **Treat Home as still unconfirmed pending another passive-capture route** — leave Home's mode value open until the official app or another Home-capable client can be captured. Rejected because: it fails the "must unblock Phase 2 with confirmed commands for all four actions" driver, and the direct Home test already produced stronger multi-signal evidence than waiting on an external dependency with no target date.

## Decision

Chosen option: **Adopt confirmed shared arm/disarm commands with configurable mode-to-slot mapping**

SPIKE-005 confirmed `cmd=6` as the shared set-arm-mode command (body mode byte `00`/`01`/`02` for Away/Night/Home on this household's panel) and `cmd=8, body=01` as mode-independent disarm, including cancel-during-exit. The command mechanism is panel-universal; the mode-byte-to-HA-mode mapping is not, and must be sourced from per-installation configuration. Leaving Home open or hardcoding this house's layout each fails a listed decision driver; Option A satisfies all four.

## Consequences

**Positive:** Phase 2 can implement full arm Away/Night/Home and Disarm without further protocol reverse-engineering of the send path. The app stays honest about which facts generalise across Premier Elite installations. Disarm and exit-cancel share one confirmed command, simplifying the client.

**Negative:** The add-on must expose and document a configuration surface for the mode-to-slot mapping before other households can install correctly — a small piece of product/UX work not yet designed. Installers who mis-map slots will get wrong HA arm modes even though the wire commands succeed. Auto-detection of slot roles is not available via the area-details command already tested.

**Follow-on:** Design the concrete add-on option shape for the mapping (fields vs ordered list) during architecture/plan — this ADR only requires configurability. Do not assume `GETAREADETAILS` can supply the mapping. Architecture Open questions that still describe send-side arm/disarm as unknown should be reconciled when `/architecture` next runs in Update mode.

## Confirmation

Against a live panel with `the prior MQTT bridge` stopped, the app (or an equivalent client using the same commands) can arm Away, arm Night, arm Home, and disarm, each producing the expected panel acknowledgement and AREA-state sequence recorded in SPIKE-005 / `docs/protocol-reference.md`, and changing the configured mode-byte mapping changes which HA arm mode corresponds to which Part-Arm slot without a code change.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-04 | Clear | — |
