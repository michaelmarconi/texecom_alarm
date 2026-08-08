# ADR-007: Use Panel Area-Flags Snapshot for Alarm Startup Re-Sync

**Status:** ~~Accepted~~ Superseded by [ADR-009](adr-009-use-panel-area-flags-snapshot-for-alarm-startup-re-sync.md)  
**Date:** 2026-08-04  
**Spike:** [spike-007-area-arm-state-startup-read/SPIKE.md](../spikes/spike-007-area-arm-state-startup-read/SPIKE.md)

## Overview

**Background:** Live area change events alone are not enough at app start — after a restart, the Home Assistant alarm entity can show the wrong armed/disarmed/triggered value until the next panel event. The alarm-control restart edge case requires a true re-sync to the panel’s current arm state.
**Decision:** After login (and again after a reconnect re-login), the app must ask the panel for a current area-flags snapshot, derive each in-use area’s armed/disarmed/part-armed/in-alarm status from that snapshot, and publish that to MQTT before relying on alarm entity state; live area/log change events then keep the entity updated.
**Why this way:** Waiting only for the next push leaves the alarm entity wrong after every restart. Relying on retained MQTT alone goes stale when the panel changed while the app was down, and fails when the broker has nothing retained. A panel area-flags snapshot is what today’s working add-on does at startup, and it was confirmed live on this household’s panel — the same class of answer already required for zones.
**What this constrains:**
- Startup and post-reconnect flows must include a panel area/arm-state snapshot after login — not push-only and not MQTT-retain-only for correctness of the alarm entity.
- Snapshot status meaning must stay aligned with how live area events are interpreted so armed/disarmed/part-armed/in-alarm does not diverge between startup and steady state.
- Test doubles used in CI must speak the same area-flags read so alarm startup re-sync is verifiable without the live panel.
- Part-Arm slot → Home/Night/Away labels remain install-time configuration; the snapshot reports which part-arm slot is active, not which HA mode name that slot carries.
**Open follow-ons:**
- Optional arm-then-re-poll corroboration was skipped in the spike run (optional hardening, not a blocker).
- How exit/entry transient states appear in the flag block versus only on live area pushes was not observed in the Disarmed-only run — live pushes may still be required for arming/pending MQTT states even when the snapshot covers settled Disarmed/Armed/PartArmed/InAlarm.
- Wider area-bitmap layouts (the dual-request path used on some larger panels) were not exercised on this Elite 88.

## Context

The alarm-control spec requires that on integration restart, the alarm entity re-syncs to the panel’s actual current state rather than defaulting to disarmed or another incorrect value. ADR-006 settled the same class of problem for zone open/closed, and explicitly left area/alarm arm-state startup snapshot as a separate decision. Architecture parked that question for alarm-state drafts. SPIKE-007 probed the live panel and confirmed a dedicated area-flags read returns a fixed-length flag block after login that decodes to a coherent Disarmed status for the household’s in-use area, matching the “updating all area states” step today’s closed-source add-on performs at startup.

## Decision drivers

- Restart must leave the alarm entity reflecting the panel’s actual current armed/disarmed/part-armed/in-alarm state, not a default or stale guess.
- The mechanism must be a confirmed, safe panel read (no arm/disarm/omit side effects on the default path) with empirically observed request/response behaviour on this panel.
- Live area/log change events and the startup snapshot must share one status meaning so implementers do not invent a second mapping for the same panel facts.
- CI must be able to exercise the alarm startup path via FakePanel (or equivalent), not only against the live household panel.
- Part-Arm → HA mode naming must remain install-time configuration (ADR-005); the snapshot must not be treated as auto-detecting Night/Home role names.

## Options considered

- **Panel area-flags snapshot after login (and on reconnect)** — poll current area flags, derive alarm MQTT state for in-use areas, then subscribe to live area/log change events. Chosen.
- **Push-only (no startup poll)** — subscribe to live area events and wait for the next arm/disarm/trigger push. Rejected because: fails the restart re-sync driver; the alarm entity stays wrong until something changes at the panel.
- **Retain last MQTT alarm state across restarts only** — rely on retained broker payloads without reading the panel. Rejected because: goes stale when the panel changed while the app was down; fails empty-broker / first-start cases; does not satisfy “re-sync to the panel.”

## Decision

Chosen option: **Panel area-flags snapshot after login (and on reconnect)**

SPIKE-007 Validated that after LOGIN the panel accepts `GetAreaFlags` (command byte `11`) with body `[start][count]` (this Elite 88 used `00 48` for start 0 / count 72 with `area_size=1` derived from zone count 88) and returns exactly `count * area_size` flag bytes. Per-area bits decode with priority Alarm(0) → InAlarm; else Armed(21)/FullArmed(22)/PartArmed(23)/ForceArmed(26) → Armed or PartArmed (+ PartArm1/2/3 slot bits); else Disarmed — the same decode today’s add-on uses after its “Updating all area states…” step. Production must call this snapshot after login (and after reconnect re-login), publish MQTT alarm state for in-use areas, then use `SETEVENTMESSAGES` pushes for ongoing updates. Part-Arm slot numbers from the snapshot map to HA Home/Night/Away only through install-time configuration (ADR-005).

## Consequences

**Positive:** Restart and reconnect can publish correct alarm entity state immediately; FakePanel can implement the same command for CI; protocol reference can record a previously missing read; ADR-006’s parked area/alarm follow-on is closed for the settled-state path.

**Negative:** Client, FakePanel, and tests must implement one more command family and flag decode; startup takes an extra round-trip (acceptable vs wrong alarm state); exit/entry transients may still depend on live pushes until corroborated in the flag block.

**Follow-on:** Record `GetAreaFlags` framing, `area_size` derivation, and flag decode in the living protocol reference when implementing. Optional arm-mode corroboration and `area_size === 8` dual-request panels may still be probed later for extra confidence. Mapping PartArm slots to HA mode labels remains ADR-005 configuration — do not treat this snapshot as auto-detecting Night/Home names.

## Confirmation

Startup (and reconnect) path unit/E2E tests against FakePanel assert: after login, a `GetAreaFlags` exchange yields flag bytes for the configured area bitmap width, the in-use area’s MQTT alarm state matches the decoded Disarmed/Armed/PartArmed/InAlarm status (including part-arm slot when PartArmed), and no arm/disarm/omit commands are sent during the default snapshot path.
