# Spec: ready-to-arm

**Date:** 2026-08-23
**State:** Accepted ✅

---

## Problem

Arming can still set the panel when the house is not ready. If a door or window
is open, the alarm can go off immediately. The household also needs to choose
*which* arm mode is allowed — for example guests staying, so they use Home
rather than Night. Anyone who arms from Home Assistant or HomeKit can hit that
path. Stopping it *after* the panel has armed is too late.

## Goal

The household can see and control whether Away, Home, and Night are ready to
arm. If a mode is not ready, that arm does not set the alarm; the panel stays
as it was. Household rules (which doors, night, guests) stay in their own
automations. Other Premier Elite households get the same knobs without being
protocol experts.

## Scope

**In scope**

- Three ready-to-arm controls in Home Assistant — Away, Home, Night — that
  start **on**, so arming behaves as it does today until someone turns one off.
- If a control is off, the matching arm does not set the alarm, including when
  Home Assistant itself requested it. The alarm stays in the state it already
  was (usually Disarmed if they were arming from rest).
- Disarm always works, even if every ready control is off.
- Home Assistant can see that an arm was blocked, so Activity and a notify
  automation can use it. This app does not explain *why*.
- Automations in Home Assistant can turn the ready controls on and off. This
  app does not decide when they flip.

**Out of scope**

- The keypad on the panel.
- Hiding Away, Home, or Night on the alarm entity so HomeKit or the iOS app
  drop the button. Those clients may still *offer* the mode; the app must still
  refuse the arm.
- This app sending the “why” notification (open door, guests, and so on).
- Disarming because a ready control was turned off while already armed.
- Encoding household rules (which doors and windows, darkness, guests) inside
  this app.
- Changing Lovelace or HomeKit setup.

## Acceptance Criteria

1. Given the app is running, When Home Assistant has received what the app
   publishes, Then three ready-to-arm controls exist for Away, Home, and Night,
   and each starts on.
   - **How we'll know:** integration test (stand-in: FakePanel and a fake
     Home Assistant / MQTT client)

2. Given the Away, Home, or Night ready control is off, When that arm is
   requested, Then the panel is not armed and the alarm entity stays in the
   state it already was.
   - **How we'll know:** integration test (stand-in: FakePanel — no arm
     command, state unchanged)

3. Given a ready control is off, When Home Assistant itself requests that arm,
   Then the refuse is the same as AC2 (panel not armed, state unchanged).
   - **How we'll know:** integration test (stand-in: FakePanel), arm issued on
     the same command path Home Assistant uses

4. Given every ready control is off, When disarm is requested, Then the panel
   still disarms.
   - **How we'll know:** integration test (stand-in: FakePanel)

5. Given an arm was refused because the matching ready control was off, When
   that happens, Then Home Assistant can see that that mode was blocked (enough
   for Activity or a notify automation). The payload does not include the
   household’s reason.
   - **How we'll know:** integration test (stand-in: fake Home Assistant /
     MQTT client sees the blocked-arm signal)

6. Given the alarm is already armed, When the matching ready control is turned
   off, Then the panel does not disarm.
   - **How we'll know:** integration test (stand-in: FakePanel)

7. Given a ready control is on, When that arm is requested, Then arming follows
   `spec-alarm-control.md` (this spec does not change a successful arm).
   - **How we'll know:** integration test (stand-in: FakePanel)

8. Given HomeKit or the iOS app still shows an arm mode whose ready control is
   off, When the user chooses that mode, Then the panel is not armed (same as
   AC2). The mode may still appear in those UIs.
   - **How we'll know:** manual acceptance test (live HomeKit / iOS); refuse
     path itself is AC2/AC3 in CI

## User Stories

- As a household member, I want an arm that is not ready to leave the alarm
  as it was, so an open door cannot set the panel off immediately.
- As a household member, I want to allow Home and not Night (or the reverse)
  when guests are staying, so part-arm matches the house that day.
- As someone writing Home Assistant automations, I want to turn the ready
  controls on and off from ordinary automations, and to notify when an arm was
  blocked, without this app knowing my rules.
- As another Premier Elite household, I want those controls to appear when I
  install the app, so I am not expected to know the panel protocol.

## Edge Cases

- Arm requested while already armed in another mode, and the requested mode’s
  ready control is off — stay in the current armed state; do not disarm.
- Ready control turned off during exit / arming — do not complete that arm on
  the panel; do not treat that as a disarm of a fully armed house (AC6). If
  live timing is ambiguous, prefer “panel not newly armed.”
- All three ready controls on — behaviour matches today’s arming
  (`spec-alarm-control.md`).
- This app does not hide arm modes on the alarm entity; clients that cache
  buttons may still show them (AC8).

## Constraints

- Household policy stays in Home Assistant automations. This app only honours
  the three ready controls and emits that an arm was blocked.
- Disarm is never gated by ready-to-arm.
- Do not rely on HomeKit or iOS dropping arm buttons as the safety mechanism.

## Spike Candidates

- How the three ready controls and the blocked-arm signal should appear as
  ordinary Home Assistant entities (so a non-expert can automate them).
  `/analyse` should pick this up; this spec does not choose the mechanism.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-23 | Clear | — |
