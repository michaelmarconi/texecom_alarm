# ADR-019: Use a Single Reconnect Interval and No Line-Noise Defense for Panel Disconnects

**Status:** ~~Accepted~~ Superseded by [ADR-021](adr-021-use-one-busy-versus-dead-session-model-for-panel-connection-health.md)
**Date:** 2026-08-26
**Supersedes:** ADR-014

## Overview

**Background:** The app currently carries two defenses built for a household sharing a
communication module between Home Assistant and the panel's own alarm-reporting path:
it skips over unexpected, non-alarm-protocol bytes instead of treating them as an error,
and it waits notably longer to reconnect after a real alarm trigger than after an
everyday disconnect. Both exist only because, on a shared module, the panel's reporting
subsystem can inject noise and disconnects around exactly those events.
**Decision:** Retire both defenses. The app now assumes it is always reached over the
panel's dedicated local-control module — already a hard install requirement — and treats
any unexpected data on that connection as a fault to reconnect from, using one configured
wait interval no matter what caused the disconnect.
**Why this way:** Keeping two reconnect speeds and a byte-skipping parser alive only
protects installs still sharing a module against the setup guidance, or households that
haven't yet corrected it. This household has decided it will not carry that ongoing
complexity to protect an install choice it considers a misconfiguration, not a case the
app should keep quietly working around.
**What this constrains:**
- Unexpected or non-conforming data on the panel connection must be treated as a fault
  that triggers a reconnect, not something to skip past and keep parsing.
- Reconnecting after any panel disconnect uses one configured wait interval; the cause of
  the disconnect (an everyday drop vs. one following a real trigger) no longer selects a
  different interval.
- Add-on configuration must expose a single reconnect-wait setting, not separate
  "everyday" and "trigger" interval settings.
- Product documentation must not describe the app as tolerating a shared or
  misconfigured module — that stays an install prerequisite, not a runtime
  accommodation.
- The app must keep retrying a dropped panel connection indefinitely regardless of this
  change — nothing here reopens a stop condition on reconnect attempts.
**Open follow-ons:**
- None.

## Context

ADR-002 built two defenses against panel-firmware behaviour observed on the installer's
shared signalling module: skip-and-continue framing for a second, non-Connect-protocol
byte stream, and a longer reconnect wait specifically for the disconnect a real trigger
caused. ADR-014 kept both unconditionally after discovering the original observations
came from the wrong module — the correctly configured dedicated module didn't reproduce
either behaviour — reasoning that other households might still be pointed at the wrong
module and deserved the protection regardless. The household running this app has since
decided it does not want to carry that protection for other, unverified installs; it
treats using the dedicated module (ADR-013) as the fix for that scenario, not something
this app should keep defending against at runtime. This reverses the specific trade-off
ADR-014 made, without touching ADR-013 itself or the unconditional "keep retrying
forever" reconnect guarantee (ADR-004 / ADR-011 / ADR-018).

This decision also narrows ADR-018: ADR-018's removal of the reconnect "attempts"
settings and its indefinite-retry requirement both stand unchanged; only its position
that "the wait interval may vary by disconnect type" is superseded here in favour of one
interval for every disconnect.

## Decision drivers

- The household no longer wants runtime complexity whose sole purpose is protecting
  installs that share a module with the panel's alarm-reporting path.
- The dedicated-module requirement (ADR-013) is a documented, enforced setup
  prerequisite — the app does not also need to independently defend against installs
  that ignore it.
- The add-on's configuration surface should keep shrinking to settings that materially
  change behaviour (the same goal ADR-018 already acted on).
- The change must not weaken the existing "never give up reconnecting" guarantee — only
  how the wait interval is chosen may change, not whether or how long the app keeps
  retrying.

## Options considered

- **Option A: Leave ADR-014 unchanged** — keep frame-resync and the asymmetric
  reconnect interval unconditionally. Rejected because: the household has explicitly
  decided it will not carry this cost to protect installs it doesn't control, and the
  dedicated-module requirement is the intended fix for that scenario, not a runtime
  workaround this app should keep maintaining.
- **Option B (chosen): Retire frame-resync and merge the two reconnect intervals into
  one**, treating the dedicated module as a hard prerequisite with no runtime
  accommodation for a shared or misconfigured one.
- **Option C: Retire only one of the two defenses** (drop frame-resync but keep the
  asymmetric interval, or vice versa). Rejected because: both exist for the same root
  cause — a shared or misconfigured module — and keeping one without the other leaves
  inconsistent protection while still not achieving the household's stated goal of
  removing this class of complexity entirely.

## Decision

Chosen option: **Option B.**

This is the only option that directly satisfies the household's decision to stop
carrying this cost (driver 1), relies on the already-documented install requirement
instead of a runtime workaround (driver 2), reduces the reconnect-interval config
surface to one setting (driver 3), and leaves the indefinite-retry guarantee completely
untouched (driver 4).

## Consequences

**Positive:** The wire-protocol client no longer needs a byte-scanning resync loop, and
reconnect logic and configuration drop from two interval settings (plus the disconnect-
type classification that chooses between them) to one. This is a real reduction in code
paths and in the number of add-on settings a household has to understand.

**Negative:** A household whose Home Assistant connection later ends up sharing a module
with the panel's alarm-reporting path — through misconfiguration or a setup mistake — no
longer gets graceful handling: unexpected bytes now cause a hard reconnect cycle instead
of being silently skipped, and the app will not wait any longer specifically after a real
trigger even though that scenario could plausibly take longer to clear on a shared
module. This knowingly reopens the exposure ADR-014 was written to keep closed for
installs other than this one.

**Follow-on:** Implementation removes the frame-resync byte-scanning path from the wire
client, collapses the two reconnect-interval settings into one, and updates
`docs/architecture.md`'s frame-resync and protocol-collision-recovery material and its CI
stand-in description to match. `docs/architecture.md` cannot correctly reflect this
decision until it is updated via `/architecture` after this ADR is folded into
`AGENTS.md` via `/constitute`.

**CI vs live:** A stand-in panel and hermetic tests can fully prove the new behaviour:
that an unexpected/non-frame byte sequence now causes a reconnect rather than being
skipped, that exactly one reconnect-wait interval exists and is used for every
disconnect regardless of cause, and that the reconnect loop still retries indefinitely
per ADR-004/ADR-011/ADR-018. Whether this changes anything in practice on the household's
own panel remains live-only corroboration — production traffic on the dedicated module
is not expected to contain this noise in the first place (SPIKE-010), so the expectation
is no observable behaviour change there, but that expectation itself is not a CI claim.

## Confirmation

This decision is correctly implemented when: (1) the wire-protocol client contains no
resync/skip path — any unexpected byte sequence is treated as a session fault that
triggers reconnect, not something scanned past; (2) exactly one reconnect-wait-interval
setting exists in the add-on's config schema and runtime settings, applied to every
disconnect regardless of cause; and (3) the reconnect loop still retries a dropped
connection indefinitely per ADR-004/ADR-011/ADR-018, with no behavioural change to that
guarantee.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
