# Spike: startup-zone-state-read

**Resolves:** SPIKE-006 (no matching analysis.md entry — assigned next available number after spike-001/002/005)  
**Date:** 2026-08-04  
**Type:** Feasibility  
**State:** Validated ✅  

## Overview

**Question:** After login, can we ask the panel for each zone’s current open/closed state so a restart re-syncs entities instead of guessing?
**Answer:** Yes. After login the panel returns a full current-state snapshot for every zone slot in one read, with the same open/closed encoding used for live change events.
**Recommendation:** Use that startup snapshot read after login (before or alongside live event subscribe) so Home Assistant entities get correct initial state on every app start, then keep them updated from live pushes.
**Decisions this unlocks:**
- Whether production startup must poll current zone state (not wait for the next physical change)
- Whether that poll’s wire shape and status encoding become part of the protocol reference / implementation contract
- Whether FakePanel must speak the same snapshot read for CI

## Question

Does this panel expose a confirmed, safe read of current zone state after LOGIN (before or after event subscribe), and what are the exact request/response bytes?

## Hypothesis

We believe the panel will return each zone’s current open/closed state via a documented Connect-protocol read command after LOGIN (the same path today’s add-on uses on restart), because community reports say a restart re-reads zone state from the panel — so a live probe after login should ACK and return a decodable per-zone status payload we can map to active/secure.

## Research

- **This repo's protocol reference** (`docs/protocol-reference.md`) documents `GETZONEDETAILS` (cmd 3 — type/name only) and unsolicited ZONE events after `SETEVENTMESSAGES` (cmd 37). It does **not** list a current-state poll. SPIKE-001/002 confirm enumeration + push events; neither proves a startup snapshot read.
- **Open prior art** (`davidMbrooke/texecom-connect`) implements the same command set we already know and has **no** zone-state poll. Its `Zone.active` defaults false until a `MSG_ZONEEVENT` arrives — so that library does not solve the restart edge case.
- **Community / the prior MQTT bridge behaviour:** HA thread reports that restarting the add-on re-reads current zone state. Add-on logs (public GitHub issue #103) show an explicit step `Updating all zone states...` after `Fetched Zone N...` and before `Application ready`.
- **Published add-on image inspection (research only, not the experiment):** the distributed `a prior MQTT bridge` Docker image embeds JS that names `GetZoneState = 2`, builds request body `[startZone][zoneCount]` (1-byte zone numbers when panel zone count ≤ 256; 2-byte LE start when > 256), batches up to 168 zones per request, and parses each response byte with the same low-2-bit Secure/Active/Tamper/Short map used for ZONE push events (`parseZoneBitmap`). Adjacent enum values include write/omit commands (4/5/6/8/9) — the experiment must send **only** cmd 2.
- **Panel under test:** Elite 88 at `192.0.2.10:10001`, UDL `1234` (SPIKE-001); practitioner reports `the prior MQTT bridge` stopped so the single ComIP slot is free.

Research frames the candidate; live ACK + decodable payload against this panel is still required.

## Experiment Design

Throwaway `experiment.py` in this spike folder (same Connect framing style as SPIKE-001) was run as designed:

1. Connect to `TEXECOM_HOST`/`TEXECOM_PORT` (defaults `192.0.2.10:10001`), wait ≥500ms, `LOGIN` with `TEXECOM_UDL_PASSWORD` (default `1234`).
2. `GETPANELIDENTIFICATION` → parse zone count (expect 88).
3. Send **`GetZoneState` (cmd = 2)** with body `startZone=1`, `zoneCount=min(zone_count, 168)` using 1-byte zone numbering (Elite 88 ≤ 256). Print raw request/response hex, length, and ACK/NAK.
4. Decode each response byte’s low 2 bits as Secure/Active/Tamper/Short; print non-secure zones.
5. **Corroboration (optional env `TEXECOM_FLIP_ZONE`):** skipped in the recorded run (`TEXECOM_FLIP_ZONE` unset).
6. Never sent arm/disarm/omit/reset commands (6/8/4/5/9). Socket closed cleanly.

### Decision Criteria

| Criterion | Target | Actual |
|-----------|--------|--------|
| `GetZoneState` (cmd 2) after LOGIN is ACK'd | Response cmd echo = 2; no NAK; no timeout | **Met.** After LOGIN + GETPANELIDENTIFICATION, `TX cmd=2 body=0158` returned a response with no NAK/timeout (2026-08-04 15:15:14–15 run) |
| Response length matches requested zone count | Payload length == `zoneCount` bytes (after cmd echo) | **Met.** Requested count=88; `payload_len=88`; `TOTAL status bytes received: 88 (expected 88)` |
| Bitmap decode is coherent | Low 2 bits in {0,1,2,3}; majority Secure(0) on a quiet house | **Met.** Counts `{'secure': 87, 'active': 1}`; sole non-secure = zone 28 `active raw=0x01`; no out-of-range low bits |
| Optional physical corroboration | If `TEXECOM_FLIP_ZONE` set: queried zone shows Active then Secure across open/close | **Not run** — `TEXECOM_FLIP_ZONE` unset; recorded as skipped |

*Actuals are populated from experiment output only — not from documentation, vendor claims, or community reports.*

## Results

Raw output of `experiment.py` against `192.0.2.10:10001` (UDL default `1234`), 2026-08-04 15:15:13–15 UTC-adjacent local time:

```
[2026-08-04 15:15:13] SPIKE-006 GetZoneState probe
[2026-08-04 15:15:13] Target: 192.0.2.10:10001
[2026-08-04 15:15:14] TCP connected; waiting done; sending LOGIN
[2026-08-04 15:15:14] TX cmd=1 seq=0 attempt=0 body=31323334
[2026-08-04 15:15:14] LOGIN ACK
[2026-08-04 15:15:14] TX cmd=22 seq=1 attempt=0 body=(empty)
[2026-08-04 15:15:14] GETPANELIDENTIFICATION: b'Elite 88     ENG->SW V6.02.02LS1' → zone_count=88
[2026-08-04 15:15:14] TX cmd=2 seq=2 attempt=0 body=0158
[2026-08-04 15:15:15] GetZoneState start=1 count=88 payload_len=88 hex=00000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
[2026-08-04 15:15:15] GetZoneState summary start=1 len=88 counts={'secure': 87, 'active': 1}
[2026-08-04 15:15:15]   zone 28: active raw=0x01
[2026-08-04 15:15:15] TOTAL status bytes received: 88 (expected 88)
[2026-08-04 15:15:15] FLIP CORROBORATION: skipped (TEXECOM_FLIP_ZONE unset)
[2026-08-04 15:15:15] DONE
[2026-08-04 15:15:15] socket closed
```

Confirmed wire shape on this panel: request body `01 58` = start zone 1, count 88 (hex); response body is exactly 88 status bytes.

## Conclusion

**Hypothesis supported** — the panel accepts `GetZoneState` (cmd 2) after LOGIN and returns one status byte per requested zone. Length matched (`payload_len=88` for count 88). Bitmap decode matched the known Secure/Active encoding (`87` secure, `1` active at zone 28). Physical open/close flip was not exercised in this run, so Active↔Secure transition under deliberate operator action remains an open corroboration, not a blocker for adopting the poll itself.

## Options

### Option A: Adopt GetZoneState (cmd 2) for startup (and reconnect) zone snapshot

After LOGIN (and after zone enumeration for the in-use set), poll `GetZoneState` for the panel’s zone count (batched at ≤168 if needed), publish MQTT state for in-use zones, then `SETEVENTMESSAGES` for live updates. Pros: matches observed panel behaviour and today’s add-on; closes the restart edge case. Cons: one extra command family to implement in FakePanel/tests.

### Option B: Push-only — wait for ZONE events; no startup poll

Subscribe via `SETEVENTMESSAGES` and never snapshot. Pros: fewer commands. Cons: restart leaves entities wrong until something physically changes; violates `spec-zone-monitoring.md` restart edge case; refuted as sufficient by this spike’s product need (and by the prior MQTT bridge’s explicit update step).

### Option C: Retain last MQTT state across restarts only

Rely on retained MQTT payloads without a panel poll. Pros: no new protocol work. Cons: stale after physical changes while the app was down; does not read the panel; fails first-start / broker-empty cases.

## Recommendation

**Option A.** Criteria met for ACK, length, and coherent bitmap on the live Elite 88. Implement `GetZoneState` (cmd 2) with body `[startZone][zoneCount]` (1-byte start for panels ≤256 zones), response = `zoneCount` status bytes, low 2 bits Secure/Active/Tamper/Short — same map as ZONE push events. Call it at startup (and on reconnect after re-LOGIN) before relying on entity state. Document in `docs/protocol-reference.md`. Extend FakePanel for CI. Optional physical flip corroboration can be a follow-on test, not a gate on the ADR.

Assumptions: Elite 88 / this firmware path generalises to other Premier Elite Connect panels the same way SPIKE-001’s enumeration did; batching >168 zones was not exercised here (panel has 88).

## Decisions required

- Should production startup (and post-reconnect re-LOGIN) require a `GetZoneState` (cmd 2) snapshot before treating zone MQTT state as current?
- Should `docs/protocol-reference.md` record `GetZoneState` cmd 2 request/response framing and the shared Secure/Active bitmap with ZONE push events?
- Should FakePanel implement `GetZoneState` so DRAFT-1 / zone-state tasks can be verified in CI without the live panel?

## Open questions

- Physical open/close flip via `TEXECOM_FLIP_ZONE` was not run — worth a short follow-up probe to lock Active↔Secure under operator control, but not required to decide Option A.
- Panels with >256 zones (2-byte start zone) and batches >168 were not exercised on this Elite 88.
- Whether area-state startup poll (`GetAreaFlags` / similar, seen in add-on image research) is needed for alarm entity re-sync is out of scope for this spike (belongs with alarm-state drafts).
