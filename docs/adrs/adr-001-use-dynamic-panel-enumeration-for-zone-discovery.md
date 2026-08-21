# ADR-001: Use dynamic panel enumeration for zone discovery

**Status:** Accepted ✅
**Date:** 2026-08-01
**Spike:** [spike-001-zone-enumeration/SPIKE.md](../spikes/spike-001-zone-enumeration/SPIKE.md)

## Overview

**Background:** It was unknown whether the alarm panel could report its own zone list, or whether every zone (door, window, PIR, etc.) would have to be typed into configuration by hand and kept in sync manually as the household's wiring changed.
**Decision:** The integration asks the panel for its own zone list — count, type, and name — every time it starts up, instead of reading a zone list that a person maintains in configuration.
**Why this way:** A live test against the real panel proved the panel can report this itself, cleanly and with no errors, so there is no need to accept the ongoing maintenance burden and risk of a hand-typed list quietly drifting out of date.
**What this constrains:**
- The integration must be able to reach the panel and log in before it can build any zone entities — it cannot start with a hardcoded zone list as a substitute.
- The integration must treat "unused" zone slots (as reported by the panel) as not warranting a Home Assistant entity, rather than assuming every physical zone slot is in use.
- Because the panel's network module only accepts one connection at a time, whatever currently holds that connection must be fully stopped before this integration can connect to enumerate zones — this shapes how the old and new integrations are switched over.
- The panel's zone count and names are treated as the current source of truth going forward, superseding the older hand-written estimate used earlier in the project's documentation.
**Open follow-ons:**
- Whether to add a fallback to a last-known-good cached zone list if the panel can't be reached at startup (Option C) is left open for a future decision — it was not what was tested here.
- Whether the panel's one-connection-at-a-time behaviour is a fixed limit or a configurable setting was not established, and may affect how cutover/testing is sequenced.

## Context

The project's zone-monitoring build depended on knowing, for every physical zone on the panel, its number, type, and name. `docs/analysis.md` (RISK-003) flagged this as an open technology unknown: if the Texecom Connect protocol could not enumerate zones programmatically, all zones would need to be hand-specified and hand-maintained in configuration — a materially larger, more error-prone build, with a real risk of a zone silently going unmonitored if the hand-written list drifted from the panel's actual configuration. SPIKE-001 was run to resolve this before the zone-monitoring build proceeded.

## Decision drivers

- Must avoid a hand-maintained zone inventory that can silently drift from the panel's actual configuration (RISK-003 severity rationale).
- Must be empirically validated against the actual live panel, not just prior-art documentation or vendor claims.
- Must correctly distinguish in-use zones from unused hardware zone slots, to avoid creating dead Home Assistant entities.
- Must not depend on assumptions that were not exercised by the spike's experiment.

## Options considered

- **Dynamic enumeration via `GETPANELIDENTIFICATION` + `GETZONEDETAILS`** — query the panel for its zone count and per-zone type/name at startup, and build entities from that response.
- **Hand-maintained static zone list** — hardcode zone number, type, and name in configuration, matching the pattern used by other (serial/Crestron-transport) prior-art projects. Rejected because it directly reintroduces the silent-drift risk the decision drivers require avoiding, and the spike's experiment demonstrated the panel doesn't require this trade-off.
- **Hybrid — dynamic enumeration with a static fallback** — attempt dynamic enumeration at startup, falling back to a cached last-known-good zone list if the panel connection can't be established. Rejected for now because the fallback path itself was not exercised by the spike's experiment, so it is not yet empirically validated; it remains an open follow-on rather than part of this decision.

## Decision

Chosen option: **Dynamic enumeration via `GETPANELIDENTIFICATION` + `GETZONEDETAILS`**

The spike's live probe against the actual panel enumerated all 88 zone slots (count, type, and name) with zero framing errors, zero retries, and zero timeouts, and correctly distinguished the 40 in-use slots from the 48 unused ones. This directly satisfies the requirement to avoid a hand-maintained inventory and is backed by empirical evidence against the real panel, rather than an untested assumption, which the hybrid option could not yet claim.

## Consequences

**Positive:** The integration's zone list automatically tracks zone renames/re-programming done at the panel keypad, with no separate configuration-file update required; unused zone slots are correctly excluded from Home Assistant entities, avoiding dead entities; the approach is validated end-to-end against the household's real panel and firmware, not just prior-art claims.

**Negative:** The integration now has a hard startup dependency on the panel being reachable and logged in before any zone entities can be created — there is no offline/static fallback yet. Because the panel's ComIP module accepts only one TCP client at a time, whatever integration currently holds that connection must be fully stopped (not merely idle) before this integration can connect and enumerate.

**Follow-on:** Whether to harden this into the hybrid fallback (Option C) for graceful degradation when the panel can't be reached is an open implementation decision, not required to resolve this ADR. The cutover plan between the old and new integrations must account for the single-connection constraint. The project's documentation should be corrected to reflect the panel's actual in-use zone count (40, out of 88 addressable slots) rather than the earlier "~35-zone" estimate, and to reflect that the panel is protected by a UDL password (often the common factory default on unaltered installs) rather than having no password — both are separate documentation corrections outside the scope of this ADR.

## Confirmation

The zone-monitoring build creates Home Assistant entities that match the panel's live-reported zone list (40 in-use zones, matching the names/types recorded in SPIKE-001's Results) with no zone list present in the integration's configuration, and creates no entity for any zone slot the panel reports as unused.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-01 | Clear | — |
