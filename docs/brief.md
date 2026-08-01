# Texecom Alarm — HA Integration Replacement

A ground-up, self-built Home Assistant integration for a Texecom Premier Elite
alarm panel (via ComIP/Texecom Connect), replacing the closed-source, unreliable
`the prior MQTT bridge` add-on with something that doesn't crash and finally supports Home
arm mode.

**Date:** 2026-08-01
**State:** Accepted ✅

## Problem & Context

The household currently bridges its Texecom Premier Elite alarm panel to MQTT/Home
Assistant via the [`a prior MQTT bridge add-on`](a prior MQTT bridge)
add-on, communicating with the panel through a ComIP module on the LAN. It works, but:

- The add-on falls over occasionally (crashes/restarts) — an HA community thread
  suggests this may stem from a panel-firmware bug triggered when TX and RX collide,
  and a [known GitHub issue](community reports of MQTT-bridge crashes after Supervisor restart)
  ties another crash pattern to HA Supervisor restarts.
- Arming to **Home** mode (`part_arm_2` in the current config) has **never** worked
  without crashing the add-on — there's no `arm_home` handler in the HA-side wrapper
  at all today, because it's never been safe to expose one.
- The core application (`a prior MQTT bridge`) is **closed-source** — only the
  thin `-hassio` add-on wrapper repo is public — so it can't be forked or patched.

Because the Texecom Connect wire protocol is only partially documented publicly (see
References below), and no code/prior art implements arm/disarm commands, the
arm/disarm command framing for this panel is currently unknown.

## Target Users

Primary: the household — the people who arm/disarm via the `house_alarm_panel`
wrapper entity, get the auto-arm/auto-disarm/notification automations, watch the
~35-zone "Security" Lovelace dashboard, and use the HomeKit exposure — today, several
times a day, via an integration they can't fix when it breaks.

No secondary/external users for v1. Publishing this for other households is a
possible future stretch goal but is explicitly not shaping scope right now (see
Non-goals).

## Goals & Non-goals

**Goals**

- Full feature-parity replacement for `the prior MQTT bridge`: reproduce all ~35 zone
  entities and the alarm control panel entity, without regressing anything in the
  existing HA automation/dashboard/HomeKit layer (full checklist in
  `docs/ha-alarm-usage-spec.md`).
- A working, non-crashing Home arm mode (`part_arm_2` → `armed_home`) — the one
  capability `the prior MQTT bridge` has never supported.
- Materially fewer reliability issues (crashes / unplanned restarts) than the
  current add-on — target zero over a rolling month post-deployment (see Success
  Metrics).
- A documented, empirically-verified understanding of the Texecom Connect protocol
  (framing, arm/disarm/zone/event commands) produced by direct packet capture
  against the live panel — sufficient to build and maintain the above.

**Non-goals**

- Publishing/packaging this for other households or other Texecom panel models —
  deferred; not a v1 goal and shouldn't drive design decisions now.
- Support for the older UDL/Wintex protocol (engineer-level config access) — only
  the Texecom Connect protocol (zones/areas/arm/disarm/log/power) needed for
  day-to-day HA use is in scope.
- Reimplementing the arm guard-condition, notification, or auto-arm/auto-disarm
  logic that already lives in the HA config layer (`configuration/templates/
  house_alarm.yaml`, `script.notify_actor`, `configuration/automations/
  house_alarm.yaml`) — it operates purely on HA-side entities and stays as-is.
- Building a new dashboard or UI — the existing Lovelace "Security" dashboard and
  HomeKit bridges keep working off the same entity names/states.

## Capabilities

Work happens in two sequential phases.

**Phase 1 — protocol research (collaborative, hands-on).** Capture live network
traffic between the HA OS host and the Texecom ComIP module while physically
triggering zones around the house (opening/closing doors and windows), arming and
disarming in each mode, and deliberately triggering an alarm — then decode the
captures against known Texecom Connect framing/CRC/command-ID references to work
out how to determine zone lists, activity, and arming/disarming programmatically.

**Phase 2 — ordered development.** Gated on phase 1 having decoded the core
protocol, build the app itself: an HA-compatible alarm_control_panel entity and the
full set of zone binary_sensor entities (via MQTT discovery or a native
integration), matching the functional spec in `docs/ha-alarm-usage-spec.md`.

## Constraints

- **Hard sequencing dependency:** phase 2 cannot start until phase 1 has decoded
  zone state, arm/disarm, and trigger events for all three arm modes — including
  the byte sequence for the Home-arm mode that currently crashes the add-on.
- Phase 1 requires physical presence in the house to trigger sensors, arm/disarm,
  and trigger alarms live — it's disruptive and has to happen in person.
- Runs against Home Assistant OS (Alpine-based host); the panel is reached over the
  LAN via a ComIP module. No tap or port-mirroring is needed — a capture on the
  host's own LAN interface sees the full conversation, since the host is one of the
  two TCP endpoints.
- Must ultimately produce HA-compatible entities (via MQTT discovery or a native
  integration) equivalent to today's — but there's no dependency anywhere in the HA
  config on today's exact MQTT topic structure, so the wire/topic schema is
  otherwise free.
- No control over the panel firmware or the closed-source `the prior MQTT bridge` core —
  can't fork or patch either, so any crash-avoidance fix (e.g. the suspected TX/RX
  collision bug) has to be handled at the protocol/timing level in the new app.

## Success Metrics

- **Phase 1 complete** / not started / captures reliably decode zone state,
  arm/disarm, and trigger events for all three arm modes (including Home) / manual
  review of decoded captures against live-triggered ground truth in the house.
- **Feature parity** / 0% (nothing built yet) / 100% of entities and automations in
  `docs/ha-alarm-usage-spec.md` reproduced without regression / checklist
  walkthrough against that spec once the app is built.
- **Reliability** / unknown, unquantified today (occasional crashes/restarts) /
  zero unplanned crashes or restarts over a month of normal use, including
  successful Home-mode arm/disarm cycles / HA/app log monitoring post-deployment.

## References

Prior art for the Texecom Connect / ComIP protocol (partially reverse-engineered
publicly, so this doesn't start from zero):

- [davidMbrooke/texecom-connect](https://github.com/davidMbrooke/texecom-connect) —
  Python decoder for events, zone/area status, and time/voltage polling. Does
  **not** implement arm/disarm. Developed under an NDA with Texecom, but the author
  confirmed distributing the *code* (not Texecom's protocol docs) is fine.
- [shuckc/pytexalarm](https://github.com/shuckc/pytexalarm) — reverse-engineered
  the older UDL/Wintex protocol via a logic analyzer and `ser2net` captures, with a
  documented dissection in its `protocol/` folder. Good methodology reference even
  though it targets a different protocol variant. Links to Mike Stirling's
  [alarm-server](https://github.com/mikestir/alarm-server) (ARC receiver over TCP).
- [RoganDawes/WintexProtocol](https://github.com/RoganDawes/WintexProtocol) — Java
  decoder, same protocol family as pytexalarm.
- HA community thread: [the prior MQTT bridge: Texecom alarm panel and MQTT integration with
  HA support](Home Assistant community reports of Premier Elite MQTT bridges).
- [`a prior MQTT bridge add-on` GitHub issue #106](community reports of MQTT-bridge crashes after Supervisor restart).
- `a prior MQTT bridge add-on`'s own [README](a prior MQTT bridge)
  documents the full MQTT topic surface and panel log event types — useful as a
  cross-check for the functional spec.

Current setup, at time of writing: HA OS host on `eth0` (`192.0.2.12`);
`the prior MQTT bridge` add-on `the prior add-on` v1.3.1 on the internal `hassio`
Docker bridge (container `198.51.100.2`, NAT'd out through `eth0`); panel at
`192.0.2.10`, default port 10001, no `udl_password` set; `cache: false`,
`log: info`.

## Related docs

- `docs/ha-alarm-usage-spec.md` — full functional spec of everything today's
  `the prior MQTT bridge` + HA config layer does with the alarm: entity architecture, the
  full ~35-zone inventory, every dependent automation/script, and the arm-mode
  mapping. This is the phase 2 "must not regress" checklist.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-01 | Issues found | 1 |
| 2 | 2026-08-01 | Clear | — |
