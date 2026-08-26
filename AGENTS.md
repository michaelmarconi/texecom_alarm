# Agent Instructions

<!-- Synthesised by /constitute on 2026-08-26 from: ADR-001, ADR-003, ADR-004, ADR-006, ADR-008, ADR-009, ADR-011, ADR-012, ADR-013, ADR-015, ADR-016, ADR-017, ADR-018, ADR-019 -->
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
- This ADR's own text notes that reconnect-when-the-socket-dies and frame skipping "remain" as general robustness — ADR-019 has since retired frame skipping (and the asymmetric reconnect interval) entirely, so treat ADR-019 as the current word on that point; ADR-013's own decision (which module to use) is otherwise unaffected.
- Disarm from Home Assistant during a live alarm is expected to work when the local module is the one in use — not when Home Assistant is still on the signalling module.
- This does not prove every Premier Elite installation has two separate modules — treat as one household's evidence, not a universal layout.

### ADR-015: Use ready-to-arm switches and an MQTT blocked-arm event for refusing unready arm commands

**Decision:** The app publishes three ready-to-arm switches in Home Assistant — Away, Home, Night — that start on. If a switch is off, that arm is not sent to the panel, including when Home Assistant itself asked; the alarm stays in the state it already was. Disarm is never blocked. Turning a switch off while already armed does not disarm. When an arm is refused, the app emits a Home Assistant MQTT event naming which mode was blocked, not why.

**Constraints:**
- The app must publish three ready-to-arm controls (Away, Home, Night) that start on, so a new install arms as it does today until someone turns one off.
- When a control is off, the matching arm must not be sent to the panel — including when Home Assistant requested it — and the alarm entity must stay in the state it already was.
- Every arm command to the panel must consult the matching ready control.
- Disarm must never be gated by the ready controls.
- Turning a ready control off while the house is already armed must not disarm the panel.
- The app must not encode household rules (which doors, guests, time of day, notify text) — those stay in Home Assistant automations that turn the controls on and off.
- On refuse, the app must emit a first-class Home Assistant MQTT event that names the mode and does not include the household's reason — not a switch, a sensor, or an unspecified "signal".
- This does not replace ADR-003: entities stay on MQTT discovery, and household-specific arming/notification *rules* stay out of the app; a generic refuse mechanism *does* live in the app.

### ADR-016: Use keepalive failure and command-reject events for panel-connection detection

**Decision:** The panel-connection signal goes down only when routine check-ins stop succeeding (or the connection drops outright), or when an arm/disarm command is rejected or times out. The periodic background reconciliation poll no longer feeds this signal at all — supersedes ADR-010.

**Constraints:**
- The connection signal must not depend on the background reconciliation poll's success or failure.
- A rejected or timed-out arm/disarm command must still immediately mark the connection down.
- Missed routine check-ins or an outright disconnect must still mark the connection down, and it must recover automatically once check-ins resume — no manual restart required.
- The background reconciliation poll keeps running for its separate job of correcting the alarm entity if it disagrees with the panel's last-known state; that job is not removed by this decision.
- The automatic "stayed down too long, log back in again" recovery path (ADR-011) should be re-checked against this narrower set of degrade triggers as ordinary follow-through, not re-decided here.
- Live confirmation of quiet-house and command-rejection behaviour on this simplified design remains open — inherited from the original detection work (ADR-010/SPIKE-008), not newly resolved here.

### ADR-017: Use a configurable 5-minute interval for the panel reconciliation poll

**Decision:** The panel reconciliation poll (kept running by ADR-016 for its own job, no longer for connectivity) runs every 5 minutes by default; the interval is exposed as an add-on setting, not hardcoded.

**Constraints:**
- The reconciliation poll's timing must not be tied to any connectivity-detection bound.
- The interval must be an add-on setting, shipping with 5 minutes as the default, not a fixed value.
- A missed live update can now sit uncorrected for up to one full interval (5 minutes by default) instead of 30 seconds before the reconciliation poll catches it — not a safety-relevant delay, since no siren/lockout behaviour depends on this poll.
- Whether the panel's audible pips are actually caused by this poll's prior cadence is unconfirmed; that open question does not change the correctness of this decision either way.

### ADR-018: Use interval-only reconnect budgets for panel disconnects

**Decision:** Drop the attempts settings for panel reconnect entirely; the app always keeps retrying regardless of disconnect type. (Note: ADR-018's own framing of "the wait interval still varies between an ordinary disconnect and a real-trigger disconnect" is narrowed by ADR-019 — one interval now covers every disconnect. ADR-018's removal of the attempts settings and its indefinite-retry requirement stand unchanged.)

**Constraints:**
- The add-on's config schema must not expose settings that look like they bound behaviour but don't — a genuinely advisory/log-only setting must not be schema-validated.
- Reconnection after any panel disconnect keeps retrying indefinitely — never a stop condition, regardless of disconnect type.
- Anyone who previously set the attempts options (via add-on options or their environment-variable equivalents) will need those removed — they are dropped from the schema, not silently ignored.

### ADR-019: Use a single reconnect interval and no line-noise defense for panel disconnects

**Decision:** Retire frame-resync (skipping unexpected/non-protocol bytes) and the asymmetric reconnect interval entirely — supersedes ADR-014. The app assumes it is always reached over the panel's dedicated local-control module (ADR-013) and treats any unexpected data on the connection as a fault to reconnect from, using one configured wait interval regardless of what caused the disconnect.

**Constraints:**
- Unexpected or non-conforming data on the panel connection must be treated as a fault that triggers a reconnect — not skipped past and parsing resumed.
- Reconnecting after any panel disconnect uses one configured wait interval; the disconnect's cause (everyday drop vs. one following a real trigger) no longer selects a different interval.
- Add-on configuration must expose a single reconnect-wait setting, not separate "everyday" and "trigger" interval settings.
- Product documentation must not describe the app as tolerating a shared or misconfigured module — that stays an install prerequisite (ADR-013), not a runtime accommodation.
- The app must keep retrying a dropped panel connection indefinitely regardless of this change (ADR-004 / ADR-011 / ADR-018 unaffected).
- A household still sharing a module with alarm reporting (against the ADR-013 install requirement) gets no code-level protection from this app any more — that risk is knowingly accepted, not detected or warned about.

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
- **[ADR-011]** Before treating the household connection-entity rename (e.g. Alarm Panel Connection) as already decided by this ADR: stop and ask a human — recovery mechanism only; naming is a separate product rename.
- **[ADR-011]** Before treating in-tap auto-retry of a failed arm/disarm as already decided: stop and ask a human — ADR-011 explicitly leaves that out of scope.
- **[ADR-011]** Before hardcoding the trust-degrade "still stuck" fail window or mid-run heal retry cadence as final, unchangeable values: stop and ask a human — ADR-011 left those for plan time / live tuning.
- **[ADR-011]** Before aborting the mid-run listen loop on unanswered health-check without entering keep-trying recovery: stop and ask a human — that would violate this decision.
- **[ADR-011]** Before treating live ComIP heal / zombie recovery as already proven by CI/FakePanel alone: stop and ask a human — those remain live-only corroboration.
- **[ADR-012]** Before rewriting the Texecom Alarm App peer in a language other than Python 3: stop and ask a human — that requires a superseding ADR.
- **[ADR-013]** Before assuming every Premier Elite installation has two separate IP modules, or skipping the module-identification step for a new install because this one had two: stop and ask a human — this ADR's evidence is from one household's Elite 88, not a universal layout.
- **[ADR-013]** Before treating a live survive-trigger or HA-Disarm-during-alarm outcome as something FakePanel/CI can prove: stop and ask a human — this ADR's Confirmation keeps those live-only.
- **[ADR-015]** Before encoding household rules (which doors, guests, time of day, notify wording) in the app: stop and ask a human — those stay in Home Assistant automations; this app only honours the three ready controls and emits the blocked-arm event.
- **[ADR-015]** Before sending an arm to the panel when the matching ready control is off, including when Home Assistant requested it: stop and ask a human — that would violate this decision.
- **[ADR-015]** Before gating disarm on the ready controls, or disarming because a ready control was turned off while already armed: stop and ask a human — both are forbidden.
- **[ADR-015]** Before recording a refused arm as anything other than a Home Assistant MQTT event that names the mode and not the reason (for example a sensor, a switch, a notify from the app, or a vague "signal"): stop and ask a human — the kind is decided.
- **[ADR-015]** Before treating FakePanel/CI as proof that a real Home Assistant shows the switches and can automate on the blocked-arm event: stop and ask a human — that remains live-only.
- **[ADR-016]** Before making the connection signal depend on the background reconciliation poll's outcome again: stop and ask a human — this ADR requires connectivity to be governed only by check-in failure/disconnect and command-reject/timeout.
- **[ADR-016]** Before treating live quiet-house false-positive rate or live command-rejection zombie reproduction under this simplified detector as already proven by CI/FakePanel alone: stop and ask a human — those remain live-only corroboration.
- **[ADR-016]** Before changing or removing ADR-011's stuck-degrade re-login timing on the assumption it is unaffected by this narrower set of degrade triggers: stop and ask a human — this ADR flags that check as still open, not already done.
- **[ADR-017]** Before hardcoding the reconciliation poll interval instead of exposing it as a configurable add-on setting: stop and ask a human — this ADR requires it be configurable.
- **[ADR-017]** Before claiming the panel's audible pips are caused by (or fixed by changing) this poll's interval: stop and ask a human — this ADR leaves that cause unconfirmed.
- **[ADR-018]** Before reintroducing an attempt-count cap that stops the reconnect loop after N tries: stop and ask a human — this ADR requires reconnection to retry indefinitely regardless of disconnect type.
- **[ADR-019]** Before reintroducing a byte-skip/resync path that treats unexpected panel data as recoverable rather than as a reconnect-triggering fault: stop and ask a human — this ADR requires unexpected data to end the session and trigger reconnect.
- **[ADR-019]** Before reintroducing separate reconnect-wait-interval settings for an everyday disconnect vs. a trigger disconnect: stop and ask a human — this ADR requires one configured interval used for every disconnect cause.
- **[ADR-019]** Before documenting or coding this app as tolerating a household sharing a module with alarm reporting: stop and ask a human — that protection is retired; the dedicated module (ADR-013) is a hard install prerequisite, not something this app defends around.

## Testing stance

- **CI:** Use stand-ins / hermetic helpers only — never live household hardware or production accounts. Named stand-ins: FakePanel (zone-state snapshot, area-flags snapshot, mode-byte / Part-Arm mapping, silent-death / command-reject / quiet-house detector shapes, keepalive-failure and command-reject connection detection with an isolated reconciliation-poll timeout not falsely degrading connectivity, mid-run health-check → reconnect-heal and trust-fail → corroboration / bounded re-login per ADR-006, ADR-008, ADR-009, ADR-011, ADR-016 and architecture; single-interval reconnect-after-disconnect regression with no resync/skip path per ADR-019; ready-to-arm refuse — matching switch off means no arm command and unchanged alarm state, including Home Assistant's command path; disarm still works; switch-off while armed does not disarm — per ADR-015) and a fake MQTT client (three ready switches that start on; blocked-arm MQTT event with mode and without reason — per ADR-015).
- **Live:** `/accept` owns product validation on the real setup (full Away / Night / Home arm sequences, trigger reconnect, real ComIP, quiet-house and zombie corroboration, mid-run heal under contention, which network module the panel address actually points to per ADR-013, and that a real Home Assistant shows the ready-to-arm switches and can automate on the blocked-arm event per ADR-015); `/ship` may smoke a real target. Green CI is not product accept.
