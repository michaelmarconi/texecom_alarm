# ADR-015: Use Ready-to-Arm Switches and an MQTT Blocked-Arm Event for Refusing Unready Arm Commands

**Status:** Accepted ✅
**Date:** 2026-08-23

## Overview

**Background:** People can arm the house from Home Assistant even when the house is not ready — an open door or window can set the panel and the alarm can go off at once. The household also needs to allow one arm mode and not another (for example guests: Home is fine, Night is not). The rules for that belong in the household's own Home Assistant automations, not inside this app. What the app must supply is knobs ordinary people can find, and a refuse that happens *before* the panel is set.
**Decision:** The app publishes three ready-to-arm switches in Home Assistant — Away, Home, Night — that start on. If a switch is off, that arm is not sent to the panel, including when Home Assistant itself asked; the alarm stays in the state it already was. Disarm is never blocked. Turning a switch off while already armed does not disarm. When an arm is refused, the app emits a Home Assistant MQTT **event** naming which mode was blocked, not why.
**Why this way:** Hidden flags, a wrapper alarm, or disarming after the panel has already taken the arm either leave a path that still sets the panel, stop too late, or ask people to be protocol experts. Putting this household's door and guest rules in the app would bake one house's policy into the product. MQTT is already how this app talks to Home Assistant. A blocked arm is something that *just happened*, so the record is an event — not a switch that stays on or off, and not a sensor that holds a lasting reading.
**What this constrains:**
- The app must publish three ready-to-arm controls (Away, Home, Night) that start on, so a new install arms as it does today until someone turns one off.
- When a control is off, the matching arm must not be sent to the panel — including when Home Assistant requested it — and the alarm entity must stay in the state it already was.
- Disarm must never be gated by the ready controls.
- Turning a ready control off while the house is already armed must not disarm the panel.
- The app must not encode household rules (which doors, guests, time of day) — those stay in Home Assistant automations that turn the controls on and off.
- On refuse, the app must emit a first-class Home Assistant MQTT event that names the mode and does not include the household's reason.
- This does not replace the earlier decision that entities are surfaced over MQTT discovery and that household-specific arming/notification *rules* stay out of the app; it records that a generic refuse mechanism *does* live in the app.
**Open follow-ons:** None.

## Context

Arming from Home Assistant can still set the panel when the house is not ready, and it can still choose Night when the household only wanted Home. Stopping that *after* the panel has armed is too late. The original community idea was that the household would publish hidden ready flags for the app to honour — that works for an expert, but the app never *gives* people a control they can see. An earlier decision already forbids putting this household's arming and notification *rules* in the app, and forbids building a native Home Assistant integration. That decision did not record a generic refuse mechanism. This one does: the app owns the knobs and the refuse; Home Assistant owns when the knobs flip and what to tell people.

A blocked arm is a one-shot fact (“Away was refused just now”), not a lasting condition. Home Assistant already has a type for that: an event. A switch would be the wrong kind (that is the ready knobs). A sensor would hold a reading until something else overwrites it. The app sending the notification itself would put the “why” and the wording in the product.

## Decision drivers

- Ordinary Home Assistant users must be able to see and flip ready-to-arm controls without knowing the panel protocol or hand-publishing hidden messages.
- A new install must keep today's arming behaviour until someone turns a control off (controls start on).
- An unready arm must not reach the panel, including when Home Assistant itself requested it.
- On refuse, the alarm must stay in the state it already was — not move to arming.
- Disarm must always work, even if every ready control is off.
- Turning a ready control off while already armed must not disarm.
- Household policy (doors, guests, time of day, notify text) must stay in Home Assistant automations, not in this app.
- Home Assistant must be able to see that an arm was blocked and which mode, so Activity and a notify automation can use it — without this app explaining why.
- The blocked-arm record must be a one-shot “this just happened” fact, not a lasting on/off or a held reading.
- The mechanism must use the same MQTT discovery path this app already uses to surface entities.

## Options considered

- **App-published ready switches plus a Home Assistant MQTT blocked-arm event (chosen)** — the app creates the three controls, honours them before talking to the panel, and emits an MQTT event on refuse.
- **Hidden flags the household must publish themselves** — the original expert-only idea. Rejected because: ordinary users never get a control they can find (driver: visible knobs without protocol expertise).
- **A wrapper alarm in the household's configuration only** — intercept some Home Assistant taps, leave the real entity reachable. Rejected because: it does not stop every request path that can still set the panel (driver: unready arm must not reach the panel).
- **Disarm after a bad arm has already gone to the panel** — send the arm, then try to undo it. Rejected because: the panel may already be in exit or triggered; too late (driver: refuse before the panel is set; stay as it was).
- **Encode this household's door and guest rules in the app** — the app decides when arming is allowed. Rejected because: that is household policy inside the product (driver: policy stays in Home Assistant).
- **The app sends the “why” notification itself** — skip an event and notify from the add-on. Rejected because: notify text and reasons are household policy (driver: mode only, not why; policy in Home Assistant).
- **A flipping on/off sensor as the blocked-arm record** — a state that turns on then off to mean “it happened.” Rejected because: a blocked arm is not a lasting reading (driver: one-shot “this just happened”).
- **An MQTT signal with the Home Assistant type left unspecified** — refuse is announced on MQTT, architecture picks event vs sensor vs something else later. Rejected because: “signal” does not tell implementers which kind of thing to publish, and the kind is already known (driver: one-shot event, not a lasting state).

## Decision

Chosen option: **App-published ready switches plus a Home Assistant MQTT blocked-arm event.**

This is the only option that gives ordinary users visible knobs, keeps new installs behaving as today, stops the arm *before* the panel, leaves household rules in Home Assistant, and records a refuse as a one-shot event on the same MQTT path this app already uses.

## Consequences

**Positive:** Community installs get ready-to-arm controls without being protocol experts. Household automations can turn those controls off (open door, guests, night) and can notify from the blocked-arm event without this app knowing the story. Home Assistant's own arm request is refused the same way as any other. Disarm and an already-armed house are not disturbed. Implementers are not left to guess whether the refuse is a switch, a sensor, or an event.

**Negative:** The app now owns a generic refuse path, so every arm command to the panel must consult the ready controls. Clients that still offer an arm button when a control is off will look as if the tap worked until the household sees the blocked event or the unchanged alarm state. MQTT discovery payloads grow by three switches plus one event entity.

**Follow-on:** None. This ADR does not change how successful arm and disarm talk to the panel. Topic names and event-type strings are implementation, not a further architectural choice of *kind*.

**CI vs live:** A stand-in panel and a fake MQTT client may claim: switches exist and start on; an arm with the matching switch off is not sent to the panel and alarm state is unchanged; the same refuse applies when the request uses Home Assistant's command path; disarm still works; turning a switch off while armed does not disarm; a blocked-arm MQTT event is emitted with the mode and without a reason. That a real Home Assistant discovers the switches, shows them to a person, and can run an automation from the blocked-arm event remains live-only.

## Confirmation

This decision is correctly implemented when: (1) the app publishes three ready-to-arm switches (Away, Home, Night) that start on; (2) with a switch off, a matching arm is not sent to the panel and the alarm stays in the state it already was, including when the request uses Home Assistant's command path; (3) disarm still works with every switch off; (4) turning a switch off while armed does not disarm; (5) a refuse emits a Home Assistant MQTT event that names the mode and not the reason. CI proves (1)–(5) against a stand-in panel and a fake MQTT client. Live acceptance checks that a real Home Assistant shows the switches and can automate on the blocked-arm event.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-23 | Clear | — |
