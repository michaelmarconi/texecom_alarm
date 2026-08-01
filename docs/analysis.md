# Analysis

<!-- Synthesised by /analyse on 2026-08-01 from: spec-alarm-control.md, spec-zone-monitoring.md -->

**Date:** 2026-08-01  
**State:** Accepted ✅

Scope calibration: this is a single-household, self-built integration with no
external/customer-facing surface — on its face "small scope." However, it carries
elevated technical risk atypical of small internal projects: an undocumented
binary wire protocol, a physical hardware dependency requiring in-person capture
work, and a documented crash pattern (suspected TX/RX collision) that must be
avoided at the protocol/timing level with no ability to patch the panel firmware
or the previous closed-source core. This register is therefore calibrated to
**Medium scope** (moderate bar; ~5–10 risks, 2–5 spikes) rather than Small.

## Section 1 — Risk register

### RISK-001: Arm/disarm and triggered-event byte-level framing is unknown

| Field | Value |
|---|---|
| Source | spec-alarm-control.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | High |
| Severity rationale | This blocks the single hardest and highest-value goal (a working, non-crashing Home-arm mode) and the highest-stakes acceptance criterion (surviving a real alarm trigger without crashing); no prior art (including the cited `davidMbrooke/texecom-connect` decoder) implements arm/disarm, so this is being derived from first principles against a live panel. |
| Spike required | Yes |

No existing public code implements `arm_home`/`part_arm_2` framing or reliably
surviving/reporting a `triggered` event; the only fact known today is that a
naive attempt crashes the current add-on. Getting this wrong risks either
building on top of an unstable framing (recreating the same crash bug in the new
app) or under-investigating the collision-avoidance timing needed for the
"survive an actual alarm trigger" acceptance criterion.

### RISK-002: Two-layer vs. collapsed HA entity architecture is undecided

| Field | Value |
|---|---|
| Source | spec-alarm-control.md § Spike Candidates |
| Category | Scope and sequencing |
| Severity | Medium |
| Severity rationale | This is a genuine architectural fork (keep the raw-entity + template-wrapper split, or model the alarm more natively and retire the wrapper) that changes what phase 2 actually builds and what migration work `configuration/templates/house_alarm.yaml` needs — deciding it late risks rework of already-built entities. |
| Spike required | Yes |

Whether the replacement should expose a more natively-modeled HA alarm (removing
the need for the `house_alarm_panel` template wrapper) or preserve today's
two-layer split is still open. Because the wrapper currently carries all the
guard-condition/notification logic that is explicitly out of scope to touch, the
"right" answer materially affects migration risk and effort — this should be
decided deliberately, not implicitly by whatever the build happens to produce.

### RISK-003: Programmatic zone-list enumeration capability is unknown

| Field | Value |
|---|---|
| Source | spec-zone-monitoring.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | Medium |
| Severity rationale | If the protocol cannot enumerate zones programmatically, all ~35 zones (door/window/shock/PIR/other, including co-located sensor pairs) must be hand-specified and hand-maintained in configuration, which is a materially larger and more error-prone build than dynamic discovery, and raises the chance of a silently missing zone against the "must not regress the dashboard" goal. |
| Spike required | Yes |

Whether the Texecom Connect protocol supports enumerating zones (count, type,
name) versus requiring the ~35-entry inventory to be manually transcribed into
config is unresolved. This directly shapes the zone-monitoring build's shape and
maintenance burden.

### RISK-004: 2-second zone-state latency target is unvalidated against protocol/timing constraints

| Field | Value |
|---|---|
| Category | Performance and scale assumptions |
| Severity | Medium |
| Severity rationale | The 2-second constraint is stated as a hard requirement (it underpins the 60s auto-arm motion-cancel and the "I'm leaving" front-door wait) but no evidence yet shows what update latency the protocol can sustain safely — and the fastest possible polling/query cadence is exactly the axis suspected of triggering the current add-on's TX/RX collision crash, so "fast enough" and "safe enough" may be in tension. |
| Spike required | Yes |

There's no established basis yet for how quickly zone state can be queried or
pushed without approaching the timing conditions that are suspected to cause the
current add-on's crash pattern. Resolving RISK-001's protocol/timing findings
first is a prerequisite to answering this with evidence rather than guesswork.

### RISK-005: Entity naming/migration decision is open in both specs

| Field | Value |
|---|---|
| Category | Requirements clarity |
| Severity | Medium |
| Severity rationale | Both specs flag this as an explicit Open Question with an owner and a "resolve before Phase 2 build starts" deadline; if left open, phase 2 development on either capability cannot proceed without guessing at a decision that has direct downstream effects on `configuration/templates/house_alarm.yaml` and every automation/script/dashboard/HomeKit binding listed in `docs/ha-alarm-usage-spec.md`. |
| Spike required | No |

Both `spec-alarm-control.md` and `spec-zone-monitoring.md` leave open whether new
entity IDs must exactly match today's `alarm_control_panel.texecom_alarm_arm_status`
/ `binary_sensor.texecom_alarm_*` naming, or whether a documented rename/migration
is acceptable. This is a decision for the household/spec author, not an
investigation — no spike resolves it, but it should be closed out before phase 2
build work starts on either capability, consistent with what both specs already
say.

### RISK-006: Broad, multi-consumer regression surface with no automated safety net

| Field | Value |
|---|---|
| Category | Scope and sequencing |
| Severity | Medium |
| Severity rationale | ~35 zone entities and one alarm entity feed at least 3 aggregate template sensors and roughly 10 distinct automations/scripts (auto-arm, auto-disarm, guest-mode, "I'm leaving"/"cancel leaving", garage integration, blinds, windows/VELUX auto-close, house-number light, two HomeKit bridges, notifications) — all of which must keep working unmodified per both specs' acceptance criteria, and none of which appear to have automated tests today (this is a live household system). |
| Spike required | No |

The regression checklist in `docs/ha-alarm-usage-spec.md` is large and the
consequence of missing an implicit dependency (e.g. an aggregate or automation
that references a zone entity name/state in a way not captured in the inventory)
is a silent behavior change in a live security system — not a build error. This
is a genuine scope-management risk rather than a technology unknown, and doesn't
require investigation so much as disciplined checklist-driven verification during
build and cutover.

### RISK-007: Phase 1 is single-point, in-person, and disruptive with no fixed timeline

| Field | Value |
|---|---|
| Category | Scope and sequencing |
| Severity | Medium |
| Severity rationale | Phase 2 cannot start until Phase 1 fully decodes zone state, arm/disarm, and trigger events for all three arm modes; Phase 1 requires physically triggering sensors and deliberately setting off the alarm in the house, and the brief gives no schedule or fallback if this stretches out, so the entire project's critical path runs through a manual, disruptive, hard-to-parallelize activity. |
| Spike required | No |

This is an already-acknowledged constraint in the brief, but it is worth naming
explicitly as a risk in its own right: because arm/disarm and trigger-event
capture require deliberately setting off a live house alarm and physically
operating every door/window/PIR, this work can't be delegated, rushed, or done
remotely, and any slip here delays everything downstream. No spike resolves this
— it's a scheduling/resourcing risk to track, not an unknown to investigate.

### RISK-008: Reused prior-art protocol knowledge originates from NDA-covered reverse engineering

| Field | Value |
|---|---|
| Category | Integration and external dependencies |
| Severity | Low |
| Severity rationale | The cited `davidMbrooke/texecom-connect` decoder was developed under an NDA with Texecom, and while the brief notes the author confirmed that distributing the *code* (not Texecom's protocol docs) is acceptable, that confirmation is referenced informally (a claim in the brief) rather than as a recorded, checkable artifact (e.g. a license file, an issue comment link, written permission) — and this project's own protocol notes/capture decodes could inadvertently mix in NDA-derived documentation details rather than just the reverse-engineered code. |
| Spike required | No |

Since the project is not being published (explicit non-goal), real-world legal
exposure is low, and the brief already records the author's confirmation. This
is flagged as a low-severity residual item mainly so the empirically-verified
protocol documentation this project produces (a stated Goal) is written up from
this project's own packet captures and reasoning, not by copying Texecom's
NDA-covered protocol documentation.

### RISK-009: Panel/ComIP interface has no authentication configured

| Field | Value |
|---|---|
| Category | Security surface |
| Severity | Low |
| Severity rationale | The brief records `udl_password` as unset on the panel today; this is a pre-existing condition the new integration inherits rather than introduces, and the panel is only reachable over the household LAN (no external exposure noted), but an unauthenticated control-plane for an alarm system is worth recording rather than silently carrying forward. |
| Spike required | No |

Neither spec proposes adding authentication, and doing so isn't in scope for
either capability (arm/disarm and zone-monitoring specs both focus on
functional parity, not hardening). Recorded here so the decision to leave this
as-is is visible rather than an unexamined default.

### RISK-010: Team capability gap in binary wire-protocol reverse engineering

| Field | Value |
|---|---|
| Category | Team capability gaps |
| Severity | Medium |
| Severity rationale | Decoding an undocumented binary protocol from packet captures (framing, CRC, command IDs) is a specialized skill; the brief gives no indication the household has prior experience with this specific kind of work, though it does have a real methodology head-start via the cited prior-art repos (`davidMbrooke/texecom-connect`, `shuckc/pytexalarm`, `RoganDawes/WintexProtocol`). |
| Spike required | No |

This is a capability risk to be aware of going into Phase 1, not something a
spike resolves on its own — Phase 1 itself *is* the mitigation (hands-on capture
and decode against the cited references). Flagged so that if Phase 1 stalls, the
underlying cause (skills gap vs. protocol difficulty vs. tooling) can be
diagnosed rather than assumed.

## Section 2 — Dismissed candidates

No specs contained a Spike Candidates item that is dismissed. All three
`## Spike Candidates` items found across the two specs (the arm_home/triggered
framing, the wrapper-architecture choice, and zone-list enumeration) were
surfaced as risks above — see RISK-001, RISK-002, and RISK-003 respectively —
none were covered by an existing accepted ADR (there are no ADRs yet in
`docs/adrs/`) and none were judged to be non-genuine.

## Section 3 — Ordered spike list

### SPIKE-001: Determine whether zones can be enumerated programmatically

| Field | Value |
|---|---|
| Resolves | RISK-003 |
| Depends on | None |
| Sequencing rationale | This is the lowest-risk, read-only starting point for Phase 1 protocol work — it establishes the packet-capture/decode methodology and tooling (building on the existing `davidMbrooke/texecom-connect` zone/status decoder, which already works) before moving on to the higher-risk command/control direction of the protocol. |

Capture and decode zone-status/enumeration traffic against the live panel to
determine whether zone count, type, and identity can be read programmatically,
versus requiring the ~35-zone inventory to be hand-specified in configuration. A
good output is a documented answer plus, if enumeration is supported, the
specific command/response framing needed to retrieve it.

### SPIKE-002: Decode arm_home and triggered-event framing without inducing the collision crash

| Field | Value |
|---|---|
| Resolves | RISK-001 |
| Depends on | SPIKE-001 |
| Sequencing rationale | This spike reuses the capture/decode methodology and tooling established in SPIKE-001, but moves to the harder and higher-stakes command/control direction of the protocol (arm/disarm framing, and the timing/sequencing needed to avoid the suspected TX/RX collision bug) — the project's two hardest goals (working Home mode, and surviving a real trigger without crashing) both depend on this. |

Capture and decode the byte-level command framing for `arm_home` (`part_arm_2`)
and for a full triggered-alarm event (siren activation through to reset),
specifically looking for the timing/sequencing conditions implicated in the
current add-on's TX/RX collision crash. A good output is a documented,
empirically-verified command/response sequence for both, plus concrete
collision-avoidance timing guidance (e.g. minimum inter-command gaps, safe
polling cadence) for the app to follow.

### SPIKE-003: Establish the safe achievable zone-state update latency

| Field | Value |
|---|---|
| Resolves | RISK-004 |
| Depends on | SPIKE-001, SPIKE-002 |
| Sequencing rationale | Latency can only be measured meaningfully once the actual protocol mechanics for reading zone/status state (SPIKE-001) and the collision-avoidance timing constraints uncovered while decoding commands (SPIKE-002) are known — testing polling/event frequency against the 2-second target before that would risk re-triggering the exact crash pattern this project needs to avoid. |

Using the framing and collision-avoidance findings from SPIKE-001/SPIKE-002,
empirically test how quickly zone state can be refreshed (via polling frequency
or push events, whichever the protocol supports) while staying clear of the
collision-crash conditions. A good output is a documented safe update cadence
that meets or explicitly falls short of the 2-second target in
`spec-zone-monitoring.md`, with the gap flagged if it falls short.

### SPIKE-004: Decide two-layer vs. collapsed HA alarm entity architecture

| Field | Value |
|---|---|
| Resolves | RISK-002 |
| Depends on | SPIKE-002 |
| Sequencing rationale | This is a downstream design decision, not a protocol unknown — it's best made once SPIKE-002 confirms exactly which arm states/commands (including the previously-unsupported Home mode) are actually available to model, so the architecture choice is grounded in what the panel can really do rather than made speculatively. |

Decide whether the replacement should expose a more natively-modeled HA alarm
(e.g. via MQTT `alarm_control_panel` discovery covering all real panel states)
in a way that could retire the `house_alarm_panel` template-wrapper layer, or
whether to preserve today's two-layer split. A good output is a documented
decision (candidate for an ADR) plus, if collapsing the wrapper is chosen, an
explicit migration plan for the guard-condition/notification logic that
currently lives in `configuration/templates/house_alarm.yaml`.

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-01 | Clear | — |
