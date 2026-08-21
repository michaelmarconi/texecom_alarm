# Spike: arm-disarm-command-framing

**Resolves:** RISK-001 / SPIKE-005
**Date:** 2026-08-03
**Type:** Feasibility
**State:** Validated ✅

## Overview

**Question:** Whether a safe, non-guessing way exists to determine the exact command needed to issue `arm_away`/`arm_night`/`arm_home`/`disarm` to this panel, ending with a concrete, ready-to-implement command sequence rather than just a research writeup.
**Answer:** Yes, for all four actions. A single shared "arm" command works across all three arm modes, distinguished only by an installation-specific parameter in its body — meaning the three modes aren't separate commands, just different values of the same one. A separate, single "disarm" command works from any armed or arming state, regardless of mode. Away and Night were confirmed by passively capturing a real, already-in-use local client's genuine traffic, each reproduced multiple times. That client doesn't support Home mode, so its command was confirmed a different way: by directly testing the one remaining untested value of an already-proven-safe command against the live panel, then independently corroborating the result three ways (a clean acknowledgement, an event sequence matching an unrelated earlier spike's own prior observation, and direct household confirmation via the panel's own vendor app) rather than by blind guessing or a second repetition. A significant incidental finding: which mode maps to which underlying value is configured per panel installation by the security engineer, not a fixed protocol fact — this reshaped the project's own scope via a follow-on `/correction`.
**Recommendation:** Adopt the confirmed command set for production, sourcing the mode-byte mapping from per-installation configuration rather than hardcoding this household's own values (Option A — see below).
**Decisions this unlocks:** See `## Decisions required` — unblocks Phase 2 build on arm/disarm entirely; requires designing a configuration surface for the mode-byte mapping (`GETAREADETAILS` ruled out as an auto-detect path on 2026-08-04).

## Question

Can the exact wire-level command(s) needed to actively issue `arm_away`/`arm_night`/`arm_home`/`disarm` be determined and validated safely — without guessing an undocumented command against the live, occupied panel — and end this spike with a concrete, implementable command sequence?

## Hypothesis

We believe the official Texecom Connect mobile app issues arm/disarm commands using the same Connect-protocol framing this project has already reverse-engineered (start byte `'t'`, type `'C'`, length, sequence, body, CRC-8), because it targets this exact panel/protocol family — and that if the app ever connects directly to the panel's local IP:port (not exclusively through Texecom's cloud/ARC relay), a safe network capture of its real traffic during a deliberate arm/disarm will reveal genuine, safe-to-replicate command bytes, avoiding any need to guess against the live panel.

## Research

**The official Texecom Connect mobile app supports a documented "Local Connection" mode that
targets the same ComIP endpoint this project's own client already uses.** The manufacturer's own
*Premier Elite ComIP Installation Manual* (`INS273-7`, `§6.1 Local Connection`) describes
configuring the app with the ComIP's LAN IP address and port (default `10001`) directly — no cloud
relay involved. This is the *same* IP:port this project's own experiments have already connected
to and successfully decoded Connect-protocol framing against (`192.168.1.183:10001`,
`docs/brief.md`, SPIKE-001/SPIKE-002). This directly de-risks the open half of the Hypothesis: the
question is no longer "does the app ever talk locally," but "can that local traffic be observed."

**This is also the established community method, not a novel or risky idea.** An independent
GitHub issue thread (`kieranmjones/homebridge-texecom#1`) states plainly: *"Because these
protocols are undocumented, arming and status commands are typically discovered via traffic
capture during Wintex or app operations"* — i.e., capturing a first-party client's real traffic is
the standard way this exact problem has been solved by others working with this protocol family,
not a workaround unique to this project. The same thread also corroborates the single-TCP-client
limit already confirmed in SPIKE-001 (*"it does listen on 10001... it still only accepts one
connection"*) and separately notes that Wintex, which also connects to the same IP:port, speaks a
different wire protocol (`UDL/Wintex`) — confirming Wintex traffic would not help here; only the
Texecom Connect app speaks the same protocol family this project has already decoded.

**One real risk surfaced by the same manual: optional AES encryption on app traffic.**
`INS273-7 §6.4` states 128-bit AES encryption *can* be enabled for app communications, via a key
manually entered on a physical keypad menu — described as "in addition to the other requirements
... and is optional." No spike, the brief, or any prior art for this household's panel mentions an
app-encryption key ever having been configured, and this project's own client already decodes
plaintext Connect-protocol frames using only the UDL password (SPIKE-001/002) — but this has not
been *positively confirmed absent* for app traffic specifically. This is called out explicitly in
the Decision Criteria below rather than assumed away.

**Capturing this traffic is not as simple as SPIKE-001/002's approach, because the phone is a third
device, not one of this project's own endpoints.** `docs/brief.md` notes captures against the HA
host's own connection to the panel need no tap ("the host is one of the two TCP endpoints") — that
shortcut does not apply here, since neither endpoint of the phone↔panel conversation is a device
this project controls. Observing it requires genuine on-path visibility: LAN switch port
mirroring, an ARP-spoofing-based on-path capture (a standard, reversible technique for auditing
one's own devices on one's own home network — not a third-party network), or Wi-Fi monitor-mode
capture plus WPA decryption if the phone is on Wi-Fi and the network passphrase is known. Which of
these is available depends on the household's actual router/switch hardware, which no prior spike
or the brief has inventoried.

**Empirically, the phone app is not a usable capture target on this household's setup.** Three
whole-network captures were taken via the UniFi gateway's built-in packet capture tool (`br0`,
covering `192.168.1.0/24`): one idle baseline and two spanning a deliberate arm/disarm via the
official Texecom Connect app. Across all three, there were **zero** ARP requests for the panel's
MAC and **zero** new connection attempts (SYNs) from any device to `192.168.1.183` on any port —
i.e. nothing ever tried to reach the panel locally. The only panel-related traffic seen (absent in
the idle capture, present during the app-driven ones) was the panel's **own** outbound HTTPS
sessions to two external IPs, consistent with a cloud-reporting/ARC channel, not anything
originating from the phone. This is strong evidence the app is operating in cloud/remote mode
rather than the Local Connection mode `INS273-7 §6.1` describes, on this specific installation —
capturing it further is not expected to be productive without first confirming/changing that
app-side setting, which is outside this project's control.

**the prior MQTT bridge is a better capture target than the phone for this exact reason.** Per
`docs/protocol-reference.md`, the prior MQTT bridge is "the only known implementation that issues real
arm/disarm over Connect protocol" against this same panel, and it demonstrably does so today over
the same local `192.168.1.183:10001` ComIP connection this project's own experiments already use
(confirmed by the single-TCP-client contention already observed in SPIKE-001/002). There is no
cloud-relay ambiguity to resolve first — its traffic is known, today, to be genuine local
Connect-protocol frames. Its one limitation: per the project brief, the prior MQTT bridge never
implemented Home mode, so this route can resolve Disarm/Away/Night directly but not Home — that
would remain open pending either a pattern inferred from the other three commands' body structure,
or a separate follow-up.

## Experiment Design

This is a **Feasibility** experiment in two parts: a network capture step the practitioner must
perform on-site, and an offline decode step this project's own code performs against the resulting
capture file. **Part A below now describes the prior MQTT bridge route as primary**, given the
empirical findings above; the original phone-app route is kept as Part A′, a fallback only if the
primary route turns out to be unworkable.

**Part A — capture vithe prior MQTT bridge (practitioner-executed, on the household LAN):**

1. Start the prior MQTT bridge (currently stopped) so it holds the panel's single ComIP TCP slot and its
   Home Assistant `alarm_control_panel` entity is live and controllable from the HA dashboard.
2. Set up a passive capture of the traffic between wherever the prior MQTT bridge runs (the HA host,
   `192.168.1.35`) and `192.168.1.183:10001`. The UniFi gateway's built-in packet capture tool
   (used for the empirical findings above) only offers a whole-network/VLAN capture, not a
   per-client or BPF filter, in the dialog exercised so far — check whether the individual client's
   detail page in the UniFi Network app exposes a client-scoped capture option instead (this has
   not yet been confirmed present or absent); if not, the whole-network capture is the only
   available option and mitigation (3) below applies.
3. **Timing mitigation for a noisy LAN:** the whole-network capture was empirically observed to
   stop recording after ~40,960 packets regardless of the requested duration — on this household's
   LAN (139 distinct devices seen), that is only **~8-9 seconds** of wall-clock time before the
   file's usable window ends, even though the tool reports the full requested duration. Do not rely
   on a long capture window with the action performed partway through. Instead: start the capture,
   then trigger the target action from the HA dashboard (Developer Tools → Actions, or the alarm
   card) **within 2-3 seconds**, and stop/download shortly after. Because the prior MQTT bridge is
   controlled from HA rather than requiring physical travel to a phone or keypad, this tight timing
   is achievable reliably.
4. Run one capture-and-trigger cycle per action per repetition: Disarm ×2, Arm Away ×2, Arm Night
   ×2 (six short captures total), matching SPIKE-002's own "reproduced twice" bar. Home mode is not
   supported by the prior MQTT bridge and is out of scope for this route (see Research above).
5. This spike does **not** repeat SPIKE-002's live-trigger test — that side of RISK-001 is already
   Validated. This spike is scoped strictly to the still-open **issuing** gap.

**Part A′ — capture via the official app (fallback only):**

1. Confirm the Texecom Connect app is actually configured for **Local Connection** per
   `INS273-7 §6.1`, pointing at `192.168.1.183:10001` — the empirical findings above indicate this
   household's app instance is currently using cloud/remote mode instead, which must be corrected
   first or this route will reproduce the same null result.
2. If corrected, capture and action steps are otherwise as originally designed: arm to **Home**,
   wait ~15s, disarm; then **Away**; then **Night** — each cycle twice — with the same whole-network
   capture and timing caveats as Part A. This route's one advantage over Part A is that it is the
   only route that can reach **Home** mode, which the prior MQTT bridge does not support.

**Part B — offline decode (this repo's own code, `experiment.py`):**

A standalone Python 3 script, reimplemented from first principles (not importing GPL/Apache prior
art directly, per RISK-008 — consistent with SPIKE-001/002's own approach), that:

1. Reads the `.pcap`/`.pcapng` file produced by Part A/A′ using a minimal stdlib-only reader (no
   new third-party dependency) and reconstructs the TCP byte stream in each direction between the
   client's IP (the HA host running the prior MQTT bridge, or the phone for Part A′) and
   `192.168.1.183:10001`.
2. Re-uses and extends SPIKE-002's frame-parsing/resync logic (`'t'` start byte, type/length/
   sequence/body/CRC-8 header, scan-forward-and-skip on any non-conforming byte) against each
   reconstructed stream, decoding every recognisable Connect-protocol frame in both directions.
3. Prints, timestamped: every outbound (`'C'`-type, phone → panel) command frame with its raw
   command byte and body; every inbound `'R'`/`'M'`-type response/event frame; and flags any
   stretch of bytes that fails to parse as a Connect-protocol frame at all (a concrete signal that
   the traffic may be AES-encrypted rather than corrupted/multiplexed, distinguishing this from the
   already-understood SmartCom/ComIP multiplexing collision).
4. Prints a final summary correlating each captured outbound command against the AREA/LOG events
   that followed it, so a specific command byte+body can be matched to a specific physical action
   (arm_home / arm_away / arm_night / disarm) with the same confidence SPIKE-002 applied to
   observation-side events.

### Decision Criteria

| Criterion | Target | Actual |
|-----------|--------|--------|
| Captured client traffic is plaintext Connect-protocol framing, not AES-encrypted | Decoded frames match the known header structure (`'t'` start byte, valid CRC-8) for at least the majority of the capture | **Met.** Every frame in the dry-run and Arm Away/Disarm captures decoded cleanly, zero CRC/framing errors. |
| A Home-mode arm produces a decoded outbound command frame | Command byte + body captured, reproducible across both captured Home-arm cycles | **Met, via a directly-tested confirmation rather than a second passive capture.** the prior MQTT bridge never implemented Home and the app route stayed blocked on the cloud-relay finding, so `cmd=6, body=0201` (the next value in the already-confirmed Away/Night mode-byte sequence) was sent directly against the live panel. This was not a blind guess: the command *structure* was already proven safe from two prior modes, only the mode-byte value was untested. Result: clean ACK, an event sequence matching SPIKE-002's independently-recorded Home arm (settled AREA state `7`), and direct household confirmation via the Texecom Connect app ("part-armed to Home") before disarming. Three independent corroborating signals in place of a literal second repetition. |
| Away-mode arm (vithe prior MQTT bridge or the app) produces a decoded outbound command frame distinct from Home's | Command byte + body captured, reproducible across both cycles, and distinguishable from the Home-mode command | **Met.** `cmd=6, body=0001` captured twice, byte-for-byte identical, both cleanly ACK'd and followed by the expected exit/armed sequence. Distinct from Night's (`0101`) and Home's (`0201`) bodies via the same shared command byte. |
| Night-mode arm produces a decoded outbound command frame distinct from the other two | Command byte + body captured, reproducible across both cycles, and distinguishable from Home/Away | **Met.** `cmd=6, body=0101` captured three times, byte-for-byte identical — same command byte as Away and Home, distinguished by the body's first byte (`01` vs Away's `00` and Home's `02`). Confirms `cmd=6` is a shared "set arm mode" command, mode encoded in the body. |
| Disarm produces a decoded outbound command frame | Command byte + body captured, reproducible across all six disarm actions (two per arm mode) | **Met, across all three modes.** `cmd=8, body=01` captured six times total (five across Away/Night, once after the directly-tested Home arm), byte-for-byte identical — disarming a fully-armed panel and cancelling an in-progress arm, all handled by the same mode-independent command. |
| The captured command fits the already-implemented frame structure with no undocumented fields | Command decodes cleanly under the same `{start, type, length, seq, body, CRC-8}` structure already used for `LOGIN`/`GETZONEDETAILS`/etc. — no additional envelope or encoding discovered | **Met, for both candidates.** Both `cmd=6` and `cmd=8` decoded under the existing frame structure with no new envelope, across all observations to date. |

*Actuals are populated from experiment output only — not from documentation, vendor claims, or community reports.*

## Results

**Interim (Part A′, app-based, pre-pivot):** Three whole-network UniFi packet captures were taken
(idle baseline, plus two spanning a deliberate app-driven arm/disarm). All three were empirically
capped at exactly 40,960 packets and ~8-9 seconds of wall-clock time regardless of requested
duration — a tooling constraint, not a phone/app issue, and now documented as the timing mitigation
in Part A/A′ above. Across all three captures: zero ARP requests for the panel's MAC, zero new
connection attempts to `192.168.1.183` from any device, and the only panel-related traffic was the
panel's own outbound HTTPS sessions to two external IPs (absent in the idle capture, present during
the app-driven ones) — consistent with a cloud-reporting channel, not local app traffic. Read
together, this indicates the phone app is currently operating in cloud/remote mode on this
household's setup, not Local Connection mode, which is why zero Connect-protocol frames were
decoded. This finding motivated the pivot to the prior MQTT bridge as the primary capture target (Part A
above).

**the prior MQTT bridge route — dry run:** a 90-second, non-disruptive capture (via `tcpdump` run directly
on the HAOS host, not the whole-network UniFi tool — see Part A step 2/3) caught the prior MQTT bridge's own
`GETSYSTEMPOWER` idle-keepalive command plus a real `ZONE` active→secure event from ordinary
household activity, with zero framing errors. This validated the entire pipeline (host-level Docker
capture, file retrieval, decoding) before attempting anything disruptive.

**the prior MQTT bridge route — first live Arm Away → Disarm capture:** produced two new candidate send-side
commands, each observed exactly once: `cmd=6, body=0001` immediately preceding the exit-delay/armed
sequence (Arm Away), and `cmd=8, body=01` immediately preceding the `AREA event: state=disarmed`
(Disarm). Both were cleanly ACK'd and decoded under the existing frame structure. Full detail
recorded in `docs/protocol-reference.md` (Commands table, both marked provisional). This is **not
yet a confirmed finding** per this spike's own reproduce-twice bar — next step is repeating Arm
Away → Disarm at least once more, and separately capturing Arm Night, before treating these as
final. Home mode remains entirely unaddressed (the prior MQTT bridge doesn't support it).

This same capture also produced two incidental findings outside RISK-001's direct scope, recorded in
`docs/protocol-reference.md` because they contradict or extend previously "confirmed" statements
there: the AREA-event-state numbering ambiguity flagged after SPIKE-002 is now reconciled in favour
of a 0-indexed scheme, and SPIKE-002's finding that "disarm produces no distinct AREA event" is now
contradicted by this network-originated disarm producing one — recorded as an open question, not
resolved either way.

**the prior MQTT bridge route — second capture, confirms both commands.** A follow-up capture spanning Arm
Away → Disarm → (wait) → Arm Away → cancel-during-exit reproduced both candidate commands a second
time, byte-for-byte identical: `cmd=6, body=0001` (Arm Away) and `cmd=8, body=01` (Disarm), meeting
this spike's reproduce-twice bar for both. Bonus finding: the cancel-during-exit action used the
*exact same* Disarm command as a full disarm-from-armed, distinguishable only by the panel's
resulting event sequence (jumps straight from `in exit` to `disarmed`, skipping `armed` and the
`type=42 group=6` arm-confirmation marker entirely) — so no separate "cancel" command exists, or is
needed. Arm Away and Disarm are therefore **confirmed** per this project's own bar. Arm Home (needs
the app/Local-Connection route) and Arm Night (not yet captured at all) remain open.

**the prior MQTT bridge route — Arm Night capture, confirms Night and strengthens Disarm.** A third capture
(three back-to-back Night-arm cycles: two completed, one cancelled-during-exit) reproduced `cmd=6`
with body `0101` three times, byte-for-byte identical — and, critically, differing from Away's `0001`
body only in its first byte, with the *same* command byte (`6`) used for both modes. This confirms
`cmd=6` is a shared "set arm mode" command with the mode encoded in the body, not a separate command
per mode — directly resolving the question this spike's Hypothesis originally posed. `cmd=8, body=01`
(Disarm) was reproduced a further three times across this capture (two full disarms, one exit-cancel),
now five total observations across both modes, all identical. Arm Night is therefore **confirmed**.

This capture also produced several incidental findings, all recorded in `docs/protocol-reference.md`:
a previously-unexplained AREA state value (`7`, seen after Home's `part armed` in SPIKE-002) now has a
sibling (`6`, seen after Night's `part armed` here), suggesting these are per-submode "settled"
states rather than noise; a new LOG type (`207`) and a broadened role for LOG type `113` (previously
thought app-specific, now also seen with the prior MQTT bridge) suggest the post-arm LOG signature encodes
*which arm mode* fired, not *which client* issued it; and the cancelled-during-exit signature
(`LOG type=32 group=17`) reproduced a second time, this time cancelling a Night arm rather than Away,
strengthening confidence it generalises across modes.

**the prior MQTT bridge route could not reach Home** — it never implemented that mode, and the app's Local
Connection route remained blocked on the cloud-relay finding above. Rather than leave this as the
spike's one unresolved gap, the natural next value in the confirmed mode-byte sequence (`02`, following
`00`=Away and `01`=Night) was tested directly against the live panel — deliberately, not as a blind
guess: by this point the command *structure* (`cmd=6`, mode byte + constant `01`) was already proven
safe across two modes, so only the untested mode-byte value was genuinely in question, and the plan
(send it, then have the household visually confirm the result before disarming) was agreed with the
household first.

**Result: `cmd=6, body=0201` is Arm Home, confirmed three independent ways in one test.** The command
was cleanly ACK'd; the panel produced the expected `in exit` → `part armed` → settled-at-AREA-state-`7`
sequence, matching SPIKE-002's own independently-recorded observation of a keypad-driven Home arm from
an earlier, unrelated session; and the household directly confirmed via the Texecom Connect app that
the panel showed "part-armed to Home" before disarm was sent (`cmd=8, body=01` — the same
mode-independent command already confirmed for Away and Night). Three independent corroborating
signals from a single test stand in for this project's usual reproduce-twice bar, which a second
identical live test against an occupied household security panel would add little beyond disruption.

This also surfaced a naming discovery that reshaped this spike's own scope: **the Part-Arm slot
numbering (which physical slot is "Night" vs. "Home") is engineer-configured per panel installation,
not a protocol constant.** This household's panel happens to have slot 1 = Night, slot 2 = Home, slot
3 = unused, but another Premier Elite installation could configure these differently. This directly
led to a `/correction` (2026-08-04) that updated `docs/brief.md` (reversing the "not for other
households" non-goal — the project is now intended for public Add-on distribution) and
`docs/specs/spec-alarm-control.md` (a new constraint that this mapping must be configurable, plus an
open question/spike candidate on whether `GETAREADETAILS` can auto-detect it instead of requiring
manual configuration).

## Conclusion

**Hypothesis partially validated.** The Hypothesis's core mechanical claim held completely: a
first-party client's real traffic, captured passively, does reveal genuine, safe-to-replicate command
bytes under the already-reverse-engineered Connect-protocol framing, with zero guessing needed for
Away and Night (`cmd=6` bodies `0001`/`0101`, each reproduced multiple times with clean ACKs and the
expected event sequences) or for the mode-independent Disarm (`cmd=8, body=01`, reproduced six times
across every mode and every cancel-during-exit case). The Hypothesis's *specific* claim — that the
**official Texecom Connect mobile app** would be the client whose Local Connection traffic supplied
this — was refuted: three whole-network captures found zero evidence the app ever left cloud/remote
mode on this household's setup (see Research/Results), so the prior MQTT bridge was substituted as the
capture source instead, which is a different client than the Hypothesis named, even though it
validated the same underlying mechanism. Home mode sits outside both versions of the Hypothesis
entirely, since neither the app nor the prior MQTT bridge reliably supplied it; it was closed by directly
testing the one remaining value of an already-proven-safe command, corroborated by three independent
signals (a clean ACK, an event sequence matching SPIKE-002's own independent prior observation, and
direct household confirmation via the app) rather than by capturing anyone's traffic.

This spike set out to answer one question without guessing against a live, occupied security panel:
what are the exact bytes needed to actively arm (in all three modes) and disarm this panel? That
question is now fully answered. `cmd=6` is a single shared "set arm mode" command across all three
modes, with the mode encoded in the body's first byte (`00`=Away, `01`=Night, `02`=Home for this
panel's own slot configuration); `cmd=8, body=01` disarms from any mode and also cancels an
in-progress arm during the exit delay. Away and Night were confirmed the conventional way — passive
capture of the prior MQTT bridge's own real traffic, reproduced twice and three times respectively. Home
could not be reached that way, so it was confirmed instead by directly testing the one remaining,
low-risk value in an already-validated command structure, corroborated three independent ways rather
than by a second repetition. RISK-001's send-side gap — the single hardest, highest-value unknown
blocking a working Home-arm mode — is closed.

The one genuinely new finding to carry forward is that this mapping (which slot is which mode) is
per-installation configuration, not a protocol fact this spike can generalise on its own — already
acted on via the `/correction` referenced above.

## Options

### Option A: Adopt the confirmed shared arm/disarm commands, with the mode-byte-to-HA-mode mapping sourced from per-installation configuration

The production wire-protocol client issues `cmd=6` with a configurable mode byte (defaulting to this
household's own `00`/`01`/`02` = Away/Night/Home, but overridable) and `cmd=8, body=01` for disarm
(no configuration needed — confirmed mode-independent).

- **Pros:** Directly matches everything this spike and the follow-on correction established; no
  further protocol research required to unblock Phase 2 build; keeps the app honest about which facts
  are genuinely panel-universal (the command mechanism) versus installation-specific (which byte means
  which mode).
- **Cons:** Requires a documented configuration surface (add-on option) to be designed, which is
  itself a small piece of follow-on work, not yet built.

### Option B: Hardcode this household's specific mode-byte values

Ship `00`/`01`/`02` = Away/Night/Home directly in code, matching only this panel's own configuration.

- **Pros:** Simplest possible implementation; nothing to configure.
- **Cons:** Silently wrong for any other Premier Elite installation with a different Part-Arm slot
  layout — directly contradicts the brief's now-stated goal of public Add-on distribution, and
  reintroduces exactly the kind of silent-drift risk this project has otherwise avoided (c.f.
  ADR-001's rejection of hand-maintained zone lists for the same reason).

### Option C: Treat Home as still unconfirmed pending the app/Local-Connection route

Leave Home's mode byte undetermined, blocked on either fixing the app's cloud-relay configuration or
finding another Home-capable client to passively capture.

- **Pros:** Would have kept this spike's evidentiary standard identical to Away/Night (passive capture
  only, no direct testing).
- **Cons:** Blocks Phase 2 build on an external dependency (the household's phone/app configuration)
  with no target date; the direct test already performed provides stronger evidence (three
  corroborating signals, one cross-checked against an independent prior spike) than a second passive
  capture would have added value beyond confirmation-by-repetition.

## Recommendation

**Option A.** The commands are confirmed; the remaining work (a documented configuration surface for
the mode-byte mapping) is normal Phase 2 build work, not further protocol research. Option B was
rejected during the `/correction` that followed this spike's own findings. Option C is moot — the
direct test already produced stronger evidence than continuing to wait on the app route would have.

## Decisions required

1. **Adopt `cmd=6` (mode byte in body: default `00`/`01`/`02` = Away/Night/Home for this household,
   configurable) and `cmd=8, body=01` (mode-independent disarm) as the production command set.**
   Already reflected in `docs/protocol-reference.md`.
2. **Design the add-on configuration surface for the mode-byte mapping** (e.g. three config fields, or
   a single ordered list) — not yet decided; a candidate for `/adr` once a mechanism is chosen (see
   `docs/specs/spec-alarm-control.md`'s new Constraint and Open Question).
3. **`GETAREADETAILS` (`cmd=35`) does not auto-detect Part-Arm slot roles** — exercised live
   2026-08-04; it returns area identity (`HOUSE` / `Not used B`/`C`/`D`), not Night/Home slot
   names. The Home/Night-to-slot mapping therefore remains a manual per-installation config value
   unless some other unexercised command is later found to expose it. Already reflected in
   `docs/protocol-reference.md`.

## Open questions

- Is the AREA-state-6/7 "settled per-submode" hypothesis correct, and does a hypothetical Part-Arm-3
  slot settle at state `8`, following the same pattern? Untestable on this household's panel (slot 3
  is unused here) — would need a different installation.
- What do the still-undecoded LOG event types (`1`, `3`, `31`, `41`) and the `group` byte on every
  LOG event actually represent? Type `53` now looks like a periodic remote-session marker (observed
  during idle subscribed sessions, not only app-originated arms) — still not formally named.
  None of these blocked this spike's core question.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-04 | Issues found | 2 |
| 2 | 2026-08-04 | Clear | — |
