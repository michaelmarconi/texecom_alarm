# ADR-023: Use Ordinary Home Assistant Disarm Without a Separate Reset for a Sounding Alarm

**Status:** Accepted ✅  
**Date:** 2026-09-01  
**Spike:** [spike-009-ha-disarm-after-alarm/SPIKE.md](../spikes/spike-009-ha-disarm-after-alarm/SPIKE.md)

## Overview

**Background:** An early live run concluded that tapping Disarm in Home Assistant
does not stop a sounding alarm, and that people should use the keypad or the
vendor app instead. That run was on the installer signalling box. Later walks
on the dedicated local box, and repeated use of the current add-on, show Disarm
from Home Assistant does stop the sirens. The panel may still show that an
alarm happened until someone resets it at the keypad. That leftover reminder
does not stop the house working as usual.
**Decision:** Keep a single ordinary Disarm from Home Assistant as the way to
stop a sounding alarm when the add-on is on the dedicated local box. Do not add
a separate panel Reset command, and do not treat leftover alarm memory on the
keypad as a product defect.
**Why this way:** Declaring Home Assistant Disarm unsupported would describe the
wrong box and contradict how the current add-on is actually used. Automatically
re-sending Disarm after a drop would re-press a tap the household already saw
fail. Wiring a Reset command because the keypad still wants a reset would add
an unproven extra command for something that does not matter in practice.
**What this constrains:**
- Do not treat Home Assistant Disarm during a live alarm as unsupported when the
  add-on is on the dedicated local box.
- Do not add a separate panel Reset command as a required product path. Ordinary
  Disarm is enough to stop the alarm.
- Leftover on-panel alarm memory after a successful Disarm is acceptable. Do not
  build a Reset feature to clear it.
- The early “Disarm did nothing while sirens ran” run is installer-box evidence,
  not the product rule. Wrong box can still drop the link (ADR-013).
- FakePanel must not claim that Home Assistant Disarm fails to stop a live alarm
  on the dedicated local box, or that a Reset command is required.
**Open follow-ons:** None. Whether some other panel command could clear alarm
memory remains untested and is not needed for this decision.

## Context

SPIKE-009 asked whether tapping Disarm in Home Assistant stops a sounding
alarm. The 2026-08-21 run refuted that on the installer signalling module: the
session dropped at trigger, Disarm did not ACK, and the keypad had to unset and
reset. The spike recommended documenting Home Assistant Disarm as not that path
(Option A), and leaving Reset unwired until a run reached the panel while it
was in alarm.

ADR-013 later recorded that Home Assistant must use the dedicated local
network module. SPIKE-010 on that module kept the link up through a live alarm
and Home Assistant Disarm worked. The practitioner override on 2026-09-01:
the current add-on has repeatedly disarmed a sounding alarm; it does not reset
the panel; that leftover does not matter in practice because the panel
continues to work as usual. This is not an open product issue.

Unchanged: one confirmed Disarm for every arm mode (ADR-008); entities stay
visible through a panel-link problem (ADR-004); busy-versus-dead session health
including late command replies (ADR-022); dedicated local module (ADR-013).

## Decision drivers

- Home Assistant Disarm during a live alarm must be a supported path when the
  add-on is on the dedicated local module — matching later live walks and
  current add-on use, not the installer-box run.
- A leftover keypad reminder that an alarm happened must not force a new
  command family if the panel otherwise continues to work as usual.
- Do not silently re-send a Disarm the household already saw fail (ADR-022).
- Do not wire an unused Reset command from keypad-reset folklore or from a
  command list that has never been captured on this panel.
- FakePanel may prove ordinary Disarm while a session is logged in. A real
  siren-then-Disarm walk, and that leftover alarm memory is acceptable, remain
  live-only.

## Options considered

- **Option A: Keypad/app stop a live alarm; Home Assistant Disarm is not that
  path** — ship SPIKE-009’s recommendation. Rejected because: it fails the
  “supported on the dedicated local module” driver; that run was the installer
  box (ADR-013); current add-on use repeatedly Disarms a sounding alarm.
- **Option B: Retry the last Disarm after reconnect** — automatically re-send a
  tap that happened while the link was down. Rejected because: it fails the
  “do not silently re-send a failed tap” driver.
- **Option C: Send Reset as well as Disarm** — add a separate Reset command
  because the keypad still wanted a reset after unset. Rejected because: it
  fails the “leftover reminder must not force a new command” driver and the
  “do not wire an unused Reset” driver; Reset has not been captured on this
  panel, and leftover memory does not matter in practice.
- **Option D: Ordinary Home Assistant Disarm; no separate Reset** — one Disarm
  stops a sounding alarm on the dedicated local module; keypad alarm memory
  after that is acceptable.

## Decision

Chosen option: **Option D — ordinary Home Assistant Disarm; no separate Reset**

This keeps Disarm during a live alarm as a supported path on the dedicated
local module, refuses to turn SPIKE-009’s installer-box failure into product
policy, and leaves Reset out of the app because leftover panel alarm memory
does not stop the house working as usual.

## Consequences

**Positive:** Agents and reviews will not revive “HA cannot stop a sounding
alarm” as a shipping rule. Reset stays out of scope unless a later decision
reopens it. SPIKE-009 is covered as evidence of the wrong box, not as the
live product path.

**Negative:** The keypad may still show that an alarm happened after Home
Assistant Disarm. Households that want that reminder cleared must do it at the
keypad. FakePanel cannot prove a real siren-then-Disarm, or that leftover
memory is acceptable.

**Follow-on:** None. ADR-013 remains the install rule for which network box to
use. Do not treat this ADR as a licence to target the installer box.

**CI vs live:** FakePanel tests **may** claim: ordinary Disarm while a session
is logged in; a trigger can force-disconnect and leave MQTT triggered with
Connection off when the stand-in models a hang-up. They **may not** claim:
that Home Assistant Disarm fails to stop live sirens on the dedicated local
module; that a Reset command is required or sufficient; that leftover keypad
alarm memory is a product defect the app must clear. `/accept` live walks
remain: Disarm from Home Assistant during a real alarm on the dedicated local
module actually unsets; leftover keypad alarm memory after that is acceptable.

## Confirmation

Hermetic FakePanel tests keep proving ordinary Disarm on a live session and
must not assert that Disarm-from-triggered fails or that Reset is required.
`/accept` live walks remain: a real alarm then Home Assistant Disarm on the
dedicated local module stops the sirens; the app does not send Reset; leftover
keypad alarm memory is not treated as a failure.

## Review
