# Acceptance

**Date:** 2026-08-24
**State:** Accepted ✅
<!-- State is exactly one of: Draft 📝 | Accepted ✅ | Deferred ⏸️ -->

## What we set out to build

A Home Assistant add-on that replaces the prior MQTT bridge for a Texecom Premier Elite panel: zone sensors and an alarm control panel over MQTT, including a working Home arm mode. Ready-to-arm switches let the household block Away, Home, or Night without encoding their rules in the add-on; a refused arm must not set the panel, and the Home Assistant card must snap back to the real state.

## Scorecard

| # | Scenario | Result | Notes |
|---|----------|--------|-------|
| 1 | Replacement still live | ✅ pass | Add-on started after local rebuild; panel keepalives and zone MQTT flowing |
| 2 | Ready-to-arm switches | ✅ pass | Away, Home, Night present |
| 3 | Refused arm snaps back | ✅ pass | Away refused; card snapped back; logs showed blocked then MQTT arming |
| 4 | Disarm still works | ✅ pass | Disarm not gated by ready switches |

## Scenario: Replacement still live

**Status:** Pass ✅

- **What we're proving:** The replacement is the live panel in Home Assistant — zones, alarm, connection healthy; old MQTT bridge gone.
- **Examples:** Given the add-on is running with the prior MQTT bridge uninstalled, When Home Assistant is up, Then in-use zone entities and the alarm control panel are present and Alarm Panel Connection is on.
- **You:** Open Home Assistant, find the Texecom Alarm device, confirm zones look like the house, the alarm entity is there, Connection is on, and the old MQTT bridge is not installed.
- **I check:** Add-on `started`; panel keepalives and zone MQTT still flowing.
- **How we know:** Pass if the house view looks right and Connection is on. Fail if zones are missing, Connection is off, or the old bridge is still in use.
- **Result:** pass — practitioner confirmed the live view; add-on had been rebuilt and was publishing zone updates.

## Scenario: Ready-to-arm switches

**Status:** Pass ✅

- **What we're proving:** Away, Home, and Night each have a ready-to-arm switch, and they start on so arming still works until someone turns one off.
- **Examples:** Given a fresh install or restart, When Home Assistant has received discovery, Then three ready-to-arm controls exist and each starts on.
- **You:** Find Ready to arm Away, Home, and Night; confirm they exist and are on (unless turned off on purpose).
- **I check:** Discovery names match those three switches.
- **How we know:** Pass if all three are there. Fail if a switch is missing.
- **Result:** pass — practitioner confirmed all three switches.

## Scenario: Refused arm snaps back

**Status:** Pass ✅

- **What we're proving:** If a mode is not ready, that arm never hits the panel; the alarm card briefly shows Arming then the real state; Home Assistant can see the mode was blocked, not why.
- **Examples:** Given Ready to arm Away (or Home/Night) is off, When that arm is tapped on the alarm card, Then the panel stays as it was and the card returns to that state after a brief Arming.
- **You:** Turn the matching ready switch off, tap that mode, watch the card snap back, confirm the panel did not arm, check Blocked arm named the mode only.
- **I check:** Add-on logs for blocked command and MQTT `arming`.
- **How we know:** Pass if the card snaps back and the panel stays put. Fail if the card stays on the tapped mode or the panel arms.
- **Result:** pass — practitioner confirmed snap-back; logs showed `alarm_command_blocked mode=away` then MQTT `arming`.

## Scenario: Disarm still works

**Status:** Pass ✅

- **What we're proving:** Ready switches never block Disarm. Turning a switch off while already armed does not disarm.
- **Examples:** Given every ready switch is off, When Disarm is requested, Then the panel still disarms. Given the house is already armed, When a ready switch is turned off, Then the panel stays armed.
- **You:** With a ready switch off, tap Disarm; confirm switch-off did not disarm an armed house.
- **I check:** Disarm is not gated on the ready switches.
- **How we know:** Pass if Disarm still works and switch-off did not disarm. Fail if Disarm is refused because a ready switch is off.
- **Result:** pass — practitioner confirmed Disarm still works.

## How it went

- Home Assistant was already up; the add-on had just been rebuilt from the UI and was started.
- This walk focused on the live replacement plus the new ready-to-arm refuse snap-back — not a repeat of the 21 Aug Home/siren walks.
- Refused Away from the alarm card snapped back; add-on logs matched (blocked, then MQTT arming).
- We did not re-walk Night ×3, every sensor class, TRACE log hunting, the household alarm wrapper, a crash-free month, or a second household install — those stayed accepted limitations from 21 Aug.
- HomeKit/iOS refuse (button still offered when the matching ready switch is off; that mode still must not arm) cannot be walked until this add-on is on household Home Assistant.

## Still open

- [x] HomeKit/iOS refuse when a ready switch is off — cannot walk until this add-on is on household HA (limitation accepted)

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-24 | Issues found | 1 |
| 2 | 2026-08-24 | Clear | — |
