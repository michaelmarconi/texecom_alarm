# ADR-008: Use confirmed shared arm/disarm commands with Away as full arm and configurable Home/Night Part-Arm mapping for panel control

**Status:** Accepted ✅  
**Date:** 2026-08-08  
**Spike:** [spike-005-arm-disarm-command-framing/SPIKE.md](../spikes/spike-005-arm-disarm-command-framing/SPIKE.md)  
**Supersedes:** ADR-005

## Overview

**Background:** The app already has confirmed shared arm and disarm commands, but treating Away as if it could occupy a Part-Arm config slot sent the wrong panel mode and left Home Assistant showing disarmed after a real part-arm settle.
**Decision:** Keep the confirmed shared arm and disarm commands. Away always uses the panel’s full-arm mode. Only Home and Night map to engineer Part-Arm slots via install-time configuration; each Part-Arm option is Home, Night, or Unused — never Away.
**Why this way:** Live evidence confirmed the shared commands and that Part-Arm roles differ per installation. A later live failure showed Away-on-a-Part-Arm-slot is not a valid product mapping — full Away and Part-Arm are different panel behaviours, and slot-3 settle was not mapped to an armed HA state.
**What this constrains:**
- The app must issue arm and disarm using the confirmed shared command mechanism, including Home — not invent per-mode command families.
- Away must always map to full arm, never to a Part-Arm slot number.
- Home and Night must map to Part-Arm slots through documented install-time configuration — never hardcoded to one household’s engineer layout.
- Part-Arm configuration choices are Home, Night, or Unused only; Away must not appear as a Part-Arm option.
- The app must not assume the panel auto-reports Part-Arm Night/Home roles via the area-details query already tested.
- Disarm remains mode-independent: one confirmed disarm covers armed states and cancelling an in-progress exit for every arm mode.
**Open follow-ons:**
- Exact shape of the add-on configuration surface for Home/Night→slot mapping (e.g. three fields vs a single ordered list) remains a later design choice; this ADR only requires that mapping be configurable and that Away is excluded from it.
- Whether some other, still-unexercised panel command can auto-detect Part-Arm roles remains open; the area-details query specifically does not.

## Context

SPIKE-005 confirmed a shared set-arm-mode command (`cmd=6`, mode byte in the body) and a mode-independent disarm (`cmd=8, body=01`), with Away/Night captured from a live client and Home corroborated by a direct test. ADR-005 recorded those commands and required install-time mapping of HA Home/Night (and Away) labels onto Part-Arm slots. After cutover testing, assigning Away to a Part-Arm slot caused the app to send that slot’s mode byte instead of full arm; the panel part-armed, then a settled AREA state for that slot fell through to MQTT `disarmed`. The corrected alarm-control requirement is that Away is always full arm and Part-Arm options are Home/Night/Unused only. This ADR replaces ADR-005 so living constraints match that requirement while retaining the confirmed command set.

## Decision drivers

- Must keep empirically confirmed shared arm and disarm commands for Away, Night, Home, and Disarm — not reopen send-path research.
- Must not hardcode this household’s Part-Arm slot layout for Home/Night, given public Add-on distribution to other Premier Elite installations.
- Must not treat Away as a Part-Arm slot assignment — Away is full arm on the panel.
- Must keep panel-universal protocol facts (shared arm command, mode-independent disarm, Away = full-arm mode byte) distinct from installation-specific facts (which Part-Arm slot is Home vs Night).
- Must not leave Home blocked on further capture work.

## Options considered

- **Confirmed shared commands; Away always full arm; Home/Night→Part-Arm slots configurable (Unused allowed)** — retain SPIKE-005 commands; Away uses the full-arm mode byte; only Home and Night are install-mapped to Part-Arm slots; Part-Arm radios exclude Away. Chosen.
- **Keep ADR-005 mapping (Away may occupy a Part-Arm slot via config)** — continue allowing Away as a Part-Arm option alongside Home/Night. Rejected because: it violates the “Away is full arm, not a Part-Arm assignment” driver and reproduced a live false `disarmed` after part-arm settle.
- **Hardcode this household’s Home/Night slot numbers (and Away full arm) as fixed constants** — ship without a Part-Arm config surface. Rejected because: it violates the “must not hardcode Part-Arm layout” driver for other Premier Elite installations.

## Decision

Chosen option: **Confirmed shared commands; Away always full arm; Home/Night→Part-Arm slots configurable (Unused allowed)**

SPIKE-005’s command mechanism stands: `cmd=6` with a mode byte and `cmd=8, body=01` for disarm. Away’s mode byte is the panel full-arm value (`00` on the investigated household), not a Part-Arm slot index. Home and Night mode bytes are the Part-Arm slot numbers chosen at install time. Configuration must not offer Away as a Part-Arm choice. Auto-detection of slot roles via `GETAREADETAILS` remains unavailable.

## Consequences

**Positive:** Arm/disarm stay unblocked with confirmed wire commands. Away cannot be mis-wired to a Part-Arm slot through config. Home/Night remain portable across installations. Disarm and exit-cancel stay one command.

**Negative:** The add-on must still expose and document a Home/Night→slot configuration surface (Away excluded). Mis-mapping Home/Night still yields wrong HA labels though the wire command succeeds. Auto-detection of slot roles is still unavailable via the area-details command already tested.

**Follow-on:** Design the concrete add-on option shape for Home/Night→slot mapping during architecture/plan — Away must not be an option on that surface. Do not assume `GETAREADETAILS` can supply the mapping.

**CI vs live (when this decision is about an outside system / protocol):** FakePanel and unit/E2E tests may claim correct mode-byte selection (Away → full-arm byte; Home/Night → configured slots; Away absent from Part-Arm options). Live-panel accept-walk remains the knowing path that full Away, Night, and Home each produce the expected panel acknowledgement and AREA sequence on real hardware.

## Confirmation

Against FakePanel (CI): Away resolves to the full-arm mode byte; Home and Night resolve only through configured Part-Arm slots; a Part-Arm option set that includes Away is rejected or impossible in schema. Against a live panel with the prior client stopped: arm Away, arm Night, arm Home, and disarm each produce the expected acknowledgement and AREA-state sequence; changing only the Home/Night slot mapping changes which HA mode corresponds to which Part-Arm slot without a code change.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-08 | Clear | — |
