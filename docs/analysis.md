# Analysis

<!-- Synthesised by /analyse on 2026-08-04 from: spec-alarm-control.md, spec-zone-monitoring.md -->

**Date:** 2026-08-04  
**State:** Accepted ✅

**Update note (2026-08-04):** Re-run against the public-Add-on brief, Accepted ADRs
001–005, Validated SPIKE-001/002/005, and the current Spike Candidates in both
specs (including Com Port isolation and the resolved GETAREADETAILS item). Scope
calibration remains **Medium**: still an undocumented panel protocol and a live
security system, now also with a public distribution surface — but the original
High protocol unknowns (arm/disarm send path, zone enumeration, collision crash)
are closed.

## Section 1 — Risk register

### RISK-001: Arm/disarm and triggered-event byte-level framing is unknown

| Field | Value |
|---|---|
| Source | spec-alarm-control.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | Downgraded 2026-08-04 — SPIKE-002 Validated the observation-side arm/trigger framing and the collision/forced-disconnect crash mechanism (ADR-002); SPIKE-005 Validated the send-side Away/Night/Home/Disarm commands with configurable Part-Arm mapping (ADR-005). Residual risk is ordinary implementation fidelity against the recorded protocol reference, not an open framing unknown. |
| Spike required | No (resolved 2026-08-04; was Yes) |

Originally the highest-stakes protocol unknown: no public code issued arm/disarm, and
naive attempts crashed the current add-on. That gap is closed. Build work must still
honour ADR-002 (frame resync + asymmetric reconnect) and ADR-005 (shared commands +
configurable mode mapping); those are implementation constraints, not open research.

### RISK-002: Two-layer vs. collapsed HA entity architecture is undecided

| Field | Value |
|---|---|
| Source | spec-alarm-control.md § Spike Candidates |
| Category | Scope and sequencing |
| Severity | Low |
| Severity rationale | Downgraded 2026-08-02 — see Dismissal rationale below. Originally a genuine architectural fork; the premise was removed once the project committed to an App + MQTT discovery path. |
| Spike required | No (dismissed 2026-08-02, was Yes) |

**Dismissal rationale (2026-08-02):** Raised during a `/spike 004` interview, before any
experiment was designed. The project is an HA App (add-on), not a native
`custom_components` integration, so MQTT discovery is the only entity-surfacing
mechanism (later recorded as ADR-003). Household guard-condition/notification logic
stays in the HA config layer by non-goal, so collapsing the wrapper was never this
app's decision. MQTT `alarm_control_panel` schema support for the needed states is
first-party HA documentation, not a wire-protocol unknown.

### RISK-003: Programmatic zone-list enumeration capability is unknown

| Field | Value |
|---|---|
| Source | spec-zone-monitoring.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | Downgraded 2026-08-04 — SPIKE-001 Validated full zone enumeration against the live panel; ADR-001 records dynamic discovery as the required approach. Residual risk is implementation fidelity and the still-open cached-fallback follow-on, not whether enumeration works. |
| Spike required | No (resolved 2026-08-04; was Yes) |

The panel reports zone count, type, and name programmatically. Unused slots must not
become HA entities. The ComIP single-connection constraint shapes cutover. A
last-known-good cached zone list at startup remains an explicit ADR-001 open
follow-on, not part of the resolved decision.

### RISK-004: 2-second zone-state latency target is unvalidated against protocol/timing constraints

| Field | Value |
|---|---|
| Category | Performance and scale assumptions |
| Severity | Low |
| Severity rationale | Downgraded 2026-08-02 — see Dismissal rationale below. Push-based ZONE events have no client-tunable poll cadence; consumers tolerate multi-second slack. |
| Spike required | No (dismissed 2026-08-02, was Yes) |

**Dismissal rationale (2026-08-02):** SPIKE-001/002 establish unsolicited push delivery
via `SETEVENTMESSAGES`. Downstream consumers (60s auto-arm cancel; door-transition
waits) do not need sub-2-second precision. Whether ADR-002 resync/reconnect ever adds
meaningful delay can be checked informally during build.

### RISK-005: Entity naming/migration decision is open in both specs

| Field | Value |
|---|---|
| Category | Requirements clarity |
| Severity | Medium |
| Severity rationale | Both specs still flag this as an explicit Open Question with a "resolve before Phase 2 build starts" deadline; guessing wrong affects every automation/script/dashboard/HomeKit binding in `docs/ha-alarm-usage-spec.md`. |
| Spike required | No |

Whether new entity IDs must exactly match today's
`alarm_control_panel.texecom_alarm_arm_status` / `binary_sensor.texecom_alarm_*`
naming, or a documented rename/migration is acceptable, remains a household/spec-author
decision — not an investigation.

### RISK-006: Broad, multi-consumer regression surface with no automated safety net

| Field | Value |
|---|---|
| Category | Scope and sequencing |
| Severity | Medium |
| Severity rationale | ~40 in-use zones and one alarm entity feed aggregates and roughly 10 automations/scripts plus HomeKit — all must keep working unmodified, with no automated tests on this live security system. |
| Spike required | No |

Disciplined checklist-driven verification during build and cutover remains the
mitigation; missing an implicit consumer is a silent behaviour change, not a build
error.

### RISK-007: Phase 1 is single-point, in-person, and disruptive with no fixed timeline

| Field | Value |
|---|---|
| Category | Scope and sequencing |
| Severity | Low |
| Severity rationale | Downgraded 2026-08-04 — the critical Phase 1 protocol spikes (001, 002, 005) are Validated and covered by ADRs. Residual in-person work is cutover/regression exercise and optional ops probes (e.g. Com Port layout), not a blocked decode path. |
| Spike required | No |

The original critical-path risk was that Phase 2 could not start until arm/disarm and
trigger framing were decoded. That gate is open. Remaining physical work is
verification and cutover against a live house, still disruptive but no longer an
unbounded research bottleneck.

### RISK-008: Reused prior-art protocol knowledge originates from NDA-covered reverse engineering

| Field | Value |
|---|---|
| Category | Integration and external dependencies |
| Severity | Low |
| Severity rationale | The project is now intended for public Add-on distribution, which slightly raises exposure versus the earlier non-publish framing, but the brief still records author confirmation that distributing the *code* is acceptable, and this project's protocol reference is written from its own live captures. |
| Spike required | No |

Keep protocol documentation empirically grounded in this project's captures and
reasoning; do not copy Texecom's NDA-covered protocol documentation into the public
repo.

### RISK-009: Panel/ComIP authentication uses the factory-default password

| Field | Value |
|---|---|
| Category | Security surface |
| Severity | Low |
| Severity rationale | SPIKE-001 showed the panel requires the factory-default UDL password `1234`, not an empty credential as the brief originally stated; LAN-only reachability keeps real-world exposure limited, but a known default on an alarm control plane remains worth recording. |
| Spike required | No |

Neither capability spec proposes changing panel authentication. Recorded so the
"authenticated with a known default" fact is visible rather than the earlier
"unauthenticated" misstatement.

### RISK-010: Team capability gap in binary wire-protocol reverse engineering

| Field | Value |
|---|---|
| Category | Team capability gaps |
| Severity | Low |
| Severity rationale | Downgraded 2026-08-04 — Phase 1 capture/decode methodology is now proven in-repo (three Validated spikes, living protocol reference). Residual gap is ordinary software engineering against a known protocol, not first-principles reverse engineering. |
| Spike required | No |

### RISK-011: Com Port isolation may or may not shorten trigger-time forced disconnect

| Field | Value |
|---|---|
| Source | spec-alarm-control.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | ADR-002 already requires the client to survive protocol collisions and asymmetric reconnect after a forced disconnect; whether installer-level Com Port / reporting isolation also shortens that outage is an optional secondary mitigation, not a correctness dependency for Phase 2. |
| Spike required | No |

SPIKE-002 confirmed the panel force-closes the TCP session on a real trigger and that
recovery is substantially longer than ordinary arm/disarm disruption. Isolating ARC
or remote-reporting traffic from the Com Port used by this app might reduce how often
or how long that happens — or might not. The app must not assume isolation eliminates
the outage (ADR-004 stop condition). Investigate only if residual household pain after
shipping resilient reconnect warrants an installer-level experiment.

### Categories scanned and clear of additional entries

Integration and external dependencies beyond RISK-008 (MQTT broker, HA Supervisor
Add-on Store) are ordinary standing dependencies with known contracts — no separate
risk entry. Requirements clarity beyond RISK-005 is adequately specified in the two
Accepted specs.

## Section 2 — Dismissed candidates

| Item | Source | Rationale |
|---|---|---|
| Whether the new integration can expose the alarm as a more natively-modeled HA alarm (removing the `house_alarm_panel` wrapper) vs keeping two-layer architecture | spec-alarm-control.md § Spike Candidates | Covered by ADR-003 — MQTT discovery from an App; wrapper collapse is not this app's decision |
| Exact byte-level command framing for `arm_home` / surviving triggered events without TX/RX collision crash | spec-alarm-control.md § Spike Candidates | Covered by ADR-002 (frame resync + asymmetric reconnect) and ADR-005 (confirmed shared arm/disarm commands); SPIKE-002 and SPIKE-005 Validated |
| Whether/how the Texecom Connect protocol supports enumerating the zone list programmatically | spec-zone-monitoring.md § Spike Candidates | Covered by ADR-001 — dynamic panel enumeration; SPIKE-001 Validated |
| Whether `GETAREADETAILS` (`cmd=35`) exposes each Part-Arm slot's configured name/role | spec-alarm-control.md § Spike Candidates | Not a genuine open unknown — exercised live 2026-08-04; returns area identity only, not Part-Arm roles; ADR-005 already requires manual per-installation mapping |

**Note:** Com Port isolation is surfaced as RISK-011 above (not dismissed), with no
spike required unless residual outage pain warrants an installer experiment.

## Section 3 — Ordered spike list

No spikes required. All identified risks that needed investigation are resolved
(SPIKE-001, SPIKE-002, SPIKE-005) or dismissed without experiment (SPIKE-003,
SPIKE-004). Remaining risks are Low/Medium decisions or cutover discipline that do
not need advance research spikes.

### Historical spikes (complete or dismissed — retained for traceability)

### SPIKE-001: Determine whether zones can be enumerated programmatically — Validated ✅

| Field | Value |
|---|---|
| Resolves | RISK-003 |
| Depends on | None |
| Outcome | ADR-001 |

### SPIKE-002: Decode arm_home and triggered-event framing without inducing the collision crash — Validated ✅

| Field | Value |
|---|---|
| Resolves | RISK-001 (observation / crash path) |
| Depends on | SPIKE-001 |
| Outcome | ADR-002 |

### SPIKE-003: ~~Establish the safe achievable zone-state update latency~~ — Dismissed 2026-08-02

| Field | Value |
|---|---|
| Resolves | RISK-004 |
| Depends on | SPIKE-001, SPIKE-002 |

**Dismissed — no experiment run.** See RISK-004.

### SPIKE-004: ~~Decide two-layer vs. collapsed HA alarm entity architecture~~ — Dismissed 2026-08-02

| Field | Value |
|---|---|
| Resolves | RISK-002 |
| Depends on | SPIKE-002 |

**Dismissed — no experiment run.** See RISK-002; ADR-003 later recorded the App/MQTT path.

### SPIKE-005: Decode send-side arm/disarm command framing — Validated ✅

| Field | Value |
|---|---|
| Resolves | RISK-001 (send path) |
| Depends on | SPIKE-002 |
| Outcome | ADR-005 |

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-01 | Clear | — |
| 2 | 2026-08-04 | Clear | — |
