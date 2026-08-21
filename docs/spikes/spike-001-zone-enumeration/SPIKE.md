# Spike: zone-enumeration

**Resolves:** RISK-003 / SPIKE-001
**Date:** 2026-08-01
**Type:** Feasibility
**State:** Validated ✅

## Overview

**Question:** Whether the Texecom Connect protocol can enumerate zones (count, type, and name) programmatically, versus requiring the ~35-zone inventory to be hand-transcribed into configuration.
**Answer:** Yes. A live probe against the household's actual panel retrieved the total zone count, then the type and name of every zone, entirely programmatically — with no manual zone list involved and no errors. Two related things were also discovered along the way: the panel's network module only allows one connection at a time, and the panel's password turned out to be the unchanged factory default rather than genuinely blank.
**Recommendation:** Build the new integration to discover the zone list from the panel itself at startup, rather than hand-maintaining a zone inventory in configuration.
**Decisions this unlocks:**
- Whether to build dynamic, panel-driven zone discovery instead of a hand-maintained zone list
- Whether the existing add-on needs to be fully stopped (not just left running) before the new integration can connect, which affects how the cutover between the two is sequenced
- Whether the project's documentation should be corrected to say LOGIN requires a UDL password (often the common factory default on unaltered installs) rather than an empty credential at all
- Whether the "~35 zones" figure used throughout the project's documentation should be updated to the actual number of in-use zones found on the panel

## Question

Whether the Texecom Connect protocol supports enumerating zones (count, type, name) programmatically, versus requiring the ~35-entry inventory to be manually transcribed into configuration.

## Hypothesis

We believe the Texecom Connect protocol supports full zone enumeration (count, type, and name) programmatically, because the publicly available `davidMbrooke/texecom-connect` library already implements a `GETPANELIDENTIFICATION` command (which returns the panel's total zone count) and a `GETZONEDETAILS` command (which returns per-zone type and name/text) against Premier Elite panels speaking Connect protocol v4+.

## Research

**Prior-art code inspection (`davidMbrooke/texecom-connect`, `texecomConnect.py`, MIT/Apache-2.0
licensed, cited in `docs/brief.md` References).** This library already implements two commands
directly relevant to the hypothesis, against Premier Elite panels speaking Connect protocol v4+:

- `CMD_GETPANELIDENTIFICATION = chr(22)` — no request body. The response is a fixed 32-byte
  string that `get_number_zones()` splits on whitespace into `panelType, numberOfZones, something,
  firmwareVersion`. i.e. the panel self-reports its total zone count on request, with no
  configuration-file input required.
- `CMD_GETZONEDETAILS = chr(3)` — request body is a single byte, the zone number. The response
  (34, 35, or 41 bytes depending on firmware/model, per `get_zone_details()`) decodes to a
  `zoneType` byte (1 = Entry/Exit 1 … 21 = Confirmed PA Audible, 0 = unused — see the `zone_types`
  table at `texecomConnect.py:150-171`), an `areaBitmap` (1/2/8 bytes), and a trailing zone
  **name/text** field (`zone.text`, null-padded, stripped of non-word characters in
  `get_zone_details()`). `retrieve_zones()`-style callers (`texecomConnect.py:766-767`) loop
  `for zoneNumber in range(1, numberOfZones + 1)`, i.e. the library's own intended usage pattern is
  full sequential enumeration by combining both commands — count first, then per-zone
  type+name — not a hand-maintained zone list.

**Packet framing needed to reproduce this independently** (`texecomConnect.py:112-143, 364-571`):
a 4-byte header — `'t'` (start), a type byte (`'C'` command / `'R'` response / `'M'` unsolicited
message), a total-length byte (`len(body) + 5`), and a rolling sequence number — followed by the
command body (`cmd_byte` + optional args) and a trailing CRC-8 byte (`poly=0x185, rev=False,
initCrc=0xff`, computed over header+body). `CMD_LOGIN = chr(1)` must be sent first with the UDL
password as its body (empty here, since `docs/brief.md` records no `udl_password` is set on the
panel); the panel ACKs with `0x06` or NAKs with `0x15`. Texecom's own guidance (linked from a
forum post in the source comments) is not to send the login faster than ~500ms after connecting,
or the panel ignores it.

**Corroborating/contrasting evidence from other prior art.** `zebraland/homebridge-texecom` and
`TechDadUK/homebridge-texecom` (both cited informally via web search, not in `docs/brief.md`)
require every zone to be **hand-specified** in their config file (name, number, type). This does
not refute the hypothesis — those projects target the older serial/Crestron transport, not the
Texecom Connect/ComIP protocol this spike is scoped to — but it is a useful caveat: even where a
protocol-level enumeration capability exists, not every integration chooses to use it.

**Live reachability check (this session).** A direct TCP probe from the sandbox to the
configured panel host/port (`TEXECOM_HOST`/`TEXECOM_PORT`) succeeded. The experiment below ran
against live hardware rather than being deferred to an Unvalidated/research-only path.
(Host addresses are not recorded here.)

## Experiment Design

A standalone Python 3 script (`experiment.py`) reimplements the minimal subset of the framing
above from first principles (not by importing the GPL/Apache-licensed prior art directly, to keep
this project's own protocol notes self-produced per RISK-008) and runs it against the live panel:

1. Open a TCP connection to the panel (`TEXECOM_HOST`/`TEXECOM_PORT` env vars — required, no
   hardcoded default), wait 500ms per the framing note above.
2. Send `LOGIN` (command byte `0x01`) with the UDL password from `TEXECOM_UDL_PASSWORD`; confirm `ACK` (`0x06`).
3. Send `GETPANELIDENTIFICATION` (command byte `0x16`/22); parse the 32-byte response into
   panel type, zone count, and firmware version.
4. Loop zone numbers `1..zone_count`; send `GETZONEDETAILS` (command byte `0x03`) with the zone
   number as the argument; decode `zoneType` and the trailing name/text field for each.
5. Print a plain-text report: total zone count, and a table of zone number → type → decoded name
   for every zone, plus any framing/CRC errors or timeouts encountered.

This is a read-only, query/response command sequence (no arm/disarm, no state-changing commands),
so it does not exercise the collision-crash conditions RISK-001/SPIKE-002 is scoped to investigate.

### Decision Criteria

| Criterion | Target | Actual |
|-----------|--------|--------|
| Panel reports a zone count without config input | `GETPANELIDENTIFICATION` returns a non-null integer zone count | **88** — raw response identified an Elite 88 panel model (firmware V6.02.02LS1) |
| Panel reports per-zone type without config input | `GETZONEDETAILS` returns a valid zone-type code (0–21) for every queried zone number | **88/88 zones queried successfully**; 6 distinct type codes observed (0 Unused, 1 Entry/Exit 1, 2 Entry/Exit 2, 3 Interior, 4 Perimeter, 8 Silent PA) |
| Panel reports per-zone name/text without config input | `GETZONEDETAILS` returns a non-empty decoded name string for in-use zones | **40/88 zone slots returned non-empty, human-readable name text**; the other 48 all decoded as `zoneType=0` (Unused) with empty text — consistent with unprogrammed hardware zone slots, not a decode failure |
| Read-only enumeration is safe (no crash/collision) | No forced disconnect (`+++`), repeated NAK, or CRC failure during the full enumeration pass | **True** — all 88 `GETZONEDETAILS` calls succeeded on the first attempt (zero retries, zero timeouts, zero CRC mismatches), login ACKed cleanly, socket closed cleanly |

*Actuals are populated from experiment output only — not from documentation, vendor claims, or community reports.*

**Unplanned but load-bearing sub-experiment.** The first several connection attempts (with the prior MQTT bridge
still running) hung at the TCP `connect()` stage for the full 8s timeout with zero response — not a fast
"connection refused". Stopping the prior MQTT bridge add-on made the very next `connect()` succeed instantly
(0.00s), and the enumeration run above completed immediately afterward. This is strong evidence the
ComIP module accepts only **one TCP client at a time**; see `## Decisions required`.

**Unplanned but load-bearing sub-experiment #2.** A LOGIN with an empty password body was cleanly
**NAK**'d (framing/CRC round-tripped). LOGIN with a non-empty UDL password (panels often ship with
factory default `1234` — see consumer docs) was **ACK**'d. Empty credential is therefore not a valid
assumption; UDL must be supplied. See `## Decisions required` and `## Open questions`.

## Results

Raw output of `experiment.py` against the live panel (`TEXECOM_HOST`/`TEXECOM_PORT`,
`TEXECOM_UDL_PASSWORD` set; the prior MQTT bridge stopped). Host address and zone name
strings are redacted for publish hygiene (RISK-017):

```
=== SPIKE-001 experiment: zone enumeration feasibility ===
Target: <redacted>:10001
[ok] TCP connected
[ok] LOGIN (password set)
[ok] GETPANELIDENTIFICATION raw: 'Elite 88     ENG->SW V6.02.02LS1'
     parsed parts: ['Elite', '88', 'ENG->SW', 'V6.02.02LS1']
[ok] panel reports 88 zones
  … 40 in-use zones with human-readable panel name text (types Entry/Exit, Perimeter,
    Interior, Silent PA); 48 Unused empty slots …
  (per-zone name dump omitted — household layout fingerprint)

=== Summary ===
Zone count from panel: 88
Zones successfully queried: 88/88
Distinct zone type codes seen: [0, 1, 2, 3, 4, 8]
Zones with non-empty name text: 40/88

=== Decision criteria (raw) ===
zone_count_reported: 88
zone_type_reported: 6 distinct type codes seen across 88/88 zones queried ok
zone_name_reported: 40/88 zones returned non-empty name text
no_crash_or_collision: True
```

Prior to this successful run, four separate connection attempts (three from Python, one from a
raw `bash /dev/tcp` probe) each hung for their full timeout (8s) with zero bytes returned, while
the prior MQTT bridge was still running. The very next attempt, immediately after the prior MQTT bridge was
stopped, connected in 0.00s.

## Conclusion

**Hypothesis supported.** The panel returned a usable zone count (`88`, via
`GETPANELIDENTIFICATION`) and, for every one of those 88 zone slots, a decoded type and name/text
via `GETZONEDETAILS` — with zero framing errors, zero retries, and zero timeouts across the full
88-zone pass (`no_crash_or_collision: True`). 40 of the 88 slots came back with non-empty
human-legible name text; the remaining 48 decoded as `zoneType=0` (Unused), which is the
expected signal for unprogrammed hardware zone slots on an 88-zone-capacity panel, not a decode
failure. This directly refutes the alternative ("zones must be hand-transcribed into config") for
a Premier Elite 88 on firmware `V6.02.02LS1`.

Two secondary findings emerged that were not part of the original hypothesis but carry their own
architectural consequences (see `## Decisions required`): the ComIP module appears to accept only
one TCP client at a time, and LOGIN requires a non-empty UDL password (blank is NAK'd; factory
default `1234` is commonly accepted on unaltered installs — consumer docs note this generically).

## Options

### Option A: Dynamic enumeration via `GETPANELIDENTIFICATION` + `GETZONEDETAILS`

The new integration queries the panel for its zone count and per-zone type/name at startup (and
re-queries on a "Site Data Changed" event, per the `# FIXME` noted in the prior-art source), and
builds its HA entities from that response.

- **Pros:** Empirically validated end-to-end against the live panel with zero errors; automatically
  tracks zone renames/re-programming done at the panel keypad without an app config change;
  correctly distinguishes in-use (40) from unused (48) zone slots, avoiding dead entities.
- **Cons:** Requires exclusive access to the single ComIP TCP session (see Decisions required);
  adds a startup dependency on the panel being reachable and logged in before entities can be
  created.

### Option B: Hand-maintained static zone list (status quo pattern)

Zone number, type, and name are hardcoded in the new integration's configuration, as
`homebridge-texecom` and `TechDadUK/homebridge-texecom` do for their (different, serial/Crestron)
transport.

- **Pros:** No dependency on a live panel connection to know the zone list; matches the pattern
  already used by every other prior-art project surveyed.
- **Cons:** Directly reintroduces the maintenance burden and silent-drift risk this spike exists to
  avoid (RISK-003's severity rationale); was not what was tested — this experiment demonstrated the
  panel doesn't require this, making it a strictly worse fit now that Option A is validated.

### Option C: Hybrid — dynamic enumeration with a static fallback

Attempt dynamic enumeration at startup; if the panel connection can't be established (e.g. another
client is holding the single ComIP session) or times out, fall back to a last-known-good cached
zone list (persisted from a prior successful enumeration) rather than failing to start.

- **Pros:** Keeps Option A's benefits while giving the integration a graceful degradation path for
  the single-session constraint this spike surfaced, instead of a hard startup failure.
- **Cons:** More implementation complexity than Option A alone; the fallback path itself is
  untested by this spike (no experiment exercised it).

## Recommendation

**Option A (dynamic enumeration)**, with the single-session caveat from `## Decisions required`
factored into the cutover plan. The experiment validated exactly this approach against the live
panel with a clean, error-free 88-zone pass, and it directly resolves RISK-003's severity concern
(the ~35-entry, manually-transcribed, drift-prone inventory). Whether to harden it into Option C's
fallback behavior is a reasonable follow-up implementation decision, but is not required to resolve
this spike's core question, and wasn't itself experimentally validated here — recorded as an open
question rather than folded into the recommendation.

This recommendation assumes: (a) the panel firmware/model behaves the same way when the eventual
integration code (not this throwaway script) performs the same command sequence; (b) the new
integration will have exclusive access to the ComIP session when it needs to enumerate (addressed
by the cutover-sequencing decision below); (c) the panel's zone configuration (which slots are
in-use, and their names) doesn't need to be known at build time — it can genuinely be discovered
at runtime.

## Decisions required

- Should the new integration retrieve the zone inventory dynamically via
  `GETPANELIDENTIFICATION` + `GETZONEDETAILS` at startup (Option A), rather than a hand-maintained
  zone list in configuration (Option B)?
- Given the ComIP module accepted no second TCP client while the prior MQTT bridge held its session (four
  consecutive silent connect-timeouts, resolved instantly once the prior MQTT bridge was stopped), should
  the phase 2 cutover plan require the prior MQTT bridge to be **stopped**, not just present-but-idle,
  before the new integration first connects — foreclosing a side-by-side testing period on the same
  ComIP module unless a second module/port is used?
- `docs/brief.md`'s Current Setup note ("no `udl_password` set") and RISK-009's severity rationale
  both describe the panel as unauthenticated; this experiment shows the panel is actually running
  with a UDL password (commonly the factory default `1234` on unaltered installs) active and required for every command, not an empty
  credential. Should these two documents be corrected to reflect an authenticated-with-a-known-
  default-password panel, which changes RISK-009's exact framing (still low real-world exposure per
  its own rationale, but for a different reason)?
- The panel reports 88 total addressable zone slots but only 40 are actually in-use/named — a
  materially different number from the "~35-entry inventory" language used throughout
  `docs/brief.md` and both specs. Should the zone-monitoring build treat "in-use" as
  `zoneType != 0` (as this experiment did) as the authoritative definition of which zones get HA
  entities, superseding the earlier ~35 estimate?

## Open questions

- Whether the ComIP module's one-connection-at-a-time behavior is a fixed hardware/firmware limit
  or a configurable setting (e.g. via panel engineer/Wintex programming) was not tested here — if
  it can be relaxed, a side-by-side testing period alongside the prior MQTT bridge might become possible
  after all. Would need a follow-up check (not necessarily a full spike) against the panel's
  installer-level configuration options.
- The `areaBitmap` field returned alongside each zone's type/name was received but not decoded or
  cross-checked against the panel's actual area configuration in this experiment — deferred as out
  of scope for the zone-enumeration question, but may be relevant to SPIKE-004 (entity architecture)
  if area membership needs to be modeled.
- Only 6 of the ~21 documented zone-type codes were observed in this house's actual configuration
  (Unused, Entry/Exit 1, Entry/Exit 2, Interior, Perimeter, Silent PA) — the mapping for the other
  15 codes rests on the prior-art `zone_types` table (research, not this experiment) and hasn't
  been independently confirmed against a live panel reporting one of those less-common types.
