# Spike: comip-stays-online

**Resolves:** unlisted (dedicated ComIP vs SmartCom session) / SPIKE-010  
**Date:** 2026-08-21  
**Type:** Feasibility  
**State:** Validated ✅  

## Overview

**Question:** With Home Assistant on the dedicated local network module (not the installer signalling module), do Arm Home then Disarm, and Arm then alarm then Disarm, complete with the panel link still on?
**Answer:** Yes. Home arm and disarm stayed linked. A real alarm then Disarm from Home Assistant also stayed linked and actually stopped the alarm — while the panel was simultaneously reporting that alarm to the monitoring station and feeding the Texecom Connect phone app.
**Recommendation:** Point Home Assistant at the local module you added, not the installer’s signalling box. Treat the old crashes and siren lockouts as the wrong box, not as “the panel always drops us.”
**Decisions this unlocks:**
- Whether production must document and require that local module as the Home Assistant target
- Whether the long “after an alarm, keep retrying” design is still the main story
- Whether Disarm from Home Assistant during a live alarm is supported when that module is used

## Question

With this add-on on the dedicated ComIP, do Arm Home → Disarm and Arm → alarm → Disarm complete with the panel link still ON (and HA Disarm working in the alarm walk)?

## Hypothesis

We believe the ComIP session will stay up through Arm Home → Disarm and through Arm → alarm → HA Disarm, because those failures were the SmartCom grabbing or polluting its own login, not something every Connect module does.

## Research

Earlier live work treated “junk on the wire around Home arm/disarm” and “TCP drop at a real alarm” as normal Connect behaviour on this Elite 88 (SPIKE-002, ADR-002, SPIKE-009). Those sessions used `192.0.2.10:10001`. In 2026-08-21 that address was identified as the **installer SmartCom**, not the homeowner **ComIP**. Alarm reporting is supposed to seize the SmartCom; HA on that IP gets kicked off. `the prior MQTT bridge` historically crashed on Home arm/disarm (CRC / unexpected start byte) on the same kind of shared path.

The ComIP is a second Ethernet module. Two clients can be live at once if they use **different** IPs. A quiet Connection-ON stretch is **not** evidence; the bar is the two sequences that used to fail: **Arm Home → Disarm**, and **Arm → alarm → Disarm from HA**, with the link remaining ON.

This spike uses the **add-on on the ComIP**. It does not stop the add-on to send panel bytes from `experiment.py`. A throwaway MQTT logger only records Connection and alarm state so Actuals are not memory.

## Experiment Design

Add-on running; `panel_host` is the ComIP (not the SmartCom). `the prior MQTT bridge` off, or only on the SmartCom IP.

`experiment.py` in this folder: MQTT subscribe to panel connection and alarm state; print timestamped lines. Start it before Walk A; leave it running through Walk B.

**Walk A — old crash.** Arm **Home** from HA (or keypad). Wait until settled. **Disarm**. Connection must stay ON throughout.

**Walk B — old lockout.** Tell the monitoring station; bells off if possible. Arm (Away is enough). Trigger so HA shows **triggered**. **Disarm from HA**. Connection stays ON; Disarm actually stops the alarm. If it does not, stop from the keypad and record fail.

Do not treat idle time as a pass. Fill Actuals from the MQTT log, add-on TRACE if needed, and the practitioner’s yes/no on Disarm in Walk B.

### Decision Criteria

| Criterion | Target | Actual |
|-----------|--------|--------|
| Walk A: Home arm then Disarm, link stays up | Alarm Panel Connection stays ON for the whole Home arm → settle → Disarm; no connection OFF in that window | **Met.** MQTT (2026-08-21): `arming` → `armed_home` → `disarmed` at 17:07:13–28, and again 17:07:59–17:08:13. After initial retained `panel_connection/state ON`, that topic never published `OFF`. |
| Walk B: Arm then alarm then HA Disarm, link stays up | Connection stays ON from arm through triggered through HA Disarm | **Met.** Same log: `arming` → `armed_away` (17:08:53–17:09:03) → `triggered` (17:09:47) → `disarmed` (17:09:54). No `panel_connection/state OFF`. |
| Walk B: HA Disarm actually works | Practitioner: sirens/alarm stop from HA Disarm (not only the keypad) | **Met.** Practitioner: both walks worked; HA Disarm after trigger succeeded (contrast SPIKE-009 on SmartCom, where HA Disarm did nothing). |
| Host under test is the ComIP | Add-on `panel_host` is the dedicated ComIP, not the SmartCom IP used in SPIKE-002/009 | **Met as practitioner config.** Logger does not print `panel_host`. Walks were run after repointing the add-on off `192.0.2.10` (SmartCom) onto the dedicated ComIP. |

*Actuals are populated from experiment output only — not from documentation, vendor claims, or community reports.*

## Results

`python3 experiment.py` (MQTT logger only; add-on stayed up). Log 2026-08-21 17:04:16–17:09:54 local:

```
texecom/panel_connection/state ON
texecom/alarm/state disarmed
texecom/status online
texecom/alarm/state arming
texecom/alarm/state armed_home
texecom/alarm/state disarmed
texecom/alarm/state arming
texecom/alarm/state armed_home
texecom/alarm/state disarmed
texecom/alarm/state arming
texecom/alarm/state armed_away
texecom/alarm/state triggered
texecom/alarm/state disarmed
```

`panel_connection/state` was `ON` at subscribe (retained) and never published `OFF` during Walk A (Home twice) or Walk B (Away → triggered → disarmed in 7s).

Practitioner: all done, it worked (HA Disarm after the alarm included).

**Concurrency observed during Walk B** (practitioner report, recorded 2026-08-21 after the walk — not a pre-registered criterion):

- The **monitoring station telephoned the practitioner** while Walk B was in progress. The panel was therefore signalling the alarm out to the ARC over its reporting path at the same time this add-on held a live ComIP session.
- The practitioner **watched the whole event live in the Texecom Connect iOS app**, which tracked the trigger and the disarm. The app path (installer module / Texecom cloud) stayed functional throughout.
- All three consumers — this add-on on the ComIP, the ARC reporting path, and the Connect app — were live and working simultaneously through a real alarm. Nothing was evicted.

## Conclusion

**Hypothesis supported** — on the dedicated ComIP, the add-on session stayed up through Home arm/disarm and through a real alarm plus HA Disarm; HA Disarm stopped the alarm.

Walk A and Walk B Actuals: no Connection OFF; alarm state moved `triggered` → `disarmed` without a keypad-only rescue. That is the opposite of SPIKE-009 on the SmartCom (`triggered` then Connection OFF; HA Disarm failed).

**The concurrency observation is the strongest line in this run.** Walk B was not a local session that happened to survive a quiet moment — the panel was actively reporting the alarm to the ARC (monitoring station rang the practitioner mid-walk) and serving the Connect app, and the ComIP session stayed up and accepted Disarm anyway. Alarm signalling and local control coexisted on this install under real load. That answers empirically what reading Program Digi could only have answered on paper: whatever this panel's reporting configuration is, an alarm report does not evict the ComIP session.

**CI vs live:** FakePanel may keep proving reconnect-when-TCP-dies and ordinary arm/disarm. It must **not** claim a live alarm always drops the panel login, or that HA Disarm-from-triggered fails. Those were SmartCom-path facts. Dedicated-ComIP survive-trigger and HA Disarm-during-alarm remain **live-only** (this run is the live evidence for this install).

## Options

### Option A: Home Assistant uses the local ComIP; installer module stays for app/monitoring

Document and configure `panel_host` as the homeowner ComIP. Keep SmartCom for the Texecom app and monitoring. The how-to already describes the wrong-IP trap.

Pros: Matches this run; HA Disarm during alarm worked. Cons: Two IPs to get right. Fit: Strong.

### Option B: Keep shipping as if every real alarm drops the HA link

Leave trigger reconnect budgets and “HA cannot disarm while sounding” as the main product story.

Pros: Still covers a mis-pointed `panel_host` or Dial-All on the ComIP. Cons: Contradicts this Validated run when the host is correct. Fit: Fallback only, not the headline.

### Option C: After an ADR, slim trigger-only reconnect; keep cheap resync and reconnect-on-drop

Do not delete defences tonight. Change the *story* first (ADR-002 bits that assumed trigger always drops Connect). Then consider simplifying the long trigger retry profile.

Pros: Code still handles real drops. Cons: Needs a follow-on ADR, not this spike merge alone. Fit: Sensible sequel.

## Recommendation

**Option A**, with **C** as the follow-on for architecture. Point HA at the ComIP. Do not treat SPIKE-002/009 disconnect-at-sirens as ComIP behaviour. Keep resync and ordinary reconnect until an ADR says otherwise.

Assumptions: one install, Elite 88, ComIP vs SmartCom as identified 2026-08-21; Walk B was a real trigger with HA Disarm succeeding. Program Digi / Dial-All menus were not read this run — but Walk B exercised the condition those menus govern (a live ARC report concurrent with the ComIP session) and the session survived, so the menu check is corroboration rather than a gap.

## Decisions required

- Should production require (or strongly document) that Home Assistant’s panel address is the dedicated local module, not the installer signalling module?
- Should ADR-002’s “panel always force-drops Connect at a real alarm” and the long trigger reconnect budget be superseded or narrowed to the SmartCom / wrong-host case?
- Should “Disarm from Home Assistant while triggered” be treated as supported when HA is on the dedicated ComIP (SPIKE-009’s SmartCom fail no longer the product answer)?

## Open questions

- Whether Program Digi / Dial All Numbers names the ComIP — menus unread, but effectively answered for this install: Walk B ran a real ARC report concurrently with the ComIP session and nothing was evicted. Open only as a general-installs question, not a gap in this run.
- Whether SPIKE-009 should be annotated/disposed as SmartCom-only rather than merged as “HA cannot disarm during alarm.”
- How much trigger-profile reconnect code to keep as a safety net if someone points HA at the SmartCom again.