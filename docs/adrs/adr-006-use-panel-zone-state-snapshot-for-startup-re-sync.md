# ADR-006: Use Panel Zone-State Snapshot for Startup Re-Sync

**Status:** Accepted ✅  
**Date:** 2026-08-04  
**Spike:** [spike-006-startup-zone-state-read/SPIKE.md](../spikes/spike-006-startup-zone-state-read/SPIKE.md)

## Overview

**Background:** Live zone change events alone are not enough at app start — after a restart, Home Assistant zone entities can show the wrong open/closed value until something physically changes again. The zone-monitoring edge case requires a true re-sync to the panel’s current state.
**Decision:** After login (and again after a reconnect re-login), the app must ask the panel for a full current-state snapshot of every zone slot and publish that to MQTT for in-use zones before relying on entity state; live change events then keep those entities updated.
**Why this way:** Waiting only for the next physical change leaves entities wrong after every restart. Relying on retained MQTT alone goes stale when the panel changed while the app was down, and fails when the broker has nothing retained. A panel snapshot is what today’s working add-on does at startup, and it was confirmed live on this household’s panel.
**What this constrains:**
- Startup and post-reconnect flows must include a panel zone-state snapshot after login — not push-only and not MQTT-retain-only for correctness.
- Snapshot status encoding must stay aligned with live zone-change event encoding so open/closed meaning does not diverge.
- Test doubles used in CI must speak the same snapshot read so startup re-sync is verifiable without the live panel.
**Open follow-ons:**
- Physical open/close flip corroboration was skipped in the spike run (optional hardening, not a blocker).
- Whether a similar startup snapshot is required for area/alarm arm state is out of scope here (alarm-state drafts).

## Context

The zone-monitoring spec requires that on integration restart, zone entities re-sync to the panel’s current state rather than defaulting to an incorrect on/off value. Architecture and prior spikes had proven dynamic zone enumeration and unsolicited zone-change pushes, but left the startup snapshot path unconfirmed — open prior art never polls current zone state, while today’s closed-source add-on logs an explicit “updating all zone states” step after fetching zone metadata. SPIKE-006 probed the live panel and confirmed a dedicated read returns one status byte per zone after login.

## Decision drivers

- Restart must leave in-use zone entities reflecting the panel’s actual current open/closed state, not a default or stale guess.
- The mechanism must be a confirmed, safe panel read (no arm/disarm/omit side effects) with empirically observed request/response behaviour on this panel.
- Live change events and the startup snapshot must share one status encoding so implementers do not invent a second mapping.
- CI must be able to exercise the startup path via FakePanel (or equivalent), not only against the live household panel.

## Options considered

- **Panel zone-state snapshot after login (and on reconnect)** — poll current status for all zone slots, publish MQTT for in-use zones, then subscribe to live change events. Chosen.
- **Push-only (no startup poll)** — subscribe to live change events and wait for the next physical change. Rejected because: fails the restart re-sync driver; entities stay wrong until something moves.
- **Retain last MQTT state across restarts only** — rely on retained broker payloads without reading the panel. Rejected because: goes stale when the panel changed while the app was down; fails empty-broker / first-start cases; does not satisfy “re-sync to the panel.”

## Decision

Chosen option: **Panel zone-state snapshot after login (and on reconnect)**

SPIKE-006 Validated that after LOGIN the panel accepts `GetZoneState` (command byte `2`) with body `[startZone][zoneCount]` (1-byte `startZone` when panel zone count ≤ 256; one household's Elite 88 used `01 58` for start 1 / count 88) and returns exactly `zoneCount` status bytes. Low two bits decode as Secure / Active / Tamper / Short — the same map already used for unsolicited ZONE events. Production must call this snapshot after login (and after reconnect re-login), publish MQTT state for in-use zones, then use `SETEVENTMESSAGES` pushes for ongoing updates. Batches of up to 168 zones per request match observed add-on behaviour; an 88-zone Premier Elite's zones fit in one request.

## Consequences

**Positive:** Restart and reconnect can publish correct zone entity state immediately; FakePanel can implement the same command for CI; protocol reference can record a previously missing read.

**Negative:** Client, FakePanel, and tests must implement one more command family; startup takes an extra round-trip (acceptable vs wrong entity state).

**Follow-on:** Record `GetZoneState` framing in the living protocol reference when implementing. Alarm/area startup snapshot (if needed) remains a separate decision for alarm-state work. Optional physical flip corroboration may still be run later for extra confidence.

## Confirmation

Startup (and reconnect) path unit/E2E tests against FakePanel assert: after login, a `GetZoneState` exchange yields status bytes for the configured zone count, in-use zones receive MQTT state matching those bytes (Secure→off / Active→on using the shared bitmap), and no arm/disarm/omit commands are sent during the snapshot.
