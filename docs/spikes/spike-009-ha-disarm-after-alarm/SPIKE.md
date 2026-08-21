# Spike: ha-disarm-after-alarm

**Resolves:** RISK-018 / SPIKE-009  
**Date:** 2026-08-19  
**Type:** Feasibility  
**State:** Validated ✅  
**Disposition:** Superseded (2026-08-21) — this run was on the installer SmartCom. ADR-013 / SPIKE-010 show the dedicated ComIP stays up and HA Disarm during alarm works. Do not write a product ADR from this spike’s “HA cannot stop a sounding alarm” recommendation.  

## Overview

**Question:** When the alarm is already going off, does tapping Disarm in Home Assistant actually stop it?
**Answer:** No. Home Assistant showed triggered; Disarm did nothing; the keypad had to unset and reset the panel. The add-on had already lost the panel link, which is usual right after a real alarm.
**Recommendation:** Do not treat Home Assistant Disarm as a way to stop a sounding alarm. Use the keypad or the vendor app. Do not add a separate Reset command until a run actually reaches the panel while it is in alarm.
**Decisions this unlocks:**
- Whether production should promise that Disarm from Home Assistant works during a live alarm
- Whether to queue or hide Disarm while the panel link is down after a trigger
- Whether a separate Reset belongs in the product (still untested on the wire)

## Question

When the alarm is already going off, does tapping Disarm in Home Assistant actually stop it?

## Hypothesis

We believe tapping Disarm in Home Assistant after a real alarm will stop the panel because the same Disarm command already works from ordinary armed states — a separate Reset is not required unless Disarm is refused.

## Research

The household already stops a real alarm with the keypad or the Texecom app. The only open product question is whether **Disarm in Home Assistant** would also stop it.

What we already know from earlier live work:

- Ordinary Disarm (not during an alarm) is confirmed: one Disarm command, same for every arm mode (SPIKE-005). Home Assistant sends that same command today.
- A real trigger often **drops the panel network link** and takes tens of seconds to come back (SPIKE-002). Any test of Disarm-after-alarm must reconnect first; a failed Disarm on a dead link would not answer the question.
- Command 9 (“Reset”) appears in another client’s command list. It has **never** been sent or captured on this panel. It is out of this experiment unless Disarm itself is refused.
- After one live trigger, disarming at the keypad left an on-panel reminder that an alarm had happened. That reminder is not the goal here.

A throwaway `experiment.py` in this folder can send those Disarm bytes itself, but **that requires stopping the add-on**. Product accept needs the add-on **running**. Those two live runs would mean **two siren events**. Do not do that.

**Chosen live path:** one sounding alarm with the add-on up. Disarm from Home Assistant. `experiment.py` is fallback only if we ever need a panel login without Home Assistant.

## Experiment Design

One live siren. Add-on running. No `experiment.py` unless the HA path is impossible.

Quiet work (zones, arm/disarm each mode, phone app) happens **first**, with no sirens. Then:

1. Add-on running; the prior MQTT bridge not running.
2. Arm from Home Assistant (one mode is enough for the siren).
3. Open a zone so the alarm actually sounds. Do not enter a code yet.
4. Watch Home Assistant: alarm shows triggered; connection goes off if the panel drops the link; last-trigger snapshot present; add-on still running; alarm entity not blanked.
5. When the link is back (or if it never dropped), tap **Disarm in Home Assistant**.
6. You: did the sirens stop? If not, stop them from the keypad or Texecom app (the proven way) and record that HA Disarm failed.
7. Fill this spike’s Actuals from that same event. The same notes feed `/accept` (survive trigger, connection signal, snapshot, Disarm from triggered).

Do not send Reset. Do not run a second trigger for this spike.

### Decision Criteria

| Criterion | Target | Actual |
|-----------|--------|--------|
| Alarm was actually going off before Disarm | Panel in alarm (AREA in-alarm and/or flags InAlarm) after trigger, before Disarm | **Met.** MQTT `texecom/alarm/state` went `arming` → `armed_away` → `triggered` (2026-08-21). Practitioner saw triggered in Home Assistant; sirens running. |
| Disarm was accepted or refused | ACK, NAK, or timeout, printed in the summary | **Not a clean ACK.** First HA Disarm at 13:50:15 while state was `triggered`: `panel_set_area_disarm` then ForcedDisconnect (session ended 13:50:17). Later taps: “Not connected… cannot send commands” (13:50:22) and SETAREADISARM timeout (13:50:31). No panel NAK that meant “need Reset first.” |
| Sirens stopped after Disarm | You answer **yes** (stopped) or **no** (still sounding) | **No.** Practitioner: Disarm clicked several times did nothing; had to disarm and reset at the panel. |
| Panel no longer in alarm after Disarm | Flags after Disarm are not InAlarm (Disarmed or ordinary Armed) | **Not via HA.** MQTT still `triggered` with Connection OFF while the add-on was on the trigger reconnect profile (attempts 1–15+ LOGIN timeout / socket close). Panel was cleared only at the keypad. |

*Actuals are populated from experiment output only — not from documentation, vendor claims, or community reports.*

## Results

Live run 2026-08-21, add-on `local_texecom_alarm` running (TRACE). `experiment.py` not used. the prior MQTT bridge stopped first.

MQTT (`/tmp/spike-009/mqtt.log`):

```
texecom/status online
texecom/panel_connection/state ON
texecom/alarm/state disarmed
texecom/alarm/state arming
texecom/alarm/state armed_away
texecom/alarm/state triggered
texecom/panel_connection/state OFF
```

Add-on log (container `app_local_texecom_alarm`):

- 13:48:44 reconnect succeeded (normal); alarm disarmed; listen started.
- 13:49:34 `alarm_command_arm` / `panel_set_area_arm_ok` (Away).
- 13:50:15 `alarm_command_disarm` / `panel_set_area_disarm`.
- 13:50:17 session ended (forced disconnect); last alarm state **triggered**; reconnect on **trigger** profile. MQTT command handler: unexpected failure on `texecom/alarm/command`.
- 13:50:22 second Disarm: “Not connected to the panel — cannot send commands.” Trust: Connection OFF (`disarm_nak`).
- 13:50:26–31 third Disarm: SETAREADISARM **timeout**. Trust: Connection OFF (`disarm_timeout`).
- 13:50:27 onward: trigger-profile reconnect attempts failing (LOGIN timeout / socket closed). Still failing at 13:52:37 (attempt 15).

Practitioner: HA showed triggered; Disarm clicked several times did nothing; **disarm and reset at the panel** required to stop it.

After the walk, MQTT still `alarm/state=triggered`, `panel_connection/state=OFF` (add-on not yet logged in again).

## Conclusion

**Hypothesis refuted** — tapping Disarm in Home Assistant did not stop a sounding alarm.

- Alarm was really going off (MQTT `triggered`; practitioner).
- Connection went OFF at trigger time (same class of forced disconnect as SPIKE-002).
- Disarm did not ACK. First tap died on a dropped socket; later taps were not-connected or timed out. Sirens kept going until the keypad.

This run does **not** prove the panel would NAK Disarm for “need Reset first.” We never got a calm in-alarm session to send Disarm into. The keypad still needed a reset after unset — that is panel UI, not a captured Reset command.

**CI vs live:** FakePanel may keep proving ordinary Disarm while a session is logged in, and that a trigger can force-disconnect and leave MQTT `triggered` with Connection OFF. It must **not** claim that Home Assistant Disarm stops live sirens, or that a Reset command is required or sufficient. Those remain live-only. This Validated run is the live evidence that the HA button did not stop the alarm during the outage.

## Options

### Option A: Keypad/app stop a live alarm; HA Disarm is not that path

Document and ship: after a real trigger, stop the alarm at the keypad or Texecom app. Home Assistant may show triggered and Connection off; Disarm there is not reliable until the panel accepts a login again.

Pros: Matches this run and how the house already stops alarms. Cons: HA Disarm looks like it should work and does not. Fit: Strong.

### Option B: Retry the last Disarm after reconnect

When login succeeds after a trigger, automatically re-send a Disarm the user tapped while offline.

Pros: Might unset once ComIP is back. Cons: Heal policy already left in-tap auto-retry out of scope (ADR-011). Could unset later than the user meant. Did not test Reset. Fit: Needs an explicit product decision, not inferred from this spike.

### Option C: Send Reset as well as Disarm

Once back online (or instead of Disarm), send the unused Reset command because the keypad needed a reset.

Pros: Matches keypad story. Cons: Never sent or ACKed on this panel; this run never had a live session in alarm. Fit: Do not wire from this spike alone.

### Option D: Do not offer Disarm while Connection is off

Grey out or reject Disarm in HA/MQTT while Connection is OFF so taps are not silent no-ops.

Pros: Honest UI. Cons: MQTT alarm panel may still show the button; HA MQTT discovery may not hide it easily. Fit: Optional UX, not required to answer the unknown.

## Recommendation

**Option A.** Home Assistant Disarm did not stop the alarm. Keep a single Disarm for ordinary unset. Do not add Reset from this run. Do not claim the HA button works during a live trigger.

Assumptions: one trigger on this Elite 88; ComIP dropped as in SPIKE-002; practitioner cleared the panel at the keypad. A later run that Disarms **after** Connection is ON again, while sirens still run, could still test “panel refuses Disarm until Reset” — that is a different experiment, not this one.

## Decisions required

- Should the product treat “Disarm from Home Assistant during a live alarm” as unsupported, with the keypad or vendor app as the stop path?
- Should Disarm tapped while Connection is OFF be queued until reconnect, rejected clearly, or left as today’s silent failure?
- Should a Reset command be added to the app? (Not evidenced on the wire here; keypad reset is not the same as a captured command.)

## Open questions

- After Connection is ON again and sirens are still going, does Disarm then ACK and unset, or does the panel refuse until Reset?
- How long the trigger reconnect window lasted after keypad reset (this capture stopped while LOGIN was still failing).
- Whether HA’s alarm entity should leave `triggered` only after a successful panel snapshot post-reconnect (it was still `triggered` / Connection OFF at 13:52).

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-19 | Design: Ready to run | — |
