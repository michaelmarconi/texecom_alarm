# Texecom Connect Protocol Reference

> **Observational — not an official Texecom specification.**  
> This document records what was **seen on the wire** and in panel responses while probing a
> household Premier Elite installation for Home Assistant interoperability. It was **not**
> derived from Texecom’s confidential protocol manuals, NDA packs, or other official materials,
> and it is **not** endorsed by Texecom.  
> Facts taken from public prior art (open-source clients, community reports) are cited and marked
> when not yet independently confirmed on this panel.  
> Full project position: [Legal stance — protocol interoperability](legal-stance.md).

**Status:** Living document — updated whenever a spike, experiment, or implementation work discovers
something new about the wire protocol. Do not treat this as complete or final; treat gaps as gaps,
not as "not applicable."

**Panel under test:** Texecom Elite 88, firmware `ENG->SW V6.02.02LS1`, via a ComIP network module.
Findings here are empirical (captured live against this panel) unless explicitly marked otherwise.
Behaviour may differ on other panel models/firmware.

**Sources so far:**
- [SPIKE-001](spikes/spike-001-zone-enumeration/SPIKE.md) — zone enumeration
- [SPIKE-002](spikes/spike-002-arm-home-triggered-framing/SPIKE.md) — arm_home / triggered-event framing and the collision crash
- [SPIKE-005](spikes/spike-005-arm-disarm-command-framing/SPIKE.md) — send-side arm/disarm command framing
- Live panel probes 2026-08-04 — `GETAREADETAILS`, multi-class ZONE event mission (door / window contact / shock / sliding door / garage), idle-session behaviour
- Live panel observations 2026-08-07–08 — Part-Arm Night vs Home disarm follow-up (AREA delivery, mid-command frame resync, OUTPUT/LOG accompaniment) against the production Connect client
- `davidMbrooke/texecom-connect` (`texecomConnect.py`, MIT/Apache-2.0) — public prior-art source inspection, cited where it informed a finding (not Texecom confidential docs)
- Community report: HA forum thread on panel/MQTT bridging, user Ben.S, 2020 — cited where it corroborates a finding

## Framing

Every message (command, response, or unsolicited) uses the same 4-byte header + body + CRC structure:

| Offset | Field | Notes |
|---|---|---|
| 0 | Start byte | Always `'t'` (`0x74`) |
| 1 | Type byte | `'C'` command, `'R'` response, `'M'` unsolicited message |
| 2 | Length byte | Total message length including header and CRC (`len(body) + 5`) |
| 3 | Sequence number | Rolls over; retries of the same command reuse the same sequence number |
| 4..n-1 | Body | Command byte + args (commands), or event payload (unsolicited messages) |
| n | CRC-8 | `poly=0x185, rev=False, initCrc=0xff`, computed over header+body |

- `LOGIN` (command byte `1`) must be sent **at least ~500ms after the TCP connection opens**, or the
  panel ignores it (source: forum post cited in `davidMbrooke/texecom-connect`'s comments; not yet
  independently stress-tested for the exact minimum).
- The panel ACKs a command with `0x06`, NAKs with `0x15`.
- A command that gets no response within ~2-3s should be **resent with the same sequence number**
  (confirmed by source-level comments in prior art; SPIKE-002 validated this recovers cleanly from
  ordinary same-protocol timing collisions).

### Forced-disconnect signal

The panel can also send a literal `+++` over the socket as a forced-disconnect signal, distinct from
a plain TCP close. Never independently observed to date (SPIKE-002 only ever saw an outright
`socket closed by peer`, not `+++`) — treat both as "the panel has ended this session" until an actual
`+++` capture confirms whether it behaves differently.

## Protocol-format collisions (read this before writing any client) — the real crash mechanism

**This is not a timing problem.** Ordinary command/response vs. unsolicited-message collisions on the
same socket are benign — a missed response just times out and retries. The actual, dominant crash
mechanism (confirmed in [SPIKE-002](spikes/spike-002-arm-home-triggered-framing/SPIKE.md)) is that the
panel's own SmartCom/ComIP hardware **multiplexes a second, non-Connect-protocol byte stream onto the
same TCP session**, specifically around arm/disarm/trigger events — and this happens on ordinary
keypad use alone, not just via the Texecom Connect mobile app. Confirmed contents seen so far:
literal Hayes/Hayes-compatible AT modem commands (`ATH0\r`, `ATZ\r`) from the module's own
dialer/reporting subsystem, plus at least one burst of unidentified higher-entropy binary data.

**Any client must scan forward for the next valid frame header instead of treating an unexpected
byte as fatal.** A client that assumes every byte on the socket is Connect-protocol will throw a
framing/CRC error and, unless built to recover, crash — this is the exact symptom that has crashed
both this project's own throwaway client and, independently, `the prior MQTT bridge` on different hardware
four years earlier (`CRC is invalid`, `Unexpected start, expected 't'`).

A real alarm trigger additionally causes the panel to **forcibly close the TCP connection**
(confirmed — this had only been an unverified claim in prior art before SPIKE-002), and the recovery
window afterward is measured in tens of seconds to at least a minute — much longer than the near-
instant recovery seen around an ordinary arm/disarm. See ADR-002 for the resulting client design
requirement (resync + asymmetric reconnect budget).

## Commands (client → panel)

Only commands actually confirmed safe/working against the live panel or directly sourced from
prior-art inspection are listed. **Send-side Arm Away, Arm Night, Arm Home, and Disarm are all
confirmed (SPIKE-005)** — see the notes below the table.

| Byte | Name | Body | Notes |
|---|---|---|---|
| 1 | `LOGIN` | UDL password | Panel ACK/NAK. This panel's password is the factory default `1234`, not blank (SPIKE-001). |
| 3 | `GETZONEDETAILS` | zone number (1 byte) | Returns zone type + area bitmap + name/text. 34/35/41-byte response depending on firmware. |
| 6 | `SETAREAARM` *(provisional name)* | `[mode] 01` — mode byte `00`=Away (×2), `01`=Night (×3), `02`=Home (×1) | **Confirmed shared "set arm mode" command, all three modes (SPIKE-005).** Same command byte for all three, differing only in the body's first byte. Home's mode byte (`02`) was determined by testing the natural next value in the sequence directly against the live panel — not blind guesswork: the command structure itself was already proven safe (used identically for Away/Night), only the untested mode-byte value was in question, and the result was independently corroborated three ways before being treated as confirmed: a clean ACK, an event sequence (`in exit` → `part armed` → settled at AREA state `7`) matching SPIKE-002's own independent prior observation of a keypad-driven Home arm, and direct visual confirmation via the household's Texecom Connect app ("part-armed to Home"). Disarmed immediately after with the same `cmd=8, body=01` used for the other modes. |
| 8 | `SETAREADISARM` *(provisional name)* | `01` — identical across all observations (Away, Night, and Home) | **Confirmed live (SPIKE-005), reproduced multiple times, mode-independent.** Same command disarms a fully-armed panel, cancels in-progress exit, and disarms Part-Arm Night or Home. ACK'd (`0x06`) every time. **AREA `disarmed` after ACK is not uniform by prior mode** — see AREA section (Night/Away observed; Home unsettled on the event path as of 2026-08-07–08). |
| 13 | `GETLCDDISPLAY` | — | Not yet exercised against this panel. |
| 15 | `GETLOGPOINTER` | — | Not yet exercised against this panel. |
| 22 | `GETPANELIDENTIFICATION` | — | Returns a 32-byte string: panel type, zone count, unknown field, firmware version. This panel: `'Elite 88     ENG->SW V6.02.02LS1'` → 88 zones. |
| 23 | `GETDATETIME` | — | Used as a safe idle/keepalive probe in SPIKE-002 and again 2026-08-04; read-only. A ~15s cadence kept a subscribed session alive for minutes; without it the panel closed the socket after ~1 minute of passive listen-only. |
| 25 | `GETSYSTEMPOWER` | — | Confirmed live (SPIKE-005 dry run) — `the prior MQTT bridge` uses this as its own idle/keepalive probe (this project's own client instead uses `GETDATETIME` for the same purpose, per SPIKE-002). Response body not yet decoded field-by-field (raw example: `b0b0ad5300`). |
| 27 | `GETUSER` | — | Not yet exercised against this panel. |
| 35 | `GETAREADETAILS` | area number (1 byte; `0` NAK'd) | **Exercised live 2026-08-04.** Area `1` returns name `HOUSE` plus trailing timer-ish bytes; areas `2`–`4` return `Not used B`/`C`/`D`. This is **area** identity, not Part-Arm slot role/name — it does **not** expose which engineer-configured Part-Arm slot is Night vs Home. Empty body and area `0` both NAK (`0x15`). |
| 37 | `SETEVENTMESSAGES` | 2-byte bitmask: `DEBUG \| ZONE_EVENT \| AREA_EVENT \| OUTPUT_EVENT \| USER_EVENT \| LOG_FLAG` | Subscribes the session to unsolicited `'M'`-type push messages. Confirmed safe and working. |

**Send-side Arm Away, Arm Night, Arm Home, and Disarm — all confirmed.**
`the prior MQTT bridge`'s own real traffic (captured passively, per SPIKE-005 — not guessed against the live
panel) shows command byte `6` issuing an arm, with the mode encoded in the body's first byte
(`00`=Away, confirmed ×2; `01`=Night, confirmed ×3), and command byte `8` (body `01`) issuing a
Disarm regardless of mode, confirmed across both Away and Night, including cancel-during-exit cases.
Home's mode byte (`02`) was the one value `the prior MQTT bridge` could never produce (it doesn't support Home)
— rather than leaving this open pending the still-blocked app/Local-Connection route, it was tested
directly: the command structure was already proven safe from the Away/Night observations, so only the
untested mode-byte value was actually in question. Sending it produced a clean ACK, the expected
`in exit` → `part armed` → settled-at-`7` event sequence (matching SPIKE-002's independent prior
observation of a keypad-driven Home arm), and was independently confirmed via the household's Texecom
Connect app showing "part-armed to Home" before disarming. All four actions now comfortably clear this
project's reproduce-twice bar (Home's single observation is corroborated three independent ways
instead, in lieu of a second identical test) and **RISK-001's send-side gap is fully closed.**

**Important scoping note (raised 2026-08-04, see the brief/spec correction that followed):** these
exact byte values (which physical Part-Arm slot is Night vs. Home) are specific to *this household's*
panel configuration — Part-Arm slots are engineer-configured per installation, and a different Premier
Elite panel could have Night and Home assigned to different slots, or a third slot in active use where
this one has none. The wire-level *mechanism* (one shared arm command, mode encoded in the body's
first byte, disarm is mode-independent) generalizes; the specific mode-byte-to-HA-mode mapping does
not, and must be sourced from per-installation configuration, not hardcoded from this spike's findings.

## Unsolicited messages (panel → client, after `SETEVENTMESSAGES`)

All arrive as `'M'`-type frames. First payload byte is a sub-type:

| Sub-type | Meaning | Payload (after sub-type byte) |
|---|---|---|
| `0x01` | ZONE event | zone number, state bitmap (`0x01` active / `0x00` secure, other bits seen: `0x10`, `0x40` — meaning not yet decoded) |
| `0x02` | AREA event | area number, state byte (see AREA state table below) |
| `0x03` | OUTPUT event | output/relay number + state — bookkeeping only, not yet decoded in detail |
| `0x04` | USER event | fires on every keypad code entry (arm, disarm, or clearing an alarm-memory indicator) — does **not** by itself distinguish which action occurred |
| `0x05` | LOG event | event type byte + group byte + timestamp-ish trailing bytes (see LOG event table below) |

**ZONE events are sensor-class-agnostic (confirmed 2026-08-04).** The same framing carries
door contacts, window contacts, shock sensors, sliding-door contacts, ordinary PIRs, and the
garage mirror sensor — each is just a zone number + active/secure bit. A live walk-around mission
observed clean open→close pairs for an Entry/Exit door, a kitchen sliding door, two window
contacts, repeated shock activations on the co-located window shocks, and the garage mirror PIR,
with no distinct payload shape per physical sensor class. Mapping zone → HA device class therefore
comes from `GETZONEDETAILS` / naming conventions at discovery time, not from the live event wire
format.

### AREA event states

**Reconciled (SPIKE-005):** the ambiguity flagged below between a 0-indexed and 1-indexed state byte
is now resolved in favour of **0-indexed**, based on two live captures agreeing with each other. A
SPIKE-005 capture of a full Arm Away → Disarm cycle showed, unambiguously, state byte `00` firing
exactly at disarm and state byte `01` firing exactly at the exit-delay start of the same cycle — both
clearly distinct, both consistent with SPIKE-002's own `raw=020101` = "in exit" reading. The table
below (sourced from prior art, 1-indexed) does not match this panel/firmware; treat the 0-indexed
scheme as the empirically-confirmed one going forward.

| Value | State | Confirmed live? |
|---|---|---|
| 0 | `disarmed` | Yes (SPIKE-005) |
| 1 | `in exit` | Yes (SPIKE-002, SPIKE-005) |
| 2 | `in entry` | No — prior-art numbering only, not yet independently observed |
| 3 | `armed` (full) | Yes (SPIKE-005) |
| 4 | `part armed` | No — prior-art numbering only, not yet independently observed |
| 5 | `in alarm` | No — prior-art numbering only, not yet independently observed |
| 6 | unknown — observed (SPIKE-005) as the settled resting state immediately after every completed Night `part armed` transition, both completed Night-arm cycles | Yes (SPIKE-005) |
| 7 | unknown — observed immediately after every `part armed` transition in both SPIKE-002 arm cycles (`arm_home`) and again after SPIKE-005's directly-tested Home arm | Yes (SPIKE-002, SPIKE-005) |

**Working hypothesis for 6 vs 7 (strengthened, still not fully confirmed):** both appear only as a
settled state immediately following a transient `part armed` (value `4`), and each is specific to a
different part-arm submode — `6` for Night (Part Arm 1), `7` for Home (Part Arm 2), now observed in
two independent SPIKE-005 sessions plus SPIKE-002. If this holds, value `4` is a brief mid-transition
state and `6`/`7`/etc. are the actual per-submode "settled" states, one per configured Part Arm slot.
Untested: whether a hypothetical Part Arm 3 slot would settle at `8`, and whether this numbering is
fixed or configuration-dependent (see the scoping note above — Part Arm slot assignment itself is
known to be configuration-dependent, so this numbering should not be assumed universal either).

**Disarm and AREA `disarmed` — mode-dependent on this panel.**

`SETAREADISARM` (`cmd=8`, body `01`) is mode-independent: the same bytes disarm from Away,
Night, or Home and cancel an in-progress exit. The panel ACK (`0x06`) confirms command
acceptance; it does **not** carry the resulting arm state. Clients that publish HA alarm
state from AREA pushes (or from `GetAreaFlags`) must still observe a subsequent state source.

| Prior mode | AREA `disarmed` (`raw=020100` / equivalent) after network `SETAREADISARM` | Notes |
|---|---|---|
| Away (full arm) | Observed (SPIKE-005, `the prior MQTT bridge` captures) | |
| Night (Part-Arm 1, mode byte `01`) | Observed (SPIKE-005; reproduced 2026-08-08 on the production client) | Intact AREA handled on the event path; MQTT alarm state advances to `disarmed`. |
| Home (Part-Arm 2, mode byte `02`) | **Not observed** on the application event path across multiple reproduced 2026-08-07–08 cycles | Command still ACK'd. Settled Home remains visible until a later `GetAreaFlags` snapshot (e.g. after reconnect). |
| Keypad-originated disarm | Often no distinct AREA (SPIKE-002) | USER/LOG accompaniment only in those captures. |

**Home (Part-Arm 2) disarm framing disruption (2026-08-07–08, reproduced):** while awaiting the
`SETAREADISARM` response after a settled Home arm, the TCP stream repeatedly presents **nine
non-frame bytes** that a CRC/start-byte resync must discard before the next valid Connect frame.
Captured discarded payloads share the lead-in `03 08 25 01` and trailing timestamp bytes with the
intact `LOG` type=`3` / group=`8` burst that follows the ACK — i.e. **Connect LOG-body-shaped
debris**, not Hayes/AT modem text (`ATH0` / `ATZ`). Across those same Home cycles, no AREA
`disarmed` event reached the application message handler. Equivalent Night→disarm cycles on the
same client and panel **did not** exhibit that nine-byte discard and **did** deliver AREA
`disarmed` (plus LOG type=`42` group=`5`, matching the SPIKE-005 disarm signature).

**Interpretation (open):** the send-side command for Home disarm is not wrong. Either (a) this
panel/firmware omits or corrupts the AREA `disarmed` push specifically after Part-Arm 2 / Home, or
(b) a Home-specific post-disarm collision destroys that frame before a correct decode. The
correlation with the nine-byte LOG-shaped discard favours (b) or a panel-side multiplex fault
concentrated on the Home path; it is **not** yet proven which. Historical note: `the prior MQTT bridge`
never implemented Home arm, so its reliable AREA-on-disarm captures (Away/Night) do not contradict
a Home-only defect.

**OUTPUT events** (`0x03`) accompany both arm-settle and disarm for Night and Home alike
(output/relay bookkeeping). They are not a substitute for AREA arm-state.

### LOG event types

Confirmed against this panel (via live capture) unless marked "prior art only":

| Type | Name | Status |
|---|---|---|
| 27 | Alarm Active | Confirmed live (SPIKE-002) |
| 28 | Bell Active | Confirmed live (SPIKE-002) |
| 32 | Exit Started | Confirmed live (SPIKE-002) — fires exactly 30s before `Part Arm 2`/`part armed` on this panel's exit-timer setting. SPIKE-005 additionally observed a second `type=32` entry with `group=17` (vs. the usual `group=16`) immediately after a cancelled-during-exit arm, reproduced twice now (once cancelling an Away arm, once cancelling a Night arm) — likely a distinct "exit cancelled" marker sharing the same type; increasingly confident but still not formally confirmed. |
| 33 | Exit Error (Arming Failed) | Prior art only — not yet observed live |
| 34 | Entry Started | Confirmed live (SPIKE-002) |
| 45 | Reset After Alarm | Prior art only — **not observed live even in a dedicated follow-up test** clearing the alarm-memory indicator after a real trigger (SPIKE-002). Open question: does this panel/firmware ever emit it for this action, or only for a full engineer-level reset? |
| 78 | Part Arm 1 | Prior art only — not yet observed live |
| 79 | Part Arm 2 (`arm_home`) | Confirmed live, reproduced twice (SPIKE-002) |
| 80 | Part Arm 3 | Prior art only — not yet observed live |
| 1 | unknown | Observed live, group values 3/4 seen around alarm-trigger onset — meaning not yet decoded |
| 3 | unknown | Observed live, paired 1:1 with each zone-secure event during arm/disarm bookkeeping bursts — likely "zone secured/omitted" logging, not confirmed |
| 31 | unknown | Observed live on **every** keypad code entry (arm, disarm, alarm-memory clear) — likely a generic "user code entered" event, not confirmed |
| 41 | unknown | Observed live, not yet correlated with a specific action |
| 53 | "Download Start" / remote-session marker (inferred) | Observed live during a Texecom Connect app-originated remote arm (SPIKE-002) **and** repeatedly during an idle subscribed session with no arm/disarm activity (2026-08-04, ~every 2–10s while logged in and event-subscribed). Name inferred from context; behaviour looks more like a periodic "remote/UDL session active" log entry than an action-specific event. |
| 113 | "Remote Command" (inferred) | Inferred, not documented. Originally seen only with the phone app (SPIKE-002); SPIKE-005 has now also observed it (group=`9`) immediately after both a `the prior MQTT bridge`-issued Arm Night and a directly-tested Arm Home — so it is not app-specific after all. See the arm-mode signature note below. |
| 207 | unknown | Observed live (SPIKE-005): group=`6`, immediately after type `113`/group `9` and before the `part armed` AREA event, on every `the prior MQTT bridge`-issued Arm Night. Not seen for Arm Away or Arm Home. Meaning not decoded. |
| 208 | unknown | Observed live (SPIKE-005): group=`6`, in the same position as `207` but following the directly-tested Arm Home instead of Arm Night. Sequential with `207` — see the arm-mode signature note below. |
| 42 | unknown, likely a mode/action-specific marker rather than a client-specific one | Observed live (SPIKE-005): group=`5` immediately after **every** `the prior MQTT bridge`-issued Disarm (Away or Night alike — mode-independent), group=`6` immediately after a `the prior MQTT bridge`-issued Arm **Away** specifically (not seen for Arm Night/Home, which produce 113/207/208 instead — see below). Reproduced 2026-08-08 on Night→disarm via the production client (group=`5`). **Not** observed in the Home→disarm cycles of 2026-08-07–08 where AREA `disarmed` was also absent. Not seen in SPIKE-002. |

**Arm-mode LOG signatures (provisional):** the LOG type/group pair immediately following an
arm or disarm command appears to encode *which arm mode* fired (or that a disarm occurred), not
only *which client* issued it — revising an earlier client-specific hypothesis:
- Disarm after Away or Night: type `42` group `5` — observed with AREA `disarmed` (SPIKE-005;
  2026-08-08 Night).
- Disarm after Home: type `42` group `5` **not** observed in 2026-08-07–08 cycles; LOG type=`3`
  group=`8` bookkeeping still appears after the ACK.
- Arm Away: type `42` group `6`.
- Arm Night: type `113` group `9`, then type `207` group `6`.
- Arm Home: type `113` group `9`, then type `208` group `6` — one sequential step up from Night's
  `207`, matching the mode byte sequence (`01`=Night, `02`=Home).

Treat as a working hypothesis pending wider reproduction (including Away on the production client).

Each LOG event also carries a **group** byte whose meaning is not yet decoded (values 0, 3, 4, 5, 6, 7,
8, 9, 16, 17, 18 observed so far) — open question.

## Zone types

| Code | Meaning | Confirmed on this panel? |
|---|---|---|
| 0 | Unused | Yes |
| 1 | Entry/Exit 1 | Yes |
| 2 | Entry/Exit 2 | Yes |
| 3 | Interior | Yes |
| 4 | Perimeter | Yes |
| 8 | Silent PA | Yes |
| 5–7, 9–21 | Various (per prior-art `zone_types` table) | **No** — this panel's actual configuration only uses the 6 codes above; the rest are prior-art documentation only, unconfirmed against a live panel of this type |

## Known behavioural quirks

- **Single TCP client only.** The ComIP module refuses (silently hangs, does not fast-reject) a
  second connection attempt while another client holds the session (SPIKE-001). Whatever currently
  holds the session must be fully stopped, not just idle, before another client can connect.
- **500ms minimum delay before `LOGIN`** after the TCP connection opens (prior art guidance; not yet
  independently stress-tested for the true minimum on this panel).
- **2-3 second response timeout, retry with the same sequence number** — the documented and
  empirically-confirmed way to recover from an ordinary same-protocol send/receive collision.
- **Idle session timeout without keepalive.** A listen-only subscribed session (no outgoing commands)
  was closed by the panel after ~60s (2026-08-04). Periodic `GETDATETIME` (~15s) kept the same
  session alive for the full multi-minute walk-around mission. Production clients need a keepalive
  regardless of whether they are actively issuing arm/disarm commands.
- **Protocol-format collisions around arm/disarm/trigger events** — see the dedicated section above;
  this is the dominant real-world crash cause, not send timing.
- **Part-Arm Home (slot 2) disarm vs Night (slot 1)** — same `SETAREADISARM` bytes and ACK; Night
  reliably yields AREA `disarmed` on the event path; settled Home disarm repeatedly does not, and
  coincides with a nine-byte Connect LOG-shaped non-frame discard while awaiting the disarm
  response (see AREA section). Clients must not assume AREA-on-disarm is uniform across Part-Arm
  modes on this firmware.
- **Forced disconnect on a real trigger**, with a recovery window measured in tens of seconds to at
  least a minute — see ADR-002.

## Open questions / known gaps

- LOG event types 1, 3, 31, 41, and the "group" byte on every LOG event are unmapped.
- Whether `Reset After Alarm` (type 45) is ever emitted by this panel/firmware for a plain
  disarm-after-alarm or alarm-memory clear, versus only a full engineer-level reset, is unresolved.
- The exact byte format of the non-Connect-protocol traffic beyond the identified AT commands (e.g.
  the 83-byte unidentified burst in SPIKE-002) is not decoded.
- Whether the post-trigger disruption window has a bounded maximum duration is not established — only
  one real data point exists (~50s, not yet recovered).
- Whether any *other* unexercised command (beyond `GETAREADETAILS`, now ruled out) can auto-detect
  Part-Arm slot roles remains open — today the Home/Night-to-slot mapping must be per-installation
  configuration.
- After network disarm from settled **Home** (Part-Arm 2): does the panel omit AREA `disarmed`, or
  is the frame destroyed by ComIP/multiplex collision (nine-byte LOG-shaped discard)? Raw
  whole-stream capture during Home→disarm (before application resync) would distinguish panel
  omission from client-side loss. Away→disarm on the production client is not yet re-verified.

## How to add to this document

Whenever a spike, experiment, or implementation session observes a new command, event type, state
value, or panel behaviour against the **live panel** (not just prior-art reading), add it here with:
the panel model/firmware it was observed on, the raw byte evidence if available, and a link to the
spike/session it came from. Prior-art-only claims (not yet independently observed) must be labelled
as such, not presented as confirmed. Do not delete or water down an existing confirmed finding to
make room for a new one — if a new observation contradicts an old one, record both and flag the
contradiction as an open question until it's resolved.
