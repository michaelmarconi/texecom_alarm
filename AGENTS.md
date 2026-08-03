# Agent Instructions

<!-- Synthesised by /constitute on 2026-08-03 from: ADR-001, ADR-002, ADR-003, ADR-004 -->
<!-- Re-run /constitute after any new ADR is accepted. -->

## Project

Texecom Alarm — HA Integration Replacement: a ground-up, self-built Home Assistant integration for a Texecom Premier Elite alarm panel (via ComIP/Texecom Connect), replacing the closed-source, unreliable `the prior MQTT bridge` add-on with something that doesn't crash and finally supports Home arm mode.

## Integration branch

`main` — tasks merge here; `/build` reads this and never assumes `main`.

## Architectural decisions

### ADR-001: Use dynamic panel enumeration for zone discovery

**Decision:** The integration asks the panel for its own zone list — count, type, and name — every time it starts up, instead of reading a zone list that a person maintains in configuration.

**Constraints:**
- The integration must reach the panel and log in before it can build any zone entities — it cannot start with a hardcoded zone list as a substitute.
- Zone slots the panel reports as unused must not get Home Assistant entities.
- The panel's network module accepts only one connection at a time, so whatever currently holds that connection must be fully stopped before this integration can connect to enumerate zones.
- The panel's live zone count and names are the source of truth, superseding earlier hand-written estimates in project docs.
- There is no offline/static fallback yet — graceful degradation via a last-known-good cached zone list remains an open follow-on, not part of this decision.

### ADR-002: Use frame resync and asymmetric reconnect for panel protocol collisions

**Decision:** The client skips over unexpected, non-conforming data on the panel connection instead of crashing, and waits longer and retries more patiently to reconnect after a real alarm trigger than after an ordinary arm or disarm.

**Constraints:**
- The wire-protocol client must never treat an unrecognised or corrupted chunk of data as a fatal error — it must skip past it and keep listening for valid panel messages.
- Reconnection after a dropped connection must not use one fixed timeout/attempt budget for every situation — it must wait substantially longer and retry more after a real alarm trigger than after an ordinary arm/disarm.
- The integration should show a "reconnecting" or degraded-connectivity status to the user during recovery rather than failing silently or crashing.
- The panel's reporting/Com-Port configuration should still be checked and recorded as a one-time, secondary mitigation, but the client's correctness cannot depend on that configuration being available or unchanged.
- The reconnect budget is not yet backed by enough real-world data to guarantee it is always sufficient — only one real trigger event was observed.

### ADR-003: Use MQTT discovery (not a native integration) for entity surfacing

**Decision:** Build this as an app that publishes entities to Home Assistant purely over MQTT discovery, not as a natively-registered integration.

**Constraints:**
- The app must not embed any household-specific arming/notification rules — that logic has to keep living entirely in the household's own Home Assistant configuration, not in this app.
- The app needs its own connection to an MQTT broker as a standing runtime dependency, the same as today's add-on.
- Entities this app produces will look and behave like any other MQTT-discovered device in Home Assistant, not like a first-class, natively-registered integration with its own configuration UI — no entity-registry, config-flow, or HACS-style packaging/distribution overhead is available.
- Discovery payloads must be hand-kept in sync with whatever states/features HA's MQTT `alarm_control_panel`/`binary_sensor` platforms support.

### ADR-004: Use App-Liveness Unavailability and Trigger Snapshots for Panel-Link Outages

**Decision:** The integration marks its alarm and zone entities unavailable only when the app itself stops running — never because the panel connection drops — and separately signals degraded panel-link health plus a persisted snapshot of the events leading up to a trigger.

**Constraints:**
- The app's alarm and zone entities must never be marked unavailable because the panel connection dropped — only the app process itself being down can do that.
- The app must publish a separate, dedicated signal for panel-link health, distinct from the entities' own state, so the household and its automations can tell live data from stale data.
- The app must keep a short rolling memory of recent zone/panel activity so it can produce a "what happened right before this trigger" snapshot that survives a subsequent outage.
- Anything consuming the alarm/zone entity state (dashboards, automations) can be shown a stale value for as long as an outage lasts, with currency only communicated via the separate connectivity signal — this should be documented/exposed prominently rather than assumed to be obvious.

## Stop conditions

- **[ADR-001]** Before implementing a hybrid or cached last-known-good zone list for when the panel can't be reached at startup: stop and ask a human — that path was left open and not validated by this ADR.
- **[ADR-001]** Before planning cutover or testing that assumes the panel can accept more than one simultaneous TCP connection, or that the single-connection behaviour is a configurable setting: stop and ask a human — that was not established by this ADR.
- **[ADR-001]** Before hardcoding or hand-maintaining a zone inventory in configuration as a substitute for panel enumeration: stop and ask a human — that would violate this decision.
- **[ADR-002]** Before hardcoding the reconnect wait times/retry counts as final, unchangeable values: stop and ask a human — only one real trigger data point exists, and this ADR left the schedule tunable, not finalised.
- **[ADR-002]** Before implementing or relying on "alarm reset" as a signal the integration can act on: stop and ask a human — what that should mean is a separate, still-open decision not resolved by this ADR.
- **[ADR-003]** Before building or maintaining a natively-registered `custom_components` Home Assistant integration, or moving household-specific arming/notification logic into this app: stop and ask a human — both would violate this decision.
- **[ADR-004]** Before marking the `alarm_control_panel` or any zone `binary_sensor` entity "unavailable" due to a panel-link/reconnect problem: stop and ask a human — availability must be governed solely by whether the app process itself is running (via MQTT Last-Will), never by panel connection health.
- **[ADR-004]** Before adding a fixed-timeout auto-escalation to "unavailable" for stale panel-link data: stop and ask a human — this ADR explicitly rejected that approach as reintroducing the same problem on a delay; the exact staleness bound (if any) is left open, not decided.
- **[ADR-004]** Before assuming Com Port isolation shortens or eliminates the trigger-time forced disconnect: stop and ask a human — this remains an untested, open follow-on question, not resolved by any ADR.
