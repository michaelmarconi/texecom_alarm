# ADR-003: Use MQTT Discovery (Not a Native Integration) for Entity Surfacing

**Status:** Accepted ✅
**Date:** 2026-08-03

## Overview

**Background:** This project must produce a Home Assistant alarm entity and a set of zone
entities, the same way today's add-on does. There were two ways to build that: as a proper,
natively-registered Home Assistant integration, or as an app that talks to Home Assistant only
over MQTT. Leftover project documentation still described this as an open choice.
**Decision:** Build this as an app that publishes entities to Home Assistant purely over MQTT
discovery, not as a natively-registered integration.
**Why this way:** A native integration means taking on ongoing packaging, listing, and
maintenance overhead for something not yet planned to be published beyond this household, and
the project was already set up from the start as an app rather than an integration. MQTT
discovery, by contrast, is exactly what today's add-on already does, so nothing downstream in
the household's existing automations, dashboard, or HomeKit setup needs to change.
**What this constrains:**
- The app must not embed any household-specific arming/notification rules — that logic has to
  keep living entirely in the household's own Home Assistant configuration, not in this app.
- The app needs its own connection to an MQTT broker as a standing runtime dependency, the same
  as today's add-on.
- Entities this app produces will look and behave like any other MQTT-discovered device in Home
  Assistant, not like a first-class, natively-registered integration with its own configuration
  UI.
**Open follow-ons:** None.

## Context

The project began life scaffolded as a Home Assistant App (add-on) — `config.yaml`, `Dockerfile`,
and `rootfs/etc/services.d/` already follow the `home-assistant/apps-example` template, not a
`custom_components` integration layout. Separately, `docs/brief.md` and
the product brief and capability specs still phrase entity production as "via MQTT discovery or a native
integration," leaving the choice looking open on paper. `docs/analysis.md`'s RISK-002 originally
framed a related but distinct question — whether to collapse the household's own
`house_alarm_panel` template wrapper into a more natively-modeled entity — as requiring a spike
(`SPIKE-004`). That spike was dismissed during its interview once it became clear the "native
entity" alternative it was comparing against doesn't exist given the App-not-integration
commitment already made in the repo, and that `spec-alarm-control.md` already keeps
household-specific guard-condition/notification logic out of the app as a non-goal. That
dismissal surfaced an architectural decision that had never been formally recorded — this ADR
records it.

## Decision drivers

- Must not require building or maintaining a natively-registered `custom_components` integration
  (an explicit preference, and consistent with the app scaffolding already in place).
- Must support the full alarm state/service set this project needs (`armed_home`, `pending`,
  `arming`, `disarming`, `triggered`, plus `arm_home`/`arm_away`/`arm_night` as arm features).
- Must not require moving household-specific guard-condition/notification logic into the app
  (already a stated non-goal in `spec-alarm-control.md`).
- Should avoid forcing a migration of the household's existing config layer (templates,
  automations, HomeKit bridges), which today targets MQTT-discovered entities.

## Options considered

- **Native Python integration (`custom_components`)** — a first-class HA integration registered
  in the entity registry, with its own config flow. Rejected because: it directly conflicts with
  the "must not require building/maintaining a native integration" driver, and the project is
  already scaffolded as an app, not an integration.
- **Plain MQTT topics, hand-wired in `configuration.yaml`** — publish state to fixed topics and
  require the household to manually declare each entity in YAML, without using HA's MQTT
  discovery protocol. Rejected because: it reintroduces exactly the hand-maintained-inventory
  burden `ADR-001` already rejected for zone discovery, and would still force a migration of the
  household's config layer away from its current MQTT-discovered entities.
- **MQTT discovery from an App** — publish HA's standard MQTT discovery payloads for
  `alarm_control_panel` and `binary_sensor` entities from a long-running app process. Chosen.

## Decision

Chosen option: **MQTT discovery from an App**

This is the only option that satisfies every decision driver simultaneously: it requires no
native integration, HA's MQTT discovery schema for `alarm_control_panel` already documents
support for every state and arm feature this project needs (confirmed against first-party HA
documentation during the `/spike 004` interview), it keeps household-specific logic entirely out
of the app by construction (the app only ever publishes panel state — it has no mechanism for
guard conditions), and it requires no migration since the household's config layer already
targets MQTT-discovered entities today.

## Consequences

**Positive:** No entity-registry, config-flow, or HACS-style packaging/distribution overhead;
the app can remain a straightforward long-running MQTT-publishing process, consistent with the
app skeleton already scaffolded; the household's existing templates, automations, and HomeKit
bridges need no migration.

**Negative:** MQTT-discovered entities are less "native" than a registered integration — no
config-flow UI, no strongly-typed entity classes in HA core, and discovery payloads must be
hand-kept in sync with whatever states/features HA's MQTT `alarm_control_panel`/`binary_sensor`
platforms support. The app carries a standing runtime dependency on an MQTT broker. Any
household-specific arming rules or notifications must be implemented entirely outside this app,
in the consuming household's own Home Assistant configuration.

**Follow-on:** None.

## Confirmation

The architecture/build should show the app registering entities solely through its own MQTT
client publishing HA's standard MQTT discovery topics — no `custom_components/` directory, no
integration config entry, and no entity registry registration outside of what HA's MQTT
integration creates automatically from the discovery payloads.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-03 | Clear | — |
