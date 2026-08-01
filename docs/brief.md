# Replacing the prior MQTT bridge with a custom add-on

## Status: idea / spike only — not started

This is a brief for a **future project**, written after a short spike to confirm
feasibility of reverse-engineering the Texecom panel protocol by packet capture. No
code has been written and no capture has been taken yet.

## Problem statement

We use the [`a prior MQTT bridge add-on`](a prior MQTT bridge)
add-on to bridge our Texecom Premier Elite alarm panel (via a ComIP module) to MQTT /
Home Assistant. It works, but:

- It falls over occasionally (add-on crashes/restarts).
- Arming to **"Home"** mode (`part_arm_2` in our config) has **never** worked without
  crashing the add-on.
- The core application (`a prior MQTT bridge`, the actual npm/Docker image) is
  **closed-source** — only the thin `-hassio` add-on wrapper repo is public — so we
  can't fork and fix it ourselves.

Goal: write our own Home Assistant add-on from scratch that is at least a full
superset of `the prior MQTT bridge`'s functionality, fixes the reliability/Home-arm issues, and
covers everything we currently rely on — then publish it for the community.

## Current setup (as of this spike)

- Home Assistant OS host: Alpine Linux, root shell available with `tcpdump`, `docker`
  (protected — needs "Advanced SSH & Web Terminal" protection mode disabled to use),
  and `ha` (Supervisor CLI).
- Host LAN interface: `enp0s18` (`192.168.1.35`).
- `the prior MQTT bridge` add-on: slug `the prior add-on`, v1.3.1, runs on the internal
  `hassio` Docker bridge (`host_network: false`, container IP `172.30.33.2`) — **not**
  host networking. Its traffic to the panel is NAT'd out through `enp0s18`.
- Panel: `192.168.1.183`, default port (10001), no `udl_password` currently set in the
  add-on options.
- Area/arm mapping in use today (`ha addons info the prior add-on`):
  - `full_arm` → `armed_away`
  - `part_arm_1` → `armed_night`
  - `part_arm_2` → `armed_home` ← the mode that crashes the add-on
- `cache: false`, `log: info`.
- HA-side integration: `alarm_control_panel.texecom_alarm_arm_status` (from the
  add-on's MQTT discovery) is wrapped by a template alarm panel
  (`configuration/templates/house_alarm.yaml`, entity
  `alarm_control_panel.house_alarm_panel`) which adds door/window-open guards before
  arming away or night, and drives automations in
  `configuration/automations/house_alarm.yaml` (auto-arm countdown when empty,
  auto-disarm on door/garage open, TTS announcements, notifications, flashing the
  house number light on armed-away).

## Feasibility finding: packet capture is easy here

No network tap or switch port-mirroring is needed. Because the HA OS host is one of
the two TCP endpoints (the add-on's container traffic is NAT'd through the host's own
physical NIC), a simple capture on the host sees 100% of the conversation:

```bash
tcpdump -i enp0s18 host 192.168.1.183 -w texecom_capture.pcap
```

Plan for when we pick this up:

1. **Baseline capture** — capture, then arm Away (known working) and disarm, for a
   clean reference conversation.
2. **Crash capture** — capture, then trigger Home arm and let it crash, to get the
   exact byte sequence leading up to failure.
3. **Decode and diff** both captures using known framing/CRC/command-ID structure (see
   references below) to find where they diverge (wrong command byte, malformed
   length/CRC, or a TX/RX timing collision).
4. Use findings to inform the design of the replacement add-on.

## Useful prior art / references

The wire protocol (Texecom "Texecom Connect" protocol over ComIP/SmartCom — distinct
from the older UDL/Wintex protocol) has been partially reverse-engineered publicly, so
we don't have to start from zero:

- [davidMbrooke/texecom-connect](https://github.com/davidMbrooke/texecom-connect) —
  Python decoder for the Texecom Connect protocol (events, zone/area status, polling
  for time/voltage). Does **not** implement arm/disarm commands, but gives message
  framing, CRC, and command/event IDs as a starting point. Developed under an NDA with
  Texecom, but the author confirmed with Texecom that distributing the *code* (not the
  protocol docs themselves) is fine.
- [shuckc/pytexalarm](https://github.com/shuckc/pytexalarm) — reverse-engineered the
  older UDL/Wintex protocol via a Saleae logic analyzer and `ser2net` captures, with a
  documented dissection in its `protocol/` folder. Good methodology reference even
  though it targets a different protocol variant. Also links to Mike Stirling's
  [alarm-server](https://github.com/mikestir/alarm-server) (ARC receiver over TCP).
- [RoganDawes/WintexProtocol](https://github.com/RoganDawes/WintexProtocol) — Java
  decoder, same protocol family as pytexalarm.
- HA community thread: [the prior MQTT bridge: Texecom alarm panel and MQTT integration with HA
  support](Home Assistant community reports of Premier Elite MQTT bridges)
  — includes reports that the add-on crash may stem from a **panel-firmware bug when
  TX and RX collide** (not necessarily unique to the Home-arm command specifically),
  per the maintainer's own investigation.
- [`a prior MQTT bridge add-on` GitHub issue #106](community reports of MQTT-bridge crashes after Supervisor restart)
  — another crash pattern, this one tied to HA Supervisor updates stopping/restarting
  the container.
- `a prior MQTT bridge add-on`'s own [README](a prior MQTT bridge)
  documents the full MQTT topic surface (`zone`, `area`, `area/.../command`, `text`,
  `datetime`, `status`, `power`, `log`, `config`) and the full list of panel log event
  types — useful as a functional spec for what our replacement needs to match.

## Open questions for when we start

- Scope: diagnose-and-patch vs. full from-scratch replacement (current intent: full
  replacement, published for the community).
- Language/runtime for the new add-on (the existing app is Node-based; no requirement
  to match).
- Whether to capture live traffic passively first (safe) before deliberately
  triggering the Home-arm crash again (disruptive, needs a convenient time).
- Whether to also support the older UDL protocol (Wintex-style config access) or only
  the Connect protocol needed for day-to-day HA use (zones/areas/arm/disarm/log/power).
