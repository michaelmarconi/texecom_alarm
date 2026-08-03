# Spike: arm-disarm-command-framing

**Resolves:** RISK-001 / SPIKE-005
**Date:** 2026-08-03
**Type:** Feasibility
**State:** Draft 📝

## Overview

**Question:** Whether a safe, non-guessing way exists to determine the exact command needed to issue `arm_away`/`arm_night`/`arm_home`/`disarm` to this panel, ending with a concrete, ready-to-implement command sequence rather than just a research writeup.
**Answer:** pending experiment
**Recommendation:** —
**Decisions this unlocks:**
—

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

## Experiment Design

This is a **Feasibility** experiment in two parts: a physical/network capture step the practitioner
must perform on-site (mirroring the hands-on nature of SPIKE-001/SPIKE-002's physical zone/arm
actions), and an offline decode step this project's own code performs against the resulting
capture file.

**Part A — capture (practitioner-executed, on the household LAN):**

1. Configure the official Texecom Connect app on a household phone for **Local Connection**
   per `INS273-7 §6.1`, pointing at `192.168.1.183:10001` (the same panel/port already confirmed
   live in SPIKE-001/002) — no push notifications / remote/cloud mode needed for this test.
2. Set up a passive capture of that phone's traffic to `192.168.1.183:10001`, in order of
   preference: (a) LAN switch/router port mirroring if the hardware supports it; (b) an
   ARP-spoofing-based on-path capture (e.g. `arpspoof`/`ettercap` + `tcpdump` from a laptop already
   on the LAN) if not; (c) 802.11 monitor-mode capture with WPA decryption (using the household's
   own known Wi-Fi passphrase in Wireshark) as a last resort if the phone is Wi-Fi-only and neither
   (a) nor (b) is practical. Save the result as a `.pcap`/`.pcapng` file filtered to TCP port
   `10001`.
3. During the capture window, using the app (not the wall keypad, so every action is captured on
   the wire): arm to **Home**, wait ~15s, disarm; then arm to **Away**, wait, disarm; then arm to
   **Night**, wait, disarm — each cycle repeated twice, matching SPIKE-002's own "reproduced twice"
   bar for treating a finding as confirmed rather than a one-off.
4. This spike does **not** repeat SPIKE-002's live-trigger test — that side of RISK-001 is already
   Validated. This spike is scoped strictly to the still-open **issuing** gap.

**Part B — offline decode (this repo's own code, `experiment.py`):**

A standalone Python 3 script, reimplemented from first principles (not importing GPL/Apache prior
art directly, per RISK-008 — consistent with SPIKE-001/002's own approach), that:

1. Reads the `.pcap`/`.pcapng` file produced by Part A using a minimal stdlib-only reader (no new
   third-party dependency) and reconstructs the TCP byte stream in each direction between the
   phone's IP and `192.168.1.183:10001`.
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
| Captured app traffic is plaintext Connect-protocol framing, not AES-encrypted | Decoded frames match the known header structure (`'t'` start byte, valid CRC-8) for at least the majority of the capture | — |
| A Home-mode arm via the app produces a decoded outbound command frame | Command byte + body captured, reproducible across both captured Home-arm cycles | — |
| Away-mode arm produces a decoded outbound command frame distinct from Home's | Command byte + body captured, reproducible across both cycles, and distinguishable from the Home-mode command | — |
| Night-mode arm produces a decoded outbound command frame distinct from the other two | Command byte + body captured, reproducible across both cycles, and distinguishable from Home/Away | — |
| Disarm produces a decoded outbound command frame | Command byte + body captured, reproducible across all six disarm actions (two per arm mode) | — |
| The captured command fits the already-implemented frame structure with no undocumented fields | Command decodes cleanly under the same `{start, type, length, seq, body, CRC-8}` structure already used for `LOGIN`/`GETZONEDETAILS`/etc. — no additional envelope or encoding discovered | — |

*Actuals are populated from experiment output only — not from documentation, vendor claims, or community reports.*

## Results

## Conclusion

## Options

### Option A: {name}

### Option B: {name}

### Option C: {name}

## Recommendation

## Decisions required

## Open questions
