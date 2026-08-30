# Agent Instructions

<!-- Synthesised by /constitute on 2026-08-30 from: ADR-001, ADR-003, ADR-004, ADR-006, ADR-008, ADR-009, ADR-012, ADR-013, ADR-015, ADR-017, ADR-021 -->
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
- ADR-021 narrows when that signal goes off: it stays on through check-in patience and through a first-attempt collision resync, so treat it as a report of sustained inability to talk, not of instantaneous currency.

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
- Immediate flags refresh after a successful arm/disarm ACK is not required by this ADR when live area/log events already published the new alarm state (ADR-021).

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
- This ADR's own text still mentioned frame skipping as remaining robustness — ADR-021 retired skip-and-resync; the current word on parse misses and reconnect is ADR-021. Which module to use is unchanged.
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

### ADR-017: Use a configurable 5-minute interval for the panel reconciliation poll

**Decision:** The panel reconciliation poll (kept running for its own job, no longer for connectivity) runs every 5 minutes by default; the interval is exposed as an add-on setting, not hardcoded.

**Constraints:**
- The reconciliation poll's timing must not be tied to any connectivity-detection bound, and the poll must not feed Alarm Panel Connection (ADR-021).
- The interval must be an add-on setting, shipping with 5 minutes as the default, not a fixed value.
- A missed live update can now sit uncorrected for up to one full interval (5 minutes by default) instead of 30 seconds before the reconciliation poll catches it — not a safety-relevant delay, since no siren/lockout behaviour depends on this poll.
- Whether the panel's audible pips are actually caused by this poll's prior cadence is unconfirmed; that open question does not change the correctness of this decision either way.
- The check-in schedule must stay independent of this interval in both directions (ADR-021), so changing this setting can never change how quickly a dead session is detected.

### ADR-021: Use one busy-versus-dead session model for panel connection health

**Decision:** Use one model for the whole session: the panel being busy is not the same as the panel being gone. Alarm Panel Connection means we cannot talk to the panel. It does not mean we stubbed our toe while it was still talking.

**Constraints:**
- Alarm Panel Connection goes off only when we cannot talk: the panel hung up, it signalled the end of the session, check-ins have failed for the whole patience window, or an arm or disarm was rejected or timed out.
- A command that already succeeded must not be recorded as a connection failure if a later housekeeping read then misparses.
- While the panel is sending events, do not pile on extra questions whose answer already arrived as a live update. Required check-ins still go out on their clock even when the line is busy.
- After login, and again after a reconnect login, still re-read current zone and alarm state before trusting entity state.
- Never skip unexpected bytes hoping to find the next valid message. If the stream is unusable, close it cleanly and log in again — do not scan forward.
- Reconnect uses one wait interval, keeps trying with no attempt cap, and must release the old connection within a bounded time so this app cannot sit on the panel's single slot.
- A refused arm or disarm still turns Connection off immediately and still has its own countdown to a fresh login. That clock must not be merged into check-in patience.
- Check-in timing must not be tied to the background state-reconciliation poll. Unprompted panel traffic is not proof the session will accept commands.
- Zone and alarm entities stay visible during all of this; only the app process dying can mark them unavailable.
- Recovery must not silently re-issue an arm or disarm the household already saw fail.
- When a read does not parse, log why and enough of the arriving bytes to tell a torn message from a hung-up connection.
- Patience period, check-in cadence, and reconnect wait are install-time settings, not fixed in code. Login's own retry budget must be kept.
- A collision resync that succeeds on the first attempt does not turn Connection off — a torn frame is visible in logs, not on that entity.
- A household still sharing a module with alarm reporting (against ADR-013) gets no skip-and-resync; that is an install violation, not something this app papers over.
- The command-reject fail-window length stays a live-tuning value, not merged into check-in patience.
- FakePanel must not be treated as proof that a refusing session starts answering again without re-login.

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
- **[ADR-012]** Before rewriting the Texecom Alarm App peer in a language other than Python 3: stop and ask a human — that requires a superseding ADR.
- **[ADR-013]** Before assuming every Premier Elite installation has two separate IP modules, or skipping the module-identification step for a new install because this one had two: stop and ask a human — this ADR's evidence is from one household's Elite 88, not a universal layout.
- **[ADR-013]** Before treating a live survive-trigger or HA-Disarm-during-alarm outcome as something FakePanel/CI can prove: stop and ask a human — this ADR's Confirmation keeps those live-only.
- **[ADR-015]** Before encoding household rules (which doors, guests, time of day, notify wording) in the app: stop and ask a human — those stay in Home Assistant automations; this app only honours the three ready controls and emits the blocked-arm event.
- **[ADR-015]** Before sending an arm to the panel when the matching ready control is off, including when Home Assistant requested it: stop and ask a human — that would violate this decision.
- **[ADR-015]** Before gating disarm on the ready controls, or disarming because a ready control was turned off while already armed: stop and ask a human — both are forbidden.
- **[ADR-015]** Before recording a refused arm as anything other than a Home Assistant MQTT event that names the mode and not the reason (for example a sensor, a switch, a notify from the app, or a vague "signal"): stop and ask a human — the kind is decided.
- **[ADR-015]** Before treating FakePanel/CI as proof that a real Home Assistant shows the switches and can automate on the blocked-arm event: stop and ask a human — that remains live-only.
- **[ADR-017]** Before hardcoding the reconciliation poll interval instead of exposing it as a configurable add-on setting: stop and ask a human — this ADR requires it be configurable.
- **[ADR-017]** Before claiming the panel's audible pips are caused by (or fixed by changing) this poll's interval: stop and ask a human — this ADR leaves that cause unconfirmed.
- **[ADR-021]** Before turning Alarm Panel Connection off because a housekeeping read failed after a command that already succeeded: stop and ask a human — that is a collision to resync, not a lost panel, if first re-login succeeds.
- **[ADR-021]** Before sending an extra flags (or similar) read immediately after arm/disarm when live events already published the new alarm state: stop and ask a human — that would violate the busy-versus-dead model.
- **[ADR-021]** Before reintroducing a byte-skip/resync path that treats unexpected panel data as recoverable by scanning forward: stop and ask a human — unexpected bytes must not be skipped.
- **[ADR-021]** Before reintroducing an attempt-count cap or a second reconnect-wait interval for trigger vs everyday disconnects: stop and ask a human — reconnect retries indefinitely on one interval.
- **[ADR-021]** Before merging the check-in patience window and the command-rejection fail window into one timer: stop and ask a human — a panel that answers check-ins while refusing commands would never trigger a fresh login.
- **[ADR-021]** Before letting inbound panel traffic skip or delay a scheduled check-in, or tying the check-in schedule to the reconciliation poll interval: stop and ask a human — both starve check-ins on a healthy busy connection.
- **[ADR-021]** Before treating unprompted panel traffic as evidence the session is healthy for patience-window purposes: stop and ask a human — a session has been observed carrying traffic all day while refusing every command.
- **[ADR-021]** Before ending the session on a single refused or unanswered check-in, or conversely delaying teardown after an outright close or end-of-session signal: stop and ask a human — patience applies only to refused or unanswered check-ins.
- **[ADR-021]** Before hardcoding the patience period, the check-in cadence, or the reconnect wait, or dropping login's own retry budget: stop and ask a human — those are install-time settings, and login retries must stay.
- **[ADR-021]** Before silently re-issuing an arm or disarm that already failed, as part of heal: stop and ask a human — recovery must not re-fire a failed tap.
- **[ADR-021]** Before aborting the mid-run listen loop on a dead path without keep-trying recovery: stop and ask a human — that would require a human restart.
- **[ADR-021]** Before documenting or coding this app as tolerating a household sharing a module with alarm reporting: stop and ask a human — the dedicated module (ADR-013) is the install prerequisite, not a runtime workaround.
- **[ADR-021]** Before claiming from CI/FakePanel that patience recovers a refusing session, or that a real torn-frame during garage disarm stays quiet on Connection: stop and ask a human — those are live-only.
- **[ADR-021]** Before treating the long panel outages seen during investigation as an app defect this decision fixes: stop and ask a human — the competing-client / same-module question is unresolved and is an install issue.
- **[ADR-021]** Before hardcoding the command-rejection fail-window length as a newly final, unchangeable value, or merging it into patience: stop and ask a human — that length stays live-tuning and a separate clock.

## Testing stance

- **CI:** Use stand-ins / hermetic helpers only — never live household hardware or production accounts. Named stand-ins: FakePanel (zone-state snapshot, area-flags snapshot, mode-byte / Part-Arm mapping; scheduled check-ins not starved by inbound traffic and independent of the reconciliation-poll interval; refused check-in inside patience changes neither session nor Connection; continuous refusal past patience → bounded release → reconnect → state re-read; peer close / end-of-session end the session immediately and turn Connection off; non-Connect bytes are not skipped; arm/disarm NAK or timeout turns Connection off immediately and the command-reject watchdog still escalates on its own timer; successful arm/disarm ACK plus a housekeeping decode miss does not record a command-failure reason and does not publish Connection off if re-login succeeds on attempt 1; post-ACK flags refresh is omitted when live AREA already published the new alarm state, and still runs when it has not; reconnect retries indefinitely at one interval with no attempt cap; a failed arm/disarm is not re-issued by heal; decode failure logs reason and leading hex; isolated reconciliation-poll timeout does not degrade Connection; ready-to-arm refuse per ADR-015) and a fake MQTT client (three ready switches that start on; blocked-arm MQTT event with mode and without reason — per ADR-015).
- **CI may not claim:** that patience recovers a refusing session — FakePanel models a refusal as sticky until re-login by construction; that a real Premier Elite torn-frame during garage disarm stays quiet on Connection; that the phone app is or is not on the same module (ADR-021).
- **Live:** `/accept` owns product validation on the real setup (full Away / Night / Home arm sequences, garage-return or equivalent auto-disarm with Connection staying on, trigger reconnect, real ComIP, quiet-house and zombie corroboration, mid-run heal under contention, which network module the panel address actually points to per ADR-013, whether real check-in refusals clear inside the patience period and whether observed long outages were a competing client per ADR-021, and that a real Home Assistant shows the ready-to-arm switches and can automate on the blocked-arm event per ADR-015); `/ship` may smoke a real target. Green CI is not product accept.
