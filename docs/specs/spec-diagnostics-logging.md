# Spec: diagnostics-logging

**Date:** 2026-08-07  
**State:** Accepted ✅

---

## Problem

When monitoring looks wrong (stuck zones, silent sensors, connectivity that still
says live), the operator cannot tell from normal add-on logs whether the panel
still sent activity or the app stopped handling it. Logging is fixed at a coarse
level with little zone/command detail and no way to turn up capture from add-on
configuration — so diagnosis means stopping the add-on for a separate listen, or
guessing.

## Goal

An operator can select **WARNING**, **INFO**, **DEBUG**, or **TRACE** in add-on
configuration (default **INFO**), see appropriately detailed add-on logs for that
choice — including full panel-session detail at TRACE — and correlate those lines
with a known household event timestamp without a separate sniffer.

## Scope

**In scope**

- An add-on configuration control whose options are exactly **WARNING**, **INFO**,
  **DEBUG**, and **TRACE**, with default **INFO**.
- Logging behaviour at each level as in the level guide below (milestones and
  problems at INFO and above; app-meaningful zone/area/command handling at DEBUG;
  panel session traffic at TRACE).
- Instrumentation so those events actually appear at the stated levels (not only
  a config knob with empty DEBUG/TRACE).
- Modem / non-frame piping: suppressed at WARNING, INFO, and DEBUG; at TRACE,
  compact skip notices only (not raw modem dumps).
- Ability to leave TRACE on while hunting a fault and find matching lines around a
  known event time (e.g. a PIR in Home Assistant Activity).

**Out of scope**

- Ring buffers, “dump on zombie” buttons, or other specialised capture UX — TRACE
  plus timestamps are enough.
- Shipping with TRACE (or DEBUG) as the default.
- A separate live panel-sniffer UI or a second simultaneous panel client for
  debugging.
- Making connectivity tell the truth / auto-recover silent session death — that
  remains `spec-panel-link-liveness.md`.

### Log level guide

| Level | When you’d use it | Example scenario | Example log content (illustrative) |
|-------|-------------------|------------------|--------------------------------------|
| **WARNING** | Quietest production | Arm rejected; command failure | `alarm_command_arm_rejected` · `alarm_command_failed: … NAK` · other warnings/errors only |
| **INFO** | Day-to-day (default) | Start, enumerate, reconnect, connectivity | Start line · `enumerated_zones` · reconnect ok/degraded · connectivity live/degraded · plus all WARNING+ |
| **DEBUG** | Did we handle that? | Study PIR open/clear; arm command | Zone/area handling → MQTT outcome · arm/disarm command path outcomes · snapshot/reconnect steps · plus INFO+ |
| **TRACE** | Hunt wire/session truth | Zombie hunt; quiet keepalives | DEBUG+ · panel tx/rx (commands and unsolicited) · keepalive pairs · compact `panel_resync skipped N bytes` for modem/non-frames |

**Severity rule:** choosing a level includes that level and all more severe
messages (e.g. INFO includes WARNING and ERROR; TRACE includes everything).

## Acceptance Criteria

### AC1: Config offers WARNING, INFO, DEBUG, TRACE

Given the add-on configuration UI, When the operator opens the log-level control,
Then the selectable values are **WARNING**, **INFO**, **DEBUG**, and **TRACE**.

- **How we'll know:** unit test or config-schema assertion on the published option
  choices

### AC2: Default is INFO

Given a fresh install with no explicit log-level override, When the app starts,
Then logging runs at **INFO**.

- **How we'll know:** unit test (default settings / startup logging configuration)

### AC3: Selected level is applied

Given the operator selects a level in configuration, When the add-on is running
with that configuration applied (including any restart this add-on already
requires for options), Then log output respects that level per the guide above.

- **How we'll know:** integration test (stand-in: FakePanel + captured log
  handler) for at least INFO vs DEBUG vs TRACE filtering

### AC4: DEBUG shows app-meaningful handling

Given DEBUG, When a zone changes or an arm/disarm command completes against a
stand-in panel, Then logs include handling/outcome lines for that activity
without requiring full raw frame dumps.

- **How we'll know:** integration test (stand-in: FakePanel + captured logs)

### AC5: TRACE shows panel session traffic

Given TRACE, When the stand-in panel emits unsolicited activity or answers a
command, Then logs include panel transmit/receive (or equivalent session traffic)
so an operator can see what hit the session.

- **How we'll know:** integration test (stand-in: FakePanel + captured logs)

### AC6: Modem noise stays out of the way

Given WARNING, INFO, or DEBUG, When non-frame / modem-style piping is skipped,
Then logs do not dump that raw piping. Given TRACE, When the same skip happens,
Then at most a compact skip notice appears (not a raw modem stream).

- **How we'll know:** unit or integration test (stand-in: bytes that force resync /
  skip + captured logs)

### AC7: Live hunt without a separate sniffer

Given TRACE on the running add-on, When a known zone event occurs, Then the
operator can find corresponding log lines around that time in the add-on logs
without stopping the add-on to run a separate panel listener.

- **How we'll know:** manual acceptance test (live panel; correlate HA/MQTT event
  time with TRACE logs)

---

## User Stories

- As the household operator, I want to set WARNING / INFO / DEBUG / TRACE in
  add-on config so I can turn up detail when something looks wrong and turn it
  down again afterward.
- As an installer of this add-on on another Premier Elite panel, I want the same
  control so I can diagnose without changing code.

## Edge Cases

- Options change that requires add-on restart: behaviour matches this add-on’s
  existing options apply rules; AC3 only requires the selected level after config
  is in effect.
- TRACE left on for days: allowed; volume is accepted for hunting — default
  remains INFO so normal installs stay quiet.
- No panel traffic (quiet house) at TRACE: keepalive / probe traffic may still
  appear; absence of ZONE lines is itself useful.
- ERROR always surfaces whenever the configured level is WARNING or finer
  (standard severity inclusion).

## Constraints

- Default log level is **INFO**.
- Config dropdown values are exactly **WARNING**, **INFO**, **DEBUG**, **TRACE**.
- Modem / non-frame piping must not flood WARNING–DEBUG; TRACE may only note
  compact skips.
- Logging must not require marking zone/alarm entities unavailable or taking the
  ComIP session down for a second client.
- Cross-link: connectivity truthfulness / zombie auto-recover remain
  `spec-panel-link-liveness.md`.

## Open Questions

- Exact human labels in the Supervisor UI (e.g. “Log level” vs “Logging”) — settle
  at implement/UI copy time; values above are fixed.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-07 | Clear | — |
