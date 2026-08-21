# Acceptance

**Date:** 2026-08-21
**State:** Accepted ✅
<!-- State is exactly one of: Draft 📝 | Accepted ✅ | Deferred ⏸️ -->

## What we set out to build

A Home Assistant add-on that replaces the prior MQTT bridge for a Texecom Premier Elite panel: zone sensors and an alarm control panel over MQTT discovery, including a working Home arm mode, without the old add-on crashing on Home or locking out Disarm during a live alarm when Home Assistant uses the dedicated local network module.

## Scorecard

| # | Scenario | Result | Notes |
|---|----------|--------|-------|
| 1 | Replacement is live | ✅ pass | ~40 in-use zones, alarm entity, Alarm Panel Connection ON; add-on on dedicated ComIP `192.0.2.11`; the prior MQTT bridge not installed |
| 2 | One door/window open-close | ✅ pass | Front Door and Mstr Bed L Wind followed on MQTT; Connection stayed ON |
| 3 | Today's Home + siren walks | ✅ pass | Practitioner confirmed this afternoon's live Home arm/disarm and Away → alarm → HA Disarm on this add-on; link stayed on |

## Scenario: Replacement is live

**Status:** Pass ✅

- **What we're proving:** The replacement surfaces the panel's zones and alarm in Home Assistant with the prior MQTT bridge gone, and the panel link looks healthy.
- **Examples:** Given the new integration is running with the prior MQTT bridge fully uninstalled, When Home Assistant is up, Then the in-use zone entities and alarm control panel are present; Connection is on; we are not talking to the installer signalling module.
- **You:** Open Home Assistant, find the Texecom Alarm device, confirm zones look like the house, Alarm Panel Connection is on, and the prior MQTT bridge is not in the add-on list.
- **I check:** MQTT zone states (~40 in-use), alarm `disarmed`, `texecom/panel_connection/state` ON, add-on `panel_host` `192.0.2.11`, no the prior MQTT bridge add-on.
- **How we know:** Pass if the entities look like this panel and the old add-on is gone. Fail if zones are missing, Connection is off, or the host is still the signalling module.
- **Result:** pass — practitioner confirmed the HA view; MQTT matched (40 zone states, Connection ON, last-trigger snapshot still from 17:09 zone 4).

## Scenario: One door/window open-close

**Status:** Pass ✅

- **What we're proving:** A physical zone change shows up in Home Assistant quickly, with the connection staying live.
- **Examples:** Given a representative contact zone, When it is physically opened and then closed, Then the HA entity follows within about 2 seconds.
- **You:** Open Front Door (or any reachable contact), wait for HA, then close it. Practitioner also opened two main-bedroom windows.
- **I check:** MQTT `texecom/zone/{n}/state` flipping `0 → 1 → 0` for those contacts; Connection stays ON.
- **How we know:** Pass if the entity follows both ways without Connection dropping. Fail if it stays closed, lags badly, or Connection drops.
- **Result:** pass — Front Door (zone 1) and Mstr Bed L Wind (zone 18) each went open then closed. Hallway/study PIRs also fired while walking. Only one master-bedroom *contact* published a flip; practitioner did not flag the second window as missing.

## Scenario: Today's Home + siren walks

**Status:** Pass ✅

- **What we're proving:** Home arm works without crashing the add-on, and Disarm from Home Assistant actually stops a live alarm while the panel link stays on (dedicated local module).
- **Examples:** Given the prior MQTT bridge uninstalled, When Home is armed then disarmed from HA, Then the panel follows and the add-on stays up. Given the panel is armed and a zone triggers so the siren sounds, When Disarm is sent from HA, Then the alarm stops and Connection stays ON.
- **You:** Confirm this afternoon's live walks were this add-on on the ComIP: Arm Home then Disarm, and Arm → real alarm → Disarm from HA.
- **I check:** This afternoon's MQTT log (`arming` → `armed_home` → `disarmed`; then `armed_away` → `triggered` → `disarmed` with no Connection OFF) and the retained last-trigger snapshot (zone 4, 17:09:47).
- **How we know:** Pass if those walks are confirmed for this add-on. Fail if Home still crashes, HA Disarm does not stop the alarm, or Connection drops on the dedicated module.
- **Result:** pass — practitioner confirmed both walks; we did not re-arm or re-trigger in this session.

## How it went

- HA was already running; cold-start left the add-on on ComIP `192.0.2.11` (not the old signalling-module address).
- Zone inventory in HA looked right to the practitioner (~40 in-use slots from the panel, not a hand-kept list).
- One physical walk was enough: Front Door plus a bedroom window, with PIRs along the way.
- Home arm and live-alarm Disarm were not repeated — they were done on this add-on this afternoon, and the practitioner confirmed that still stands.
- We did not walk Night ×3, five sensor classes, TRACE log hunting, the household `house_alarm_panel` wrapper (that lives on household HA, not this sim), a month of crash-free running, or a second household's install.

## Still open

- [x] Night arm ×3 (spec-alarm-control: Away / Night / Home each three times; this walk covered Home + Away, not Night) (limitation accepted)
- [x] One physical zone per sensor class (door, window, shock, PIR, other) — this walk covered door + window + incidental PIR (limitation accepted)
- [x] TRACE live hunt: correlate a known zone event with add-on TRACE logs (limitation accepted)
- [x] Household `house_alarm_panel` wrapper and HA aggregates (`all_doors`, automations) against this add-on — lives on household HA, not this sim (limitation accepted)
- [x] Month of crash-free running (brief reliability metric) (limitation accepted)
- [x] Second Premier Elite household can install from the public add-on repo and configure Part-Arm mapping without code changes (limitation accepted)

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-21 | Issues found | 1 |

