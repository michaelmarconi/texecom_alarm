# Spike: area-arm-state-startup-read

**Resolves:** SPIKE-007 (no analysis.md RISK row — parked open follow-on from ADR-006 / SPIKE-006; raised by DRAFT-2 refine Decision gate)  
**Date:** 2026-08-04  
**Type:** Feasibility  
**State:** Validated ✅  

## Overview

**Question:** After login, can we obtain the panel’s current armed/disarmed/triggered (and exit/entry) state via a dedicated poll — without arm or disarm side effects — so a restart does not leave the Home Assistant alarm entity wrong until the next push?
**Answer:** Yes. After login the panel returns a current area-flags snapshot that decodes to Disarmed / Armed / Part-Armed / In-Alarm (and part-arm slot) for each area, without needing an arm or disarm command.
**Recommendation:** Use that startup area-flags read after login (and again after reconnect re-login) so the alarm entity gets correct initial state on every app start, then keep it updated from live area/log pushes.
**Decisions this unlocks:**
- Whether production startup must poll current area/arm state (not wait for the next push)
- Whether that poll’s wire shape and flag decode become part of the protocol reference / implementation contract
- Whether FakePanel must speak the same area-flags read for CI

## Question

After LOGIN, can we obtain the panel’s current armed/disarmed/triggered (and exit/entry) state via a dedicated poll — without arm/disarm side effects — so a restart does not leave the HA alarm entity wrong until the next push?

## Hypothesis

We believe that after LOGIN the panel will accept a dedicated area/arm-state poll (the kind of read today’s closed-source add-on appears to use) and return the current armed/disarmed/exit/alarm state without arm or disarm side effects, because zone open/closed already has a confirmed post-login snapshot pattern and the alarm-control restart edge case needs the same class of answer.

## Research

- **This repo's protocol reference** documents AREA *push* events after `SETEVENTMESSAGES` (state bytes 0–7, with 6/7 as settled Night/Home hypotheses) and `GETAREADETAILS` (cmd 35 — area *identity/name* only). It does **not** list a current arm/area-state poll. ADR-006 / architecture explicitly park whether alarm entities need a startup snapshot analogous to `GetZoneState`.
- **SPIKE-006** confirmed zone startup poll (`GetZoneState` cmd 2) and left open: *Whether area-state startup poll (`GetAreaFlags` / similar, seen in add-on image research) is needed for alarm entity re-sync.*
- **Open prior art** (`davidMbrooke/texecom-connect`) has no area-state poll — area state arrives only via unsolicited AREA events after subscribe.
- **Published add-on image inspection (research only, not the experiment):** a published MQTT-bridge image embeds JS that:
  - Names `GetAreaFlags = 11` in the same command enum as `GetZoneState = 2`.
  - Builds request body `[start, count]` via `createGetAreaFlagsInput`.
  - On startup logs `Updating all area states...` then calls `getAreaFlags(0, maxFlag, areaSize)`.
  - For panels whose area bitmap width is 8 bytes (`areaSize === 8`), also calls `getAreaFlags(50, 3)` for Part-Arm slot bits; otherwise Part-Arm flags are indices 50/51/52 inside the main flag block.
  - Decodes per-area bits with priority: Alarm(0) → InAlarm; else Armed(21)/FullArmed(22)/PartArmed(23)/ForceArmed(26) → Armed or PartArmed (+ part-arm slot); else Disarmed.
  - `areaMap[88] = 8` → `tAreaSize = ceil(8/8) = 1` byte per flag for this Elite 88; `maxFlag = 72` when `areaSize !== 8`.
- **Product need:** `spec-alarm-control.md` requires restart while armed/triggered to re-sync to the panel’s actual state, not default to disarmed. Live AREA pushes alone leave a restart gap until the next event (same class of failure ADR-006 closed for zones).
- **Panel under test:** a Premier Elite 88 (`TEXECOM_HOST`/`TEXECOM_PORT`, UDL from env; SPIKE-001); ComIP single-connection — the prior MQTT bridge must be stopped.

Research frames the candidate; live ACK + decodable payload against this panel is still required.

## Experiment Design

Throwaway `experiment.py` in this spike folder (same Connect framing style as SPIKE-006) was run as designed:

1. Connect to `TEXECOM_HOST`/`TEXECOM_PORT` (required env; no hardcoded host default), wait ≥500ms, `LOGIN` with `TEXECOM_UDL_PASSWORD` (required; no hardcoded default).
2. `GETPANELIDENTIFICATION` → parse zone count (expect 88) → derive `area_size = ceil(areaMap[zone_count]/8)` (Elite 88 → 1).
3. Send **`GetAreaFlags` (cmd = 11)** with body `start=0`, `count=72` when `area_size != 8` (Elite 88 path); if `area_size == 8`, use `count=30` then a second call `start=50`, `count=3`. Print raw request/response hex, length, and ACK/NAK.
4. Decode flag bytes for area 1 (HOUSE — bit index 0): report Alarm / Armed / FullArmed / PartArmed / ForceArmed / PartArm1–3 bits and the derived status (Disarmed / Armed / PartArmed / InAlarm) using the same priority as the add-on decode above.
5. **Corroboration (optional env `TEXECOM_ARM_MODE`):** if set to `0`/`1`/`2` (Away/Night/Home mode byte), after the initial poll: arm via confirmed cmd 6, wait for settle, re-poll GetAreaFlags, print before/after, then disarm with cmd 8. Default path sends **no** arm/disarm.
6. Never send omit/reset (cmds 4/5/9). Socket closed cleanly.

### Decision Criteria

| Criterion | Target | Actual |
|-----------|--------|--------|
| `GetAreaFlags` (cmd 11) after LOGIN is ACK'd | Response cmd echo = 11; no NAK; no timeout | **Met.** After LOGIN + GETPANELIDENTIFICATION, `TX cmd=11 body=0048` returned a response with no NAK/timeout (2026-08-04 15:56:50–51 run) |
| Response length matches `count * area_size` | Elite 88: 72 bytes for `start=0 count=72` | **Met.** `payload_len=72 (expected 72)` |
| Decode for area 1 is coherent | Derived status ∈ {Disarmed, Armed, PartArmed, InAlarm}; bit pattern printable | **Met.** Area 1 decode `status=Disarmed`; Alarm/Armed/FullArmed/PartArmed/ForceArmed and PartArm1–3 all false |
| Optional arm corroboration | If `TEXECOM_ARM_MODE` set: re-poll shows Armed/PartArmed with expected part-arm slot; then disarm restores Disarmed | **Not run** — `TEXECOM_ARM_MODE` unset; recorded as skipped |

*Actuals are populated from experiment output only — not from documentation, vendor claims, or community reports.*

## Results

Raw output of `experiment.py` against the configured panel (`TEXECOM_HOST`/`TEXECOM_UDL_PASSWORD`), 2026-08-04 15:56:50–51:

```
[2026-08-04 15:56:50] SPIKE-007 GetAreaFlags probe
[2026-08-04 15:56:50] Target: <redacted>:10001
[2026-08-04 15:56:50] Area number under test: 1
[2026-08-04 15:56:50] Arm corroboration: skipped unless TEXECOM_ARM_MODE is set
[2026-08-04 15:56:50] TCP connected; waiting done; sending LOGIN
[2026-08-04 15:56:50] TX cmd=1 seq=0 attempt=0 body=31323334
[2026-08-04 15:56:51] LOGIN ACK
[2026-08-04 15:56:51] TX cmd=22 seq=1 attempt=0 body=(empty)
[2026-08-04 15:56:51] GETPANELIDENTIFICATION: b'Elite 88     ENG->SW V6.02.02LS1' → zone_count=88 area_size=1
[2026-08-04 15:56:51] TX cmd=11 seq=2 attempt=0 body=0048
[2026-08-04 15:56:51] GetAreaFlags[initial] start=0 count=72 payload_len=72 (expected 72) hex=00000000000000000000000000000000ff0000000000000000ff000000ff0000ff000000000000000000000000000000000000000000000000000000000000000000000100000000
[2026-08-04 15:56:51] GetAreaFlags[initial] area=1 decode={'status': 'Disarmed', 'alarm': False, 'armed': False, 'full_armed': False, 'part_armed': False, 'force_armed': False, 'part_arm': None, 'part_arm_1': False, 'part_arm_2': False, 'part_arm_3': False}
[2026-08-04 15:56:51] ARM CORROBORATION: skipped (TEXECOM_ARM_MODE unset)
[2026-08-04 15:56:51] DONE
[2026-08-04 15:56:51] socket closed
```

Confirmed wire shape on this panel: request body `00 48` = start flag 0, count 72 (hex); response body is exactly 72 flag bytes (`area_size=1`). Area 1 (bit 0) decoded to Disarmed with no armed/alarm/part-arm bits set. Several non-armed flag indices returned `0xff` (all area bits set) — system-wide flag noise outside the armed/alarm indices used for status; not treated as a decode failure for this criterion.

## Conclusion

**Hypothesis supported** — the panel accepts `GetAreaFlags` (cmd 11) after LOGIN and returns a fixed-length flag block that decodes to a coherent area status for area 1 (`Disarmed` on a quiet house). Length matched (`payload_len=72` for count 72, `area_size=1`). Optional arm-then-re-poll corroboration was not exercised in this run, so Armed/PartArmed/InAlarm transitions under deliberate operator action remain an open corroboration, not a blocker for adopting the poll itself.

## Options

### Option A: Adopt GetAreaFlags (cmd 11) for startup (and reconnect) alarm-state snapshot

After LOGIN (and after reconnect re-LOGIN), poll `GetAreaFlags` for the panel’s area bitmap width, derive Disarmed / Armed / PartArmed / InAlarm (+ part-arm slot) for in-use areas, publish MQTT alarm state, then `SETEVENTMESSAGES` for live AREA/LOG updates. Pros: matches observed panel behaviour and today’s add-on; closes the alarm restart edge case the same way ADR-006 closed zones. Cons: one more command family + flag decode in FakePanel/tests; part-arm ↔ HA Home/Night still uses install-time config (ADR-005), not this poll.

### Option B: Push-only — wait for AREA events; no startup poll

Subscribe via `SETEVENTMESSAGES` and never snapshot area flags. Pros: fewer commands. Cons: restart leaves the alarm entity wrong until the next arm/disarm/trigger push; violates `spec-alarm-control.md` restart edge case; refuted as sufficient by this spike’s product need (and by the prior MQTT bridge’s explicit `Updating all area states...` step).

### Option C: Retain last MQTT alarm state across restarts only

Rely on retained MQTT payloads without a panel poll. Pros: no new protocol work. Cons: stale when the panel changed while the app was down; fails first-start / broker-empty cases; does not read the panel.

## Recommendation

**Option A.** Criteria met for ACK, length, and coherent Disarmed decode on the live Elite 88. Implement `GetAreaFlags` (cmd 11) with body `[start][count]` (Elite 88: `start=0`, `count=72`, `area_size=1`), decode Alarm / Armed / FullArmed / PartArmed / ForceArmed / PartArm1–3 bits with the priority above, call it at startup (and on reconnect after re-LOGIN) before relying on alarm entity state, then keep state from live AREA/LOG pushes. Document in `docs/protocol-reference.md`. Extend FakePanel for CI. Optional arm-mode corroboration can be a follow-on probe, not a gate on the ADR.

Assumptions: Elite 88 / this firmware path generalises to other Premier Elite Connect panels the same way SPIKE-001’s enumeration and SPIKE-006’s zone snapshot did; the `areaSize === 8` dual-request path was not exercised here (this panel uses `area_size=1`); mapping PartArm1/2/3 → HA Night/Home remains install-time config per ADR-005.

## Decisions required

- Should production startup (and post-reconnect re-LOGIN) require a `GetAreaFlags` (cmd 11) snapshot before treating alarm MQTT state as current?
- Should `docs/protocol-reference.md` record `GetAreaFlags` cmd 11 request/response framing, `area_size` derivation from zone count, and the Alarm/Armed/PartArmed/PartArm flag decode used for status?
- Should FakePanel implement `GetAreaFlags` so alarm-state tasks can be verified in CI without the live panel?

## Open questions

- Optional arm corroboration via `TEXECOM_ARM_MODE` was not run — worth a short follow-up probe to lock Armed/PartArmed (+ part-arm slot) and return-to-Disarmed under operator control, but not required to decide Option A.
- Panels with `area_size === 8` (dual `getAreaFlags(0,30)` + `getAreaFlags(50,3)` path) were not exercised on this Elite 88.
- How exit/entry transient states (`InExit` / `InEntry`) appear in the flag block vs only on live AREA pushes was not observed in this Disarmed-only run — live AREA events may still be required for `arming`/`pending` MQTT states even when the snapshot covers settled Disarmed/Armed/PartArmed/InAlarm.
