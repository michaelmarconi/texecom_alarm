# ADR-013: Use the dedicated local network module for Home Assistant panel access

**Status:** Accepted ✅  
**Date:** 2026-08-21  
**Spike:** [spike-010-comip-stays-online/SPIKE.md](../spikes/spike-010-comip-stays-online/SPIKE.md)

## Overview

**Background:** Home Assistant used to lose the panel during Home arm/disarm and
during a real alarm — Disarm from the dashboard did nothing. That was treated as
normal panel behaviour. It was actually talking to the installer’s signalling
box, which is meant to grab the line when an alarm is reported.
**Decision:** Home Assistant must use the dedicated local network module the
household added for LAN control, not the installer module used for the phone app
and the monitoring station.
**Why this way:** On that local module, Home arm/disarm and a live alarm plus
Disarm from Home Assistant kept the link up and Disarm actually worked. Pretending
every alarm still drops the link would describe the wrong box.
**What this constrains:**
- The panel address in add-on configuration is the local module, not the installer
  signalling module.
- Do not treat “the panel always kicks Home Assistant off when sirens start” as
  true for a correctly pointed local module.
- Frame skipping and reconnect-when-the-socket-dies remain; they are not a licence
  to target the signalling module on purpose.
- Disarm from Home Assistant during a live alarm is expected to work when the
  local module is the one in use — not when Home Assistant is still on the
  signalling module.
**Open follow-ons:** Whether the long extra-patient reconnect-after-alarm schedule
should be narrowed (that is a later decision, not this one). Whether to mark the
earlier “Disarm during alarm failed” spike as installer-module-only.

## Context

Live work on this Elite 88 saw junk around Home arm/disarm and a TCP drop at a
real alarm, then HA Disarm doing nothing while sirens ran. Those sessions used
the installer SmartCom address. In 2026-08-21 that was distinguished from the
homeowner ComIP. SPIKE-010 ran the two sequences that used to fail — Arm Home →
Disarm, and Arm → alarm → Disarm from HA — with the add-on on the ComIP. MQTT
showed Connection ON throughout; after trigger, alarm state returned to disarmed
from HA Disarm. Two modules can hold a login at once if they are different IPs;
one module still accepts one Connect login.

## Decision drivers

- Home arm then Disarm must not drop the HA panel link when HA is on the local module.
- A real alarm then Disarm from HA must keep that link and actually unset.
- The installer path (app, monitoring, talk-back) must remain on its own module.
- Wrong-host failures (HA pointed at the signalling module) stay explained, not
  redesigned as “all Connect is like that.”

## Options considered

- **Home Assistant uses the local ComIP; installer module stays for app/monitoring** —
  configure panel host as the dedicated LAN module.
- **Keep shipping as if every real alarm drops the HA link** — leave trigger-outage
  as the main product story. Rejected because: it fails the “link stays up and HA
  Disarm works on the local module” driver; SPIKE-010 showed that story is the
  signalling module, not the ComIP.
- **Slim trigger-only reconnect in this same decision** — drop the long post-alarm
  retry profile now. Rejected because: that is a separate trade-off about leftover
  defence if someone points HA at the SmartCom again; this ADR only chooses the
  host, not the reconnect schedule.

## Decision

Chosen option: **Home Assistant uses the local ComIP; installer module stays for app/monitoring**

SPIKE-010 supported the hypothesis that those failures were the SmartCom session,
not every Connect module. Pointing HA at the ComIP is the configuration that
matches the install and the live walks. Reconnect-when-dropped and frame resync
stay as general robustness (ADR-002), not as a reason to keep using the
signalling module.

## Consequences

**Positive:** HA can stay live through Home arm/disarm and through a real alarm
on this install when `panel_host` is the ComIP; HA Disarm during triggered is a
supported path in that setup. Two clients can run if they use the two different
module IPs.

**Negative:** Operators must pick the right IP; routers often label both poorly.
Pointing HA at the SmartCom will recreate the old lockout. This ADR does not
prove every Premier Elite layout has two modules.

**Follow-on:** A later ADR may narrow ADR-002’s long trigger reconnect budget.
Add a `Disposition:` field to SPIKE-009 — “HA Disarm during alarm is impossible”
is no longer the product answer when HA is on the ComIP; that spike’s run was
SmartCom. Do not treat ADR-001’s one-login-per-module rule as one-login-per-panel.

**CI vs live (when this decision is about an outside system / protocol):** FakePanel
may keep proving reconnect after a dropped socket and ordinary arm/disarm. It must
not claim a live alarm always drops the panel login, or that HA Disarm-from-triggered
fails. Survive-trigger and HA Disarm-during-alarm on a dedicated ComIP stay live-only
(`/accept` / this spike’s walks).

## Confirmation

Add-on `panel_host` is the ComIP, not the SmartCom used in SPIKE-002/009. Repeat
Walk A (Home arm → Disarm) and Walk B (arm → trigger → HA Disarm) with Connection
staying ON and Walk B actually unsetting from HA. CI stand-ins must not treat
those live ComIP outcomes as FakePanel facts.
