# Agent Instructions

<!-- Synthesised by /constitute on 2026-08-21 from: ADR-001, ADR-003, ADR-004, ADR-006, ADR-008, ADR-009, ADR-010, ADR-011, ADR-012, ADR-013, ADR-014 -->
<!-- Re-run /constitute after any new ADR is accepted. -->

## Project

Texecom Alarm: a Home Assistant app that talks to a Texecom Premier Elite panel over ComIP/Texecom Connect and publishes zone sensors and an alarm control panel over MQTT discovery, including Home arm mode.

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

### ADR-006: Use panel zone-state snapshot for startup re-sync

**Decision:** After login (and again after a reconnect re-login), the app must ask the panel for a full current-state snapshot of every zone slot and publish that to MQTT for in-use zones before relying on entity state; live change events then keep those entities updated.

**Constraints:**
- Startup and post-reconnect flows must include a panel zone-state snapshot after login — not push-only and not MQTT-retain-only for correctness.
- Snapshot status encoding must stay aligned with live zone-change event encoding so open/closed meaning does not diverge.
- Test doubles used in CI must speak the same snapshot read so startup re-sync is verifiable without the live panel.
- Client, FakePanel, and tests must implement this snapshot command family (extra round-trip at startup is required).
- ADR-006 itself does not decide area/alarm arm-state startup snapshot — that is settled separately by ADR-009.

### ADR-008: Use confirmed shared arm/disarm commands with Away as full arm and configurable Home/Night Part-Arm mapping for panel control

**Decision:** Keep the confirmed shared arm and disarm commands. Away always uses the panel's full-arm mode. Only Home and Night map to engineer Part-Arm slots via install-time configuration; each Part-Arm option is Home, Night, or Unused — never Away.

**Constraints:**
- The app must issue arm and disarm using the confirmed shared command mechanism, including Home — not invent per-mode command families.
- Away must always map to full arm, never to a Part-Arm slot number.
- Home and Night must map to Part-Arm slots through documented install-time configuration — never hardcoded to one household's engineer layout.
- Part-Arm configuration choices are Home, Night, or Unused only; Away must not appear as a Part-Arm option.
- The app must not assume the panel auto-reports Part-Arm Night/Home roles via the area-details query already tested.
- Disarm remains mode-independent: one confirmed disarm covers armed states and cancelling an in-progress exit for every arm mode.
- The exact shape of the add-on configuration surface for Home/Night→slot mapping is not decided by this ADR — only that the mapping must be configurable and that Away is excluded from it.

### ADR-009: Use panel area-flags snapshot for alarm startup re-sync

**Decision:** After login (and again after a reconnect re-login), the app must ask the panel for a current area-flags snapshot, derive each in-use area's armed/disarmed/part-armed/in-alarm status from that snapshot, and publish that to MQTT before relying on alarm entity state; live area/log change events then keep the entity updated.

**Constraints:**
- Startup and post-reconnect flows must include a panel area/arm-state snapshot after login — not push-only and not MQTT-retain-only for correctness of the alarm entity.
- Snapshot status meaning must stay aligned with how live area events are interpreted so armed/disarmed/part-armed/in-alarm does not diverge between startup and steady state.
- Test doubles used in CI must speak the same area-flags read so alarm startup re-sync is verifiable without the live panel.
- When the snapshot reports a Part-Arm slot, Home/Night labels come from install-time configuration (ADR-008); Away is full arm, not a Part-Arm label. The snapshot reports which slot is active, not which HA mode name that slot carries.
- Client, FakePanel, and tests must implement this snapshot command family and flag decode (extra round-trip at startup is required).
- Exit/entry transient states may still depend on live area pushes — the Disarmed-only spike run did not prove those appear in the flag block.

### ADR-010: Use command-reject events and periodic house-state polling for silent panel-path death detection

**Decision:** Treat a rejected or timed-out arm/disarm as an immediate signal that the panel link may be untrustworthy, and separately poll the panel for current house/arm state on a bounded interval as a trust check — alongside the existing idle heartbeat, not instead of it. Do not judge freshness from "zones went quiet" alone.

**Constraints:**
- The panel-connection freshness signal must go degraded on arm/disarm reject or timeout even when the idle heartbeat still succeeds.
- The app must periodically ask the panel for current house/arm state as a corroboration poll; that poll must not replace the idle heartbeat.
- Missing zone push traffic alone must not be the sole reason to mark the link degraded.
- After a brief reject, the link may return to live automatically once corroboration succeeds and no recent command failure remains — without requiring a manual add-on restart.
- Zone and alarm entities stay available with last-known state while the link is degraded (unchanged from ADR-004).
- Exact poll interval, recover window, and "tens of seconds" bound are not fixed here — settle at plan time unless live walks force a change (30s is the current shipping/plan lock from product docs).
- Session tear-down/re-login on stuck degrade is settled by ADR-011; in-tap auto-retry of a failed arm/disarm remains out of scope for ADR-010.

### ADR-011: Use automatic session recovery for mid-run panel path failures

**Decision:** Use automatic session recovery after mid-run panel failure — reconnect when the health check dies, and open a fresh login only when trust stays broken after a short corroboration window.

**Constraints:**
- An unanswered mid-run health check must enter the same keep-trying recovery path as a clean panel drop — connection signal off while recovering; live again with state re-synced when the panel accepts — without a manual add-on restart.
- Soft trust failures may try corroboration first; if still stuck after a bounded fail window, the app must tear down and log in again (still no manual restart).
- Zone and alarm entities must not be blanked solely because recovery is running; freshness stays on the connection signal.
- A failed arm/disarm tap must not be automatically re-fired as part of heal.
- Exact fail-window length and how patient retry cadence lines up with existing mid-run reconnect budgets remain plan-time (and may need live tuning); do not treat reconnect budgets as newly finalised by this ADR alone.
- Renaming the connection entity (e.g. Alarm Panel Connection) is a separate product rename — not decided by this ADR's recovery mechanism.

### ADR-012: Use Python 3 for the Texecom Alarm App

**Decision:** Use Python 3 for the Texecom Alarm App.

**Constraints:**
- New app code for this peer stays in Python 3 — do not reimplement the add-on in another language without a superseding ADR.
- Packaging and runtime stay compatible with a Python 3 process inside the Home Assistant App image (not a second language runtime as the primary app).
- Docker base image and s6 process supervision remain platform packaging, not a separate language decision.

### ADR-013: Use the dedicated local network module for Home Assistant panel access

**Decision:** Home Assistant must use the dedicated local network module the household added for LAN control, not the installer module used for the phone app and the monitoring station.

**Constraints:**
- The panel address in add-on configuration is the local module, not the installer signalling module.
- Do not treat "the panel always kicks Home Assistant off when sirens start" as true for a correctly pointed local module.
- Frame skipping and reconnect-when-the-socket-dies remain; they are not a licence to target the signalling module on purpose.
- Disarm from Home Assistant during a live alarm is expected to work when the local module is the one in use — not when Home Assistant is still on the signalling module.
- This does not prove every Premier Elite installation has two separate modules — treat as one household's evidence, not a universal layout.

### ADR-014: Use host-scoped trigger-disconnect assumptions for panel reconnect design

**Decision:** Treat the forced disconnect and wire noise around arm/disarm/trigger as expected mainly when Home Assistant shares a module with the panel's alarm-reporting path, not as universal panel behaviour. Keep every resilience mechanism in place unconditionally, but stop presenting the long, patient post-trigger reconnect wait as the normal, expected outcome for a correctly set-up install.

**Constraints:**
- Documentation and product messaging must not claim every alarm trigger disconnects Home Assistant from the panel; that is only expected when Home Assistant shares the module used for alarm reporting, or the panel is configured to signal out through every fitted module.
- The app must keep its "skip unexpected data and reconnect" resilience unconditionally — it costs little and still protects installs that are on the wrong module or have not been checked.
- The long, patient post-trigger reconnect wait must remain available as a fallback, but must no longer be documented or coded as the expected outcome for someone who has followed the module-selection guidance.
- Any future claim that a correctly-configured install still drops at trigger needs its own new evidence — it cannot be inherited from the original spike, which ran on the wrong module.
- The specific reconnect wait times and retry counts remain unset by this ADR — only the expected frequency of exercising that budget has changed.

## Stop conditions

- **[ADR-001]** Before implementing a hybrid or cached last-known-good zone list for when the panel can't be reached at startup: stop and ask a human — that path was left open and not validated by this ADR.
- **[ADR-001]** Before planning cutover or testing that assumes the panel can accept more than one simultaneous TCP connection, or that the single-connection behaviour is a configurable setting: stop and ask a human — that was not established by this ADR.
- **[ADR-001]** Before hardcoding or hand-maintaining a zone inventory in configuration as a substitute for panel enumeration: stop and ask a human — that would violate this decision.
- **[ADR-003]** Before building or maintaining a natively-registered `custom_components` Home Assistant integration, or moving household-specific arming/notification logic into this app: stop and ask a human — both would violate this decision.
- **[ADR-004]** Before marking the `alarm_control_panel` or any zone `binary_sensor` entity "unavailable" due to a panel-link/reconnect problem: stop and ask a human — availability must be governed solely by whether the app process itself is running (via MQTT Last-Will), never by panel connection health.
- **[ADR-004]** Before adding a fixed-timeout auto-escalation to "unavailable" for stale panel-link data: stop and ask a human — this ADR explicitly rejected that approach as reintroducing the same problem on a delay; the exact staleness bound (if any) is left open, not decided.
- **[ADR-004]** Before assuming Com Port isolation shortens or eliminates the trigger-time forced disconnect: stop and ask a human — this remains an untested, open follow-on question, not resolved by any ADR.
- **[ADR-006]** Before shipping zone state on restart via push-only updates or MQTT retain alone, without a panel zone-state snapshot after login: stop and ask a human — that would violate this decision.
- **[ADR-006]** Before inventing a different open/closed encoding for the startup snapshot than for live zone-change events: stop and ask a human — this ADR requires one shared status encoding.
- **[ADR-006]** Before treating physical open/close flip corroboration as already proven by this ADR: stop and ask a human — the spike skipped that optional check; residual confidence is a separate acceptance call if needed.
- **[ADR-008]** Before hardcoding this household's Home/Night Part-Arm slot layout into the app: stop and ask a human — that would violate this decision; Home/Night→slot mapping must be install-time configuration.
- **[ADR-008]** Before offering Away as a Part-Arm configuration option, or mapping Away to a Part-Arm slot number: stop and ask a human — Away must always be full arm.
- **[ADR-008]** Before implementing auto-detection of Part-Arm slot roles via the area-details query already tested, or treating that query as a source of Night/Home names: stop and ask a human — that path was ruled out by this ADR.
- **[ADR-008]** Before inventing a different per-mode arm command family, or shipping without Home arm because further capture work is pending: stop and ask a human — this ADR requires the confirmed shared command mechanism including Home.
- **[ADR-008]** Before treating a specific add-on option shape for the Home/Night→slot mapping (e.g. three fields vs one ordered list) as already decided by this ADR: stop and ask a human — only configurability (with Away excluded) was decided; the concrete surface is still open.
- **[ADR-009]** Before shipping alarm state on restart via push-only updates or MQTT retain alone, without a panel area/arm-state snapshot after login: stop and ask a human — that would violate this decision.
- **[ADR-009]** Before inventing a different armed/disarmed/part-armed/in-alarm meaning for the startup snapshot than for live area events: stop and ask a human — this ADR requires one shared status meaning.
- **[ADR-009]** Before treating the area-flags snapshot as auto-detecting Night/Home role names, or hardcoding Part-Arm → HA mode mapping from snapshot bits alone, or treating Away as a Part-Arm slot label: stop and ask a human — Home/Night mapping remains install-time configuration (ADR-008); Away is full arm.
- **[ADR-009]** Before treating exit/entry (arming/pending) as fully covered by the area-flags snapshot alone: stop and ask a human — the spike only observed Disarmed; live pushes may still be required for those transients.
- **[ADR-009]** Before treating optional arm-then-re-poll corroboration or wider dual-request area-bitmap layouts as already proven by this ADR: stop and ask a human — those paths were not exercised in the Validated run.
- **[ADR-010]** Before using missing zone push traffic alone as the sole reason to mark the panel-connection freshness signal degraded: stop and ask a human — that approach was rejected by this ADR.
- **[ADR-010]** Before replacing the idle heartbeat with the house-state corroboration poll, or dropping either: stop and ask a human — this ADR requires both, with distinct roles.
- **[ADR-010]** Before treating live quiet-house false-positive rate or live zombie reproduction as already proven by CI/FakePanel alone: stop and ask a human — those remain live-only corroboration.
- **[ADR-011]** Before treating the household connection-entity rename (e.g. Alarm Panel Connection) as already decided by this ADR: stop and ask a human — recovery mechanism only; naming is a separate product rename.
- **[ADR-011]** Before treating in-tap auto-retry of a failed arm/disarm as already decided: stop and ask a human — ADR-011 explicitly leaves that out of scope.
- **[ADR-011]** Before hardcoding the trust-degrade "still stuck" fail window or mid-run heal retry cadence as final, unchangeable values: stop and ask a human — ADR-011 left those for plan time / live tuning.
- **[ADR-011]** Before aborting the mid-run listen loop on unanswered health-check without entering keep-trying recovery: stop and ask a human — that would violate this decision.
- **[ADR-011]** Before treating live ComIP heal / zombie recovery as already proven by CI/FakePanel alone: stop and ask a human — those remain live-only corroboration.
- **[ADR-012]** Before rewriting the Texecom Alarm App peer in a language other than Python 3: stop and ask a human — that requires a superseding ADR.
- **[ADR-013]** Before assuming every Premier Elite installation has two separate IP modules, or skipping the module-identification step for a new install because this one had two: stop and ask a human — this ADR's evidence is from one household's Elite 88, not a universal layout.
- **[ADR-013]** Before treating a live survive-trigger or HA-Disarm-during-alarm outcome as something FakePanel/CI can prove: stop and ask a human — this ADR's Confirmation keeps those live-only.
- **[ADR-014]** Before claiming, in documentation or code, that a correctly-configured install still drops the panel connection at every real trigger: stop and ask a human — this ADR requires its own new evidence for that claim; it cannot be inherited from the original (wrong-module) spike.
- **[ADR-014]** Before removing, disabling, or making the frame-resync or reconnect-on-drop mechanisms conditional on which module is configured: stop and ask a human — this ADR requires them to stay unconditional.
- **[ADR-014]** Before hardcoding the reconnect wait times or retry counts as final, unchangeable values: stop and ask a human — this ADR leaves them unset; only the expected frequency of exercising that budget has changed.
- **[ADR-014]** Before documenting or coding the long post-trigger reconnect wait as the expected outcome for a correctly set-up install: stop and ask a human — this ADR treats it as a safety net for misconfiguration, not the normal path.

## Testing stance

- **CI:** Use stand-ins / hermetic helpers only — never live household hardware or production accounts. Named stand-ins: FakePanel (zone-state snapshot, area-flags snapshot, mode-byte / Part-Arm mapping, silent-death / command-reject / quiet-house detector shapes, mid-run health-check → reconnect-heal and trust-fail → corroboration / bounded re-login per ADR-006, ADR-008, ADR-009, ADR-010, ADR-011 and architecture; forced-disconnect-at-trigger resync/reconnect regression per ADR-014).
- **Live:** `/accept` owns product validation on the real setup (full Away / Night / Home arm sequences, trigger reconnect, real ComIP, quiet-house and zombie corroboration, mid-run heal under contention, which network module the panel address actually points to per ADR-013, and whether a correctly-configured install still forces a disconnect at trigger per ADR-014); `/ship` may smoke a real target. Green CI is not product accept.
