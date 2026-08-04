# Agent Instructions

<!-- Synthesised by /constitute on 2026-08-04 from: ADR-001, ADR-002, ADR-003, ADR-004, ADR-005, ADR-006, ADR-007 -->
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

### ADR-005: Use confirmed shared arm/disarm commands with configurable Part-Arm mapping for panel control

**Decision:** Use the empirically confirmed shared arm and disarm commands for production, and treat which arm mode maps to which underlying Part-Arm slot as a per-installation configuration value rather than a hardcoded constant.

**Constraints:**
- The app must issue arm and disarm using the confirmed shared command mechanism, not invent per-mode command families or leave Home unimplemented pending further capture work.
- The mapping from Home Assistant's Home/Night (and Away) labels to the panel's physical Part-Arm slots must be a documented, install-time configuration value — never baked to this household's own engineer layout.
- The app must not assume the panel can auto-report each Part-Arm slot's Night/Home role at startup via the area-details query already tested — that path was ruled out; mapping remains manual configuration unless a future decision finds another source.
- Disarm is mode-independent: one confirmed disarm command covers fully armed states and cancelling an in-progress exit for every arm mode.
- The exact shape of the add-on configuration surface for that mapping (e.g. three fields vs a single ordered list) is not decided by this ADR — only that the mapping must be configurable.

### ADR-006: Use panel zone-state snapshot for startup re-sync

**Decision:** After login (and again after a reconnect re-login), the app must ask the panel for a full current-state snapshot of every zone slot and publish that to MQTT for in-use zones before relying on entity state; live change events then keep those entities updated.

**Constraints:**
- Startup and post-reconnect flows must include a panel zone-state snapshot after login — not push-only and not MQTT-retain-only for correctness.
- Snapshot status encoding must stay aligned with live zone-change event encoding so open/closed meaning does not diverge.
- Test doubles used in CI must speak the same snapshot read so startup re-sync is verifiable without the live panel.
- Client, FakePanel, and tests must implement this snapshot command family (extra round-trip at startup is required).
- ADR-006 itself does not decide area/alarm arm-state startup snapshot — that is settled separately by ADR-007.

### ADR-007: Use panel area-flags snapshot for alarm startup re-sync

**Decision:** After login (and again after a reconnect re-login), the app must ask the panel for a current area-flags snapshot, derive each in-use area’s armed/disarmed/part-armed/in-alarm status from that snapshot, and publish that to MQTT before relying on alarm entity state; live area/log change events then keep the entity updated.

**Constraints:**
- Startup and post-reconnect flows must include a panel area/arm-state snapshot after login — not push-only and not MQTT-retain-only for correctness of the alarm entity.
- Snapshot status meaning must stay aligned with how live area events are interpreted so armed/disarmed/part-armed/in-alarm does not diverge between startup and steady state.
- Test doubles used in CI must speak the same area-flags read so alarm startup re-sync is verifiable without the live panel.
- Part-Arm slot → Home/Night/Away labels remain install-time configuration; the snapshot reports which part-arm slot is active, not which HA mode name that slot carries.
- Client, FakePanel, and tests must implement this snapshot command family and flag decode (extra round-trip at startup is required).
- Exit/entry transient states may still depend on live area pushes — the Disarmed-only spike run did not prove those appear in the flag block.

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
- **[ADR-005]** Before hardcoding this household's Part-Arm slot layout (Away/Night/Home mode values) into the app: stop and ask a human — that would violate this decision; the mapping must be install-time configuration.
- **[ADR-005]** Before implementing auto-detection of Part-Arm slot roles via the area-details query already tested, or treating that query as a source of Night/Home names: stop and ask a human — that path was ruled out by this ADR.
- **[ADR-005]** Before inventing a different per-mode arm command family, or shipping without Home arm because further capture work is pending: stop and ask a human — this ADR requires the confirmed shared command mechanism including Home.
- **[ADR-005]** Before treating a specific add-on option shape for the mode-to-slot mapping (e.g. three fields vs one ordered list) as already decided by this ADR: stop and ask a human — only configurability was decided; the concrete surface is still open.
- **[ADR-006]** Before shipping zone state on restart via push-only updates or MQTT retain alone, without a panel zone-state snapshot after login: stop and ask a human — that would violate this decision.
- **[ADR-006]** Before inventing a different open/closed encoding for the startup snapshot than for live zone-change events: stop and ask a human — this ADR requires one shared status encoding.
- **[ADR-006]** Before treating physical open/close flip corroboration as already proven by this ADR: stop and ask a human — the spike skipped that optional check; residual confidence is a separate acceptance call if needed.
- **[ADR-007]** Before shipping alarm state on restart via push-only updates or MQTT retain alone, without a panel area/arm-state snapshot after login: stop and ask a human — that would violate this decision.
- **[ADR-007]** Before inventing a different armed/disarmed/part-armed/in-alarm meaning for the startup snapshot than for live area events: stop and ask a human — this ADR requires one shared status meaning.
- **[ADR-007]** Before treating the area-flags snapshot as auto-detecting Night/Home role names, or hardcoding Part-Arm → HA mode mapping from snapshot bits alone: stop and ask a human — mapping remains install-time configuration (ADR-005).
- **[ADR-007]** Before treating exit/entry (arming/pending) as fully covered by the area-flags snapshot alone: stop and ask a human — the spike only observed Disarmed; live pushes may still be required for those transients.
- **[ADR-007]** Before treating optional arm-then-re-poll corroboration or wider dual-request area-bitmap layouts as already proven by this ADR: stop and ask a human — those paths were not exercised in the Validated run.
