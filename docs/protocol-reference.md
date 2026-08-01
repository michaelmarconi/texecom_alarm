# Texecom Connect Protocol Reference

**Status:** Living document — updated whenever a spike, experiment, or implementation work discovers
something new about the wire protocol. Do not treat this as complete or final; treat gaps as gaps,
not as "not applicable."

**Panel under test:** Texecom Elite 88, firmware `ENG->SW V6.02.02LS1`, via a ComIP network module.
Findings here are empirical (captured live against this panel) unless explicitly marked otherwise.
Behaviour may differ on other panel models/firmware.

**Sources so far:**
- [SPIKE-001](spikes/spike-001-zone-enumeration/SPIKE.md) — zone enumeration
- [SPIKE-002](spikes/spike-002-arm-home-triggered-framing/SPIKE.md) — arm_home / triggered-event framing and the collision crash
- `davidMbrooke/texecom-connect` (`texecomConnect.py`, MIT/Apache-2.0) — prior-art source inspection, cited where it informed a finding
- Community report: `the prior MQTT bridge` HA thread, user Ben.S, 2020 — cited where it corroborates a finding

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
prior-art inspection are listed. **There is no known `SETAREASTATE`/arm/disarm send-side command** —
no inspected prior art implements issuing arm/disarm, and guessing an undocumented command against a
live occupied security panel is not acceptable (see SPIKE-002 Research). This is the single biggest
remaining gap in this reference.

| Byte | Name | Body | Notes |
|---|---|---|---|
| 1 | `LOGIN` | UDL password | Panel ACK/NAK. This panel's password is the factory default `1234`, not blank (SPIKE-001). |
| 3 | `GETZONEDETAILS` | zone number (1 byte) | Returns zone type + area bitmap + name/text. 34/35/41-byte response depending on firmware. |
| 13 | `GETLCDDISPLAY` | — | Not yet exercised against this panel. |
| 15 | `GETLOGPOINTER` | — | Not yet exercised against this panel. |
| 22 | `GETPANELIDENTIFICATION` | — | Returns a 32-byte string: panel type, zone count, unknown field, firmware version. This panel: `'Elite 88     ENG->SW V6.02.02LS1'` → 88 zones. |
| 23 | `GETDATETIME` | — | Used as a safe idle/keepalive probe in SPIKE-002; read-only. |
| 25 | `GETSYSTEMPOWER` | — | Not yet exercised against this panel. |
| 27 | `GETUSER` | — | Not yet exercised against this panel. |
| 35 | `GETAREADETAILS` | — | Not yet exercised against this panel. |
| 37 | `SETEVENTMESSAGES` | 2-byte bitmask: `DEBUG \| ZONE_EVENT \| AREA_EVENT \| OUTPUT_EVENT \| USER_EVENT \| LOG_FLAG` | Subscribes the session to unsolicited `'M'`-type push messages. Confirmed safe and working. |

**Send-side arm/disarm — open gap.** `a prior MQTT bridge` (closed-source) is the only known
implementation that issues real arm/disarm over Connect protocol, but its source isn't available.
Filling in this gap safely (without guessing against the live panel) is still an open problem for
this project.

## Unsolicited messages (panel → client, after `SETEVENTMESSAGES`)

All arrive as `'M'`-type frames. First payload byte is a sub-type:

| Sub-type | Meaning | Payload (after sub-type byte) |
|---|---|---|
| `0x01` | ZONE event | zone number, state bitmap (`0x01` active / `0x00` secure, other bits seen: `0x10`, `0x40` — meaning not yet decoded) |
| `0x02` | AREA event | area number, state byte (see AREA state table below) |
| `0x03` | OUTPUT event | output/relay number + state — bookkeeping only, not yet decoded in detail |
| `0x04` | USER event | fires on every keypad code entry (arm, disarm, or clearing an alarm-memory indicator) — does **not** by itself distinguish which action occurred |
| `0x05` | LOG event | event type byte + group byte + timestamp-ish trailing bytes (see LOG event table below) |

### AREA event states

| Value | State |
|---|---|
| 1 | `disarmed` |
| 2 | `in entry` |
| 3 | `armed` (full) |
| 4 | `part armed` |
| 5 | `in alarm` |
| 7 | unknown — observed immediately after every `part armed` transition in both SPIKE-002 arm cycles; not yet explained |

`in exit` (value `1` per one capture, but note value `1` is also used for `disarmed` in the numbering
above pulled from prior art — **this needs reconciling**; SPIKE-002's raw capture shows `state=in exit`
decoded from `raw=020101`, i.e. area=1, state byte=`01`, which prior art's table also maps to
`disarmed`. Flag this as an unresolved decode ambiguity, not a confirmed value, until cross-checked.)

**Disarm does not appear to produce a distinct AREA event or dedicated LOG event on this panel** — only
the generic USER event + LOG type 31 pair (see below), same as at arm time. Same for clearing an
alarm-memory indicator after a trigger. This is a confirmed empirical finding (SPIKE-002), not an
assumption — treat "no event" as the current answer, not as "not yet tested."

### LOG event types

Confirmed against this panel (via live capture) unless marked "prior art only":

| Type | Name | Status |
|---|---|---|
| 27 | Alarm Active | Confirmed live (SPIKE-002) |
| 28 | Bell Active | Confirmed live (SPIKE-002) |
| 32 | Exit Started | Confirmed live (SPIKE-002) — fires exactly 30s before `Part Arm 2`/`part armed` on this panel's exit-timer setting |
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
| 53 | "Download Start" (inferred) | Observed live only during a Texecom Connect app-originated remote arm (SPIKE-002 first run) — name inferred from context (preceded a remote/app action), not from documentation |
| 113 | "Remote Command" (inferred) | Same as above — inferred, not documented |

Each LOG event also carries a **group** byte whose meaning is not yet decoded (values 0, 3, 4, 6, 7, 8,
9, 16, 18 observed so far) — open question.

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
- **Protocol-format collisions around arm/disarm/trigger events** — see the dedicated section above;
  this is the dominant real-world crash cause, not send timing.
- **Forced disconnect on a real trigger**, with a recovery window measured in tens of seconds to at
  least a minute — see ADR-002.

## Open questions / known gaps

- The send-side arm/disarm command byte and body format are still unknown — see Commands above.
- LOG event types 1, 3, 31, 41, and the "group" byte on every LOG event are unmapped.
- Whether `Reset After Alarm` (type 45) is ever emitted by this panel/firmware for a plain
  disarm-after-alarm or alarm-memory clear, versus only a full engineer-level reset, is unresolved.
- The `AREA event` value used for `in exit` appears to collide with the documented value for
  `disarmed` — needs reconciling against a live capture that unambiguously distinguishes the two.
- The exact byte format of the non-Connect-protocol traffic beyond the identified AT commands (e.g.
  the 83-byte unidentified burst in SPIKE-002) is not decoded.
- Whether the post-trigger disruption window has a bounded maximum duration is not established — only
  one real data point exists (~50s, not yet recovered).

## How to add to this document

Whenever a spike, experiment, or implementation session observes a new command, event type, state
value, or panel behaviour against the **live panel** (not just prior-art reading), add it here with:
the panel model/firmware it was observed on, the raw byte evidence if available, and a link to the
spike/session it came from. Prior-art-only claims (not yet independently observed) must be labelled
as such, not presented as confirmed. Do not delete or water down an existing confirmed finding to
make room for a new one — if a new observation contradicts an old one, record both and flag the
contradiction as an open question until it's resolved.
