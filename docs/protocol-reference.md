# Texecom Connect — protocol reference

> **Observational lookup — not an official Texecom specification.**  
> Human-oriented narrative and flow diagrams: [protocol overview](protocol-overview.md).  
> Legal position: [legal stance](legal-stance.md).

**Observed on:** Premier Elite (firmware example: `ENG->SW V6.02.02LS1`). Supported path is a dedicated **ComIP**. Captures that showed Hayes modem commands (`ATH0` / `ATZ`) and a trigger-time TCP drop were later identified as an installer **SmartCom**, not that ComIP.  
**Status:** Living map — incomplete by design. Gaps are gaps.

### Confidence legend

| Tag | Meaning |
|-----|---------|
| **Confirmed ✅** | Observed live on this panel (usually via a Validated spike) |
| **Hypothesis 🔬** | Consistent with live data; not fully settled |
| **Unconfirmed ⚠️** | Research / prior art only — do not ship behaviour on this alone |

---

## Framing

| Offset | Field | Notes | Confidence |
|---:|---|---|---|
| 0 | Start | Always `'t'` (`0x74`) | Confirmed ✅ |
| 1 | Type | `'C'` command, `'R'` response, `'M'` unsolicited | Confirmed ✅ |
| 2 | Length | Total length including header + CRC (`len(body) + 5`) | Confirmed ✅ |
| 3 | Sequence | 0–255; retries reuse the same sequence | Confirmed ✅ |
| 4…n−1 | Body | Command byte + args, or event payload | Confirmed ✅ |
| n | CRC-8 | `poly=0x185`, `init=0xff`, over header+body | Confirmed ✅ |

| Rule | Detail | Confidence |
|------|--------|------------|
| ACK / NAK | Response payload `0x06` / `0x15` | Confirmed ✅ |
| Login delay | ≥ ~500 ms after TCP connect before `LOGIN` | Unconfirmed ⚠️ minimum (prior art); practice works |
| Command timeout | ~2–3 s then retry **same sequence** | Confirmed ✅ |
| Forced disconnect text | Literal `+++` claimed elsewhere | Unconfirmed ⚠️ here (SPIKE-002 saw TCP close only) |

### Non-Connect serial probe

| | |
|--|--|
| Request | Raw `03 5A A2` (not a Connect frame) |
| Reply | Claimed digit string (short header + digits) |
| Confidence | **Unconfirmed ⚠️** on this panel |
| Product | Not required for zone `unique_id`s |

---

## Commands (app → panel)

| Cmd | Name | Body (this panel) | Confidence | Notes |
|---:|---|---|---|---|
| 1 | `LOGIN` | UDL password bytes | Confirmed ✅ | Factory default is often `1234`; use the password your installer set |
| 2 | `GETZONESTATE` | `[startZone][count]` (1-byte start if zones ≤256) | Confirmed ✅ | ≤168 zones/request; status bytes share ZONE push low-2-bit map (SPIKE-006 / ADR-006) |
| 3 | `GETZONEDETAILS` | zone number (1 byte) | Confirmed ✅ | Type + area bitmap + name |
| 6 | `SETAREAARM` | `[mode] 01` — `00` full arm (HA Away); `01`/`02`/`03` Part-Arm slots 1–3 | Confirmed ✅ | Shared command; HA Home/Night labels come from install config, not from the mode byte (ADR-008) |
| 8 | `SETAREADISARM` | `01` | Confirmed ✅ | Mode-independent; AREA `disarmed` push not uniform (esp. Home) |
| 9 | `SETAREARESET` | Same area-select shape as disarm (`01`) | Unconfirmed ⚠️ | Candidate before disarm when in alarm — **SPIKE-009** / RISK-018; do not ship yet |
| 11 | `GETAREAFLAGS` | `[start][count]` | Confirmed ✅ | Elite 88: `0, 72`, `area_size=1` (SPIKE-007 / ADR-009). Alternate split read when `area_size===8`: `0,30` then `50,3` — not used here |
| 13 | `GETLCDDISPLAY` | — | Unconfirmed ⚠️ | Not exercised |
| 14 | `SETLCDDISPLAY` | 32-char padded text | Unconfirmed ⚠️ | Seen in other clients |
| 15 | `GETLOGPOINTER` | — | Unconfirmed ⚠️ | Not exercised |
| 22 | `GETPANELIDENTIFICATION` | — | Confirmed ✅ | e.g. `Elite 88 … V6.02.02LS1` → 88 zones |
| 23 | `GETDATETIME` | — | Confirmed ✅ | Production idle keepalive (~15 s) |
| 24 | `SETDATETIME` | six numeric date/time bytes | Unconfirmed ⚠️ | Other clients |
| 25 | `GETSYSTEMPOWER` | — | Confirmed ✅ probe; decode **Hypothesis 🔬** | Example `b0b0ad5300`. Working decode: `[refV,sysV,batV,sysI,batI]`; `V≈13.7+(x−refV)×0.07`; `I≈byte×9` if &gt;0 — uncalibrated |
| 27 | `GETUSER` | — | Unconfirmed ⚠️ | Not exercised |
| 35 | `GETAREADETAILS` | area number (≥1) | Confirmed ✅ | Area **name/identity** only — not Part-Arm roles |
| 37 | `SETEVENTMESSAGES` | u16 LE bitmask | Confirmed ✅ | Subscribe Zone \| Area \| Log (etc.) |

**Part-Arm scoping:** mode bytes `01`/`02`/`03` are Part-Arm slots. Which slot is Home or Night is install-time configuration (ADR-008). Away is always full arm (`00`), never a Part-Arm slot.

---

## Unsolicited messages (`M` frames)

First body byte = subtype:

| Sub | Name | Payload (after subtype) | Confidence |
|---:|---|---|---|
| 1 | ZONE | zone # + bitmap | Confirmed ✅ |
| 2 | AREA | area # + state byte | Confirmed ✅ |
| 3 | OUTPUT | output # + state | Confirmed ✅ (shape); decode shallow |
| 4 | USER | keypad / user activity | Confirmed ✅ |
| 5 | LOG | type, group, … | Confirmed ✅ |

ZONE pushes are sensor-class agnostic (door/PIR/shock share framing).

### AREA state byte (0-indexed)

| Value | Meaning | Confidence |
|---:|---|---|
| 0 | disarmed | Confirmed ✅ |
| 1 | in exit | Confirmed ✅ |
| 2 | in entry | Unconfirmed ⚠️ live |
| 3 | armed (full) | Confirmed ✅ |
| 4 | part armed (transient?) | Hypothesis 🔬 |
| 5 | in alarm | Unconfirmed ⚠️ live as push value |
| 6 | settled Part-Arm slot 1 | Hypothesis 🔬 (strong) |
| 7 | settled Part-Arm slot 2 | Hypothesis 🔬 (strong) |

**Disarm → AREA `disarmed`:** observed after Away/Night network disarm; **not** reliably observed after Home on 2026-08-07–08 (ACK yes; nine-byte LOG-shaped discard while awaiting response — open whether omit vs collision).

### GetAreaFlags indices (Elite 88 decode)

One bit per flag index per area (area 1 = bit 0). Priority: Alarm → armed-family → PartArm slots → else disarmed.

| Index | Name | Role |
|---:|---|---|
| 0 | Alarm | → triggered |
| 21 | Armed | armed-family |
| 22 | FullArmed | full Away if no PartArm slot |
| 23 | PartArmed | part-armed family |
| 26 | ForceArmed | armed-family |
| 50–52 | PartArm1–3 | active slot (HA label from config) |

Exit/entry **not** from this snapshot — live AREA pushes.

| Layout | Reads | This Elite 88? |
|--------|-------|----------------|
| Single | `start=0, count=72` | **Yes** |
| Split | `0,30` then `50,3` | No |

### LOG types (selected)

| Type | Name | Confidence |
|---:|---|---|
| 27 | Alarm Active | Confirmed ✅ |
| 28 | Bell Active | Confirmed ✅ |
| 32 | Exit Started (`group=17` ≈ exit cancelled — Hypothesis 🔬) | Confirmed ✅ / Hypothesis 🔬 |
| 33 | Exit Error | Unconfirmed ⚠️ |
| 34 | Entry Started | Confirmed ✅ |
| 42 | Mode/action marker (disarm group 5; Away arm group 6) | Hypothesis 🔬 |
| 45 | Reset After Alarm | Unconfirmed ⚠️ (not seen post-trigger clear) |
| 53 | Remote-session / “download” style marker | Hypothesis 🔬 |
| 78–80 | Part Arm 1–3 | Mixed (79 Confirmed ✅ as Part-Arm 2) |
| 113 | Remote Command | Hypothesis 🔬 |
| 204–206 | Quick Part Arm 1–3 | Unconfirmed ⚠️ |
| 207–209 | Remote Part Arm 1–3 | 207/208 Confirmed ✅ live; 209 Unconfirmed ⚠️ |

**Arm-mode LOG signatures (Hypothesis 🔬):** Part-Arm 1 → 113/g9 then 207/g6; Part-Arm 2 → 113/g9 then 208/g6; Away → 42/g6; Disarm (Away / Part-Arm 1) → 42/g5. Group byte otherwise largely unmapped. HA Home/Night names for those slots are install config.

---

## Zone detail types (enumeration)

| Code | Meaning | On this panel? |
|---:|---|---|
| 0 | Unused | Yes |
| 1 | Entry/Exit 1 | Yes |
| 2 | Entry/Exit 2 | Yes |
| 3 | Interior | Yes |
| 4 | Perimeter | Yes |
| 8 | Silent PA | Yes |
| other | Prior-art table | Unconfirmed ⚠️ here |

---

## Behavioural constraints

| Quirk | Confidence | See |
|-------|------------|-----|
| Single TCP Connect client | Confirmed ✅ | SPIKE-001 |
| Idle hang ~60 s without keepalive | Confirmed ✅ | 2026-08-04 |
| Non-Connect junk → must resync (never fatal) | Confirmed ✅ | ADR-002 / ADR-014 |
| Hayes `ATH0`/`ATZ` on the HA socket | Confirmed ✅ **on SmartCom only** | SPIKE-002; wrong `panel_host`. Not seen on dedicated ComIP (SPIKE-010). |
| Trigger force-closes HA TCP; long recovery | Confirmed ✅ **on SmartCom only** | SPIKE-002 / SPIKE-009. Dedicated ComIP stayed up (SPIKE-010 / ADR-014). |
| Home disarm AREA path unreliable vs Night | Confirmed ✅ (reproduced) | 2026-08-07–08 |

---

## Open questions

- LOG types 1, 3, 31, 41 and group-byte map
- Cmd 9 before disarm-in-alarm — SPIKE-009 was SmartCom (session already dead). SPIKE-010 disarmed a live alarm on ComIP with ordinary disarm (cmd 8).
- Bound on post-trigger disruption window — SmartCom-path; not the expected ComIP path (ADR-014).
- Calibrate `GETSYSTEMPOWER` formula on this panel
- Serial probe `03 5A A2` live
- Home disarm: omitted AREA vs destroyed frame
- Part-Arm 3 settled AREA value (if slot used)

---

## Design alternatives (non-normative)

Other bridges’ **client policies** — not panel law, not ADRs:

| Topic | Alternate | This project |
|-------|-----------|--------------|
| Keepalive | `GETSYSTEMPOWER` ~30 s | `GETDATETIME` ~15 s |
| Bad CRC | Full reconnect | Resync (ADR-002) |
| Reconnect | Fixed ~10 s | Asymmetric budgets as wrong-host safety net (ADR-014) |
| Re-arm | Disarm then arm | Direct arm |
| In alarm | Cmd 9 then 8 | Cmd 8 (SPIKE-010 on ComIP) |
| MQTT death | Process exit | LWT + panel_link (ADR-004) |

---

## Evidence index

| Spike / work | Topic |
|--------------|--------|
| [SPIKE-001](spikes/spike-001-zone-enumeration/SPIKE.md) | Enumeration, single connection |
| [SPIKE-002](spikes/spike-002-arm-home-triggered-framing/SPIKE.md) | Collisions; Hayes modem + trigger drop **on SmartCom** (disposition: not universal ComIP) |
| [SPIKE-005](spikes/spike-005-arm-disarm-command-framing/SPIKE.md) | Arm/disarm bytes |
| [SPIKE-006](spikes/spike-006-startup-zone-state-read/SPIKE.md) | Zone snapshot |
| [SPIKE-007](spikes/spike-007-area-arm-state-startup-read/SPIKE.md) | Area flags snapshot |
| [SPIKE-009](spikes/spike-009-ha-disarm-after-alarm/SPIKE.md) | HA Disarm-during-alarm failed **on SmartCom** (superseded) |
| [SPIKE-010](spikes/spike-010-comip-stays-online/SPIKE.md) | Dedicated ComIP stays up; HA Disarm during alarm works |
| Live 2026-08-04 / 07–08 | Zones walk; Home vs Night disarm |

## How to update

Add live findings with panel/firmware, confidence tag, and spike link. Label Unconfirmed ⚠️ clearly. Never delete a Confirmed ✅ row to paper over a contradiction — record both and open a question.
