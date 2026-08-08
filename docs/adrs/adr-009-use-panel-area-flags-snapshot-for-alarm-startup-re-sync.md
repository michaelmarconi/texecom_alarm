# ADR-009: Use panel area-flags snapshot for alarm startup re-sync

**Status:** Accepted ✅  
**Date:** 2026-08-08  
**Spike:** [spike-007-area-arm-state-startup-read/SPIKE.md](../spikes/spike-007-area-arm-state-startup-read/SPIKE.md)  
**Supersedes:** ADR-007

## Overview

**Background:** After a restart, live area events alone leave the Home Assistant alarm entity wrong until the next panel change. The app must re-sync arm state from the panel itself.
**Decision:** After login (and again after a reconnect re-login), the app must ask the panel for a current area-flags snapshot, derive each in-use area’s armed/disarmed/part-armed/in-alarm status from that snapshot, and publish that to MQTT before relying on alarm entity state; live area/log change events then keep the entity updated.
**Why this way:** Waiting only for the next push leaves the alarm entity wrong after every restart. Retained MQTT goes stale when the panel changed while the app was down. A panel area-flags snapshot was confirmed live and matches the class of answer already required for zones.
**What this constrains:**
- Startup and post-reconnect flows must include a panel area/arm-state snapshot after login — not push-only and not MQTT-retain-only for correctness of the alarm entity.
- Snapshot status meaning must stay aligned with how live area events are interpreted so armed/disarmed/part-armed/in-alarm does not diverge between startup and steady state.
- Test doubles used in CI must speak the same area-flags read so alarm startup re-sync is verifiable without the live panel.
- When the snapshot reports a Part-Arm slot, Home/Night labels come from install-time configuration (ADR-008); Away is full arm, not a Part-Arm label. The snapshot reports which slot is active, not which HA mode name that slot carries.
**Open follow-ons:**
- Optional arm-then-re-poll corroboration was skipped in the spike run (optional hardening, not a blocker).
- How exit/entry transient states appear in the flag block versus only on live area pushes was not observed in the Disarmed-only run — live pushes may still be required for arming/pending MQTT states even when the snapshot covers settled Disarmed/Armed/PartArmed/InAlarm.
- Wider area-bitmap layouts (the dual-request path used on some larger panels) were not exercised on this Elite 88.

## Context

ADR-007 required a post-login area-flags snapshot for alarm re-sync and correctly kept Part-Arm → HA naming as install-time configuration. Its constraints still listed Away among labels that Part-Arm slots could carry. ADR-008 clarified that Away is always full arm and only Home/Night map to Part-Arm slots. This ADR restates the unchanged snapshot decision with mapping language aligned to ADR-008 so living agent context does not contradict itself.

## Decision drivers

- Restart must leave the alarm entity reflecting the panel’s actual current armed/disarmed/part-armed/in-alarm state, not a default or stale guess.
- The mechanism must be a confirmed, safe panel read (no arm/disarm/omit side effects on the default path) with empirically observed request/response behaviour on this panel.
- Live area/log change events and the startup snapshot must share one status meaning so implementers do not invent a second mapping for the same panel facts.
- CI must be able to exercise the alarm startup path via FakePanel (or equivalent), not only against the live household panel.
- Part-Arm → HA Home/Night naming must remain install-time configuration (ADR-008); Away is not a Part-Arm label; the snapshot must not be treated as auto-detecting Night/Home role names.

## Options considered

- **Panel area-flags snapshot after login (and on reconnect), with Home/Night-only Part-Arm label mapping** — same snapshot mechanism as ADR-007; Part-Arm slot → HA labels follow ADR-008 (Home/Night only; Away is full arm). Chosen.
- **Push-only (no startup poll)** — subscribe to live area events and wait for the next arm/disarm/trigger push. Rejected because: fails the restart re-sync driver; the alarm entity stays wrong until something changes at the panel.
- **Retain last MQTT alarm state across restarts only** — rely on retained broker payloads without reading the panel. Rejected because: goes stale when the panel changed while the app was down; fails empty-broker / first-start cases; does not satisfy “re-sync to the panel.”

## Decision

Chosen option: **Panel area-flags snapshot after login (and on reconnect), with Home/Night-only Part-Arm label mapping**

SPIKE-007 Validated that after LOGIN the panel accepts `GetAreaFlags` (command byte `11`) with body `[start][count]` (this Elite 88 used `00 48` for start 0 / count 72 with `area_size=1` derived from zone count 88) and returns exactly `count * area_size` flag bytes. Per-area bits decode with priority Alarm(0) → InAlarm; else Armed(21)/FullArmed(22)/PartArmed(23)/ForceArmed(26) → Armed or PartArmed (+ PartArm1/2/3 slot bits); else Disarmed — the same decode today’s add-on uses after its “Updating all area states…” step. Production must call this snapshot after login (and after reconnect re-login), publish MQTT alarm state for in-use areas, then use `SETEVENTMESSAGES` pushes for ongoing updates. Part-Arm slot numbers from the snapshot map to HA Home/Night only through install-time configuration (ADR-008); full Away is not represented as a Part-Arm slot label.

## Consequences

**Positive:** Restart and reconnect can publish correct alarm entity state immediately; FakePanel can implement the same command for CI; mapping language stays consistent with ADR-008.

**Negative:** Client, FakePanel, and tests must implement the area-flags command family and flag decode; startup takes an extra round-trip (acceptable vs wrong alarm state); exit/entry transients may still depend on live pushes until corroborated in the flag block.

**Follow-on:** Optional arm-mode corroboration and `area_size === 8` dual-request panels may still be probed later for extra confidence. Mapping Part-Arm slots to HA Home/Night labels remains ADR-008 configuration — do not treat this snapshot as auto-detecting Night/Home names or as assigning Away to a slot.

**CI vs live (when this decision is about an outside system / protocol):** FakePanel tests may claim the GetAreaFlags exchange, flag decode, and MQTT publish for Disarmed/Armed/PartArmed/InAlarm (including Home/Night from configured slots when PartArmed). Live-only: real-panel corroboration of flag bits under armed/part-armed/in-alarm, and exit/entry transient behaviour if not present in the flag block.

## Confirmation

Startup (and reconnect) path unit/E2E tests against FakePanel assert: after login, a `GetAreaFlags` exchange yields flag bytes for the configured area bitmap width, the in-use area’s MQTT alarm state matches the decoded Disarmed/Armed/PartArmed/InAlarm status (including Home/Night from install mapping when PartArmed — never treating Away as a Part-Arm slot label), and no arm/disarm/omit commands are sent during the default snapshot path.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-08 | Clear | — |
