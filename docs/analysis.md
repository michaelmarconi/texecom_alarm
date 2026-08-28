# Analysis

<!-- Synthesised by /analyse on 2026-08-23 from: spec-alarm-control.md, spec-zone-monitoring.md, spec-panel-link-liveness.md, spec-continuous-operation.md, spec-diagnostics-logging.md, spec-startup-login-backoff.md, spec-panel-session-heal.md, spec-ready-to-arm.md -->

**Date:** 2026-08-23  
**State:** Accepted ✅

**Update note (2026-08-23):** Re-run against eight Accepted specs (adds
`spec-ready-to-arm.md`). The spec’s Spike Candidate (HA entity shape for ready
controls / blocked-arm) is **not** a genuine unknown: MQTT switch discovery is
first-party Home Assistant, and this app already publishes MQTT entities.
Dismissed — no RISK-021, no SPIKE-011. Remaining product choice (blocked-arm
signal flavour) is `/adr` or architecture, not a spike. All other Spike
Candidates re-checked. Scope remains **Medium**.

**Update note (2026-08-09):** Re-run against all seven Accepted specs (adds
`spec-panel-session-heal`). Silent-death **detection** is closed by ADR-010 /
SPIKE-008 Validated (RISK-012 downgraded). Session **heal** decisions closed in
this session (RISK-019/020): health-check timeout joins reconnect heal;
trust-degrade prefers corroboration then bounded tear-down/re-login; Connection
rename is a clean id refactor. Record heal policy via `/adr` before architecture;
align Connected→Connection wording via `/correction`. Scope remains **Medium**.

## Section 1 — Risk register

### RISK-001: Arm/disarm and triggered-event byte-level framing is unknown

| Field | Value |
|---|---|
| Source | spec-alarm-control.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | Downgraded 2026-08-04 — SPIKE-002 / SPIKE-005 Validated; ADR-008 records the production command mapping and ADR-019 (supersedes ADR-002) records the current reconnect path. Residual risk is implementation fidelity, not an open framing unknown. |
| Spike required | No (resolved 2026-08-04; was Yes) |

Originally the highest-stakes protocol unknown: no public code issued arm/disarm, and
naive attempts crashed the current add-on. That gap is closed. Build work must honour
ADR-008 (shared commands; Away = full arm; Home/Night→Part-Arm configurable).
**Resolution update (2026-08-26):** ADR-002's frame-resync/asymmetric-reconnect
portion of this risk's original closure is retired — the app no longer defends
against TX/RX collision noise in code; that's now a dedicated-module install
requirement instead. The `arm_home`/trigger framing portion (ADR-008) is
unaffected. Residual protocol fidelity is covered in CI by FakePanel; live-panel
accept-walk remains the knowing path for real-panel edge cases.

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
follow-on, not part of the resolved decision. Enumeration behaviour is exercised in
CI via FakePanel; residual cutover checks against the real ComIP remain live-only.

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
meaningful delay can be checked informally during build — those informal latency
checks are live-only (no hermetic timing stand-in claimed).

### RISK-005: Entity naming/migration decision is open in both specs

| Field | Value |
|---|---|
| Category | Requirements clarity |
| Severity | Low |
| Severity rationale | Downgraded 2026-08-08 — alarm and zone Entity ID / naming Open Questions are answered in the Accepted specs (`texecom_alarm_*` with `_zone_{N}` for zones; alarm entity ID kept). Residual cutover migration of household automations remains live-only accept work, not an open naming fork. |
| Spike required | No |

Naming is decided; cutover still needs a household migration checklist at `/accept`.
Connectivity friendly-name rename is tracked separately under RISK-013.

### RISK-006: Broad, multi-consumer regression surface with no automated safety net

| Field | Value |
|---|---|
| Category | Scope and sequencing |
| Severity | Medium |
| Severity rationale | ~40 in-use zones and one alarm entity feed aggregates and roughly 10 automations/scripts plus HomeKit — all must keep working unmodified, with no automated tests on this live security system. |
| Spike required | No |

Disciplined checklist-driven verification during build and cutover remains the
mitigation; missing an implicit consumer is a silent behaviour change, not a build
error. Multi-consumer regression against the live house is live-only / accept-walk;
hermetic FakePanel covers protocol paths in CI, not household automation wiring.

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
unbounded research bottleneck — that residual cutover/verification is live-only.

### RISK-008: Reused prior-art protocol knowledge originates from NDA-covered reverse engineering

| Field | Value |
|---|---|
| Category | Integration and external dependencies |
| Severity | Low |
| Severity rationale | The project is intended for public Add-on distribution; the brief records author confirmation that distributing the *code* is acceptable, and this project's protocol reference is written from its own live captures. |
| Spike required | No |

Keep protocol documentation empirically grounded in this project's captures and
reasoning; do not copy Texecom's NDA-covered protocol documentation into the public
repo. Public stance: [legal-stance.md](legal-stance.md). No CI stand-in applies to
this IP/compliance claim; judgment is live-only / author accept-walk at publish.

### RISK-009: Panel/ComIP authentication often still uses the factory-default password

| Field | Value |
|---|---|
| Category | Security surface |
| Severity | Low |
| Severity rationale | SPIKE-001 showed LOGIN rejects an empty UDL and accepts a configured password; panels often still use the common factory default `1234` on unaltered installs. LAN-only reachability keeps real-world exposure limited, but a known default on an alarm control plane remains worth recording (consumer docs already note this generically). |
| Spike required | No |

Neither capability spec proposes changing panel authentication. Real panel credential
behaviour is live-only knowledge; FakePanel provides a login stand-in in CI.

### RISK-010: Team capability gap in binary wire-protocol reverse engineering

| Field | Value |
|---|---|
| Category | Team capability gaps |
| Severity | Low |
| Severity rationale | Downgraded 2026-08-04 — Phase 1 capture/decode methodology is now proven in-repo (Validated spikes, living protocol reference). Residual gap is ordinary software engineering against a known protocol. |
| Spike required | No |

### RISK-011: Com Port isolation may or may not shorten trigger-time forced disconnect

| Field | Value |
|---|---|
| Source | spec-alarm-control.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | **Updated 2026-08-26:** the app no longer carries client-side protocol-collision resilience (ADR-002's resync/reconnect defense is retired) — using the panel's dedicated local-control module is now the sole mitigation for Com Port/reporting-traffic collisions, not an optional secondary alongside client-side survival. Still Low: this is a documented install requirement (ADR-013), not an open code gap. |
| Spike required | No |

SPIKE-002 confirmed the panel force-closes the TCP session on a real trigger and that
recovery is substantially longer than ordinary arm/disarm disruption — but that finding
was later shown (SPIKE-010, ADR-014) to be specific to sharing a module with alarm
reporting, not universal. The app no longer resyncs past collision noise or defends
against it in any way; isolating ARC/remote-reporting traffic onto the dedicated
local-control module is now a hard install requirement, not an optional mitigation.
A household still sharing a module accepts that risk; this app does not detect or warn
about that misconfiguration today.

### RISK-012: Silent panel-path death detection mechanism is unproven

| Field | Value |
|---|---|
| Source | spec-panel-link-liveness.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | Downgraded 2026-08-09 — SPIKE-008 Validated; ADR-010 (originally) recorded command-reject + periodic house-state poll, tens-of-seconds bound locked at **30s**. **Updated 2026-08-28:** ADR-016 supersedes ADR-010 — the periodic poll no longer feeds connectivity at all; command-reject/timeout and keepalive failure are the only two triggers. ADR-020 further narrows the keepalive-failure trigger to a configured patience window rather than an immediate degrade. Residual is live quiet-house / zombie corroboration and heal follow-ons (RISK-019), not an open detection fork. |
| Spike required | No (resolved 2026-08-09; was Yes) |

Detection is decided and largely built. Live corroboration remains accept-walk;
session heal after degrade/dead-keepalive is RISK-019 / `spec-panel-session-heal`.

### RISK-013: Connectivity rename may need unique_id / Entity ID change

| Field | Value |
|---|---|
| Source | spec-panel-link-liveness.md § Spike Candidates; also spec-panel-session-heal.md § Spike Candidates |
| Category | Requirements clarity |
| Severity | Low |
| Severity rationale | Settled 2026-08-09 — clean refactor: friendly name **Alarm Panel Connection** and change `unique_id` / Entity ID as needed; no backwards-compat soft path. Ordinary plan/build + `/correction` to align older Connected wording. |
| Spike required | No |

Discovery unit tests assert the new name/ids; live cutover may need entity reset /
automation retarget. No research spike.

### RISK-014: Part-Arm config surface still allows Away (lags ADR-008)

| Field | Value |
|---|---|
| Category | Requirements clarity |
| Severity | Medium |
| Severity rationale | Accepted `spec-alarm-control` and ADR-008 forbid Away on Part-Arm options; a live incident already showed Away-on-slot yields wrong panel mode and false MQTT `disarmed`. Schema/defaults not yet aligned. |
| Spike required | No |

Ordinary plan/build work: remove Away from Part-Arm radios (Home/Night/Unused only),
ensure Away always uses full-arm mode byte, migrate live options. FakePanel/unit
tests claim mode-byte selection; live Away arm is accept-walk.

### RISK-015: Continuous operation / startup backoff residual vs live ComIP contention

| Field | Value |
|---|---|
| Category | Integration and external dependencies |
| Severity | Low |
| Severity rationale | Accepted continuous-operation and startup-login-backoff specs name FakePanel for CI; residual uncertainty is only live ComIP contention timing under real Supervisor, which the specs already label optional manual corroboration. |
| Spike required | No |

Hermetic FakePanel covers login-fail-then-succeed and backoff intervals. Live
contention corroboration remains live-only / accept-walk.

### RISK-016: Diagnostics TRACE live hunt is live-only

| Field | Value |
|---|---|
| Category | Integration and external dependencies |
| Severity | Low |
| Severity rationale | Diagnostics-logging ACs 1–6 name unit/integration + FakePanel; AC7 (correlate TRACE with a known live zone event) is honest live-only and does not block hermetic coverage of the logging contract. |
| Spike required | No |

### RISK-017: Repository contains live household security fingerprint

| Field | Value |
|---|---|
| Category | Security surface |
| Severity | Low |
| Severity rationale | Working-tree Critical/High inventory closed (2026-08-21) and `main` history rewritten the same day (`git filter-repo` + force-push). Residual risk is copies of the old history on other clones/forks — re-clone after the rewrite. |
| Spike required | No |

**Closed 2026-08-21:** Critical/High items redacted or removed from the tree; household
usage spec deleted; brief/acceptance/spikes/ADRs/tests/cold-start/experiment defaults
cleansed; captures remain gitignored. History rewrite purged LAN IPs, personal notify
targets, and related fingerprint strings from reachable `main` commits; `docs/ha-alarm-usage-spec.md`
removed from history.

### RISK-018: Post-alarm disarm may require a dedicated ResetArea command (cmd 9)

| Field | Value |
|---|---|
| Source | Protocol research candidate (cmd 9); related open product question in ADR-002 / SPIKE-002 (“alarm reset” as a signal) |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | Downgraded 2026-08-23 — ADR-008 already records mode-independent disarm (cmd 8); ADR-013 records that HA Disarm during a live alarm is expected to work on the dedicated local module (ordinary disarm unsets). Cmd 9 is not a production prerequisite on that path. Residual is optional SmartCom-era curiosity and the separate ADR-002 “alarm reset” *signal* product question. |
| Spike required | No (closed 2026-08-23; was Yes) |

Production disarm-when-triggered is cmd 8 on the dedicated local module (ADR-013, ADR-008).
Do not treat ResetArea (cmd 9) as an open production decision. A dedicated HA “alarm reset”
entity/signal remains an ADR-002 stop — ask a human before that product path. Provisional
cmd-9 protocol notes may stay in [protocol-reference.md](protocol-reference.md) as
historical; FakePanel need not model cmd 9 for the current disarm contract.

### RISK-019: Mid-run session heal / re-login policy not yet in an ADR

| Field | Value |
|---|---|
| Source | spec-panel-session-heal.md § Spike Candidates |
| Category | Scope and sequencing |
| Severity | Medium |
| Severity rationale | Accepted heal spec requires no manual restart after dead health-check or stuck trust-degrade; ADR-010 left tear-down/re-login open and live keepalive timeout aborted the listen loop. Without a recorded ADR, architecture cannot lock the mechanism. |
| Spike required | No |

**Session decisions (2026-08-09) — record via `/adr` before `/architecture` Update:**

1. Unanswered mid-run health-check → same keep-trying reconnect heal as clean
   disconnect (connection signal OFF while recovering; live + re-sync after).
2. Trust-degrade heal → corroboration first; tear down and re-login only if still
   stuck after a bounded fail window (bound at plan/ADR time; auto-retry of the
   failed arm/disarm tap remains out of scope).

FakePanel must cover fail-then-heal shapes in CI; live zombie/heal corroboration
remains accept-walk. Patient retry cadence is now settled by ADR-011 (command-
rejection fail window) and ADR-020 (check-in patience window) as two separate,
unmerged install-time settings — not the retired ADR-002 reconnect budgets.

### RISK-020: Panel-link-liveness naming still says Connected

| Field | Value |
|---|---|
| Category | Requirements clarity |
| Severity | Low |
| Severity rationale | Two Accepted specs disagree on the household label until `/correction` propagates **Alarm Panel Connection** from `spec-panel-session-heal` into `spec-panel-link-liveness` and downstream docs. |
| Spike required | No |

Ordinary `/correction` (and constitute/architecture follow-through). No spike.

### Categories scanned and clear of additional entries

Team capability gaps beyond RISK-010: none new. Security surface: RISK-009 (panel
factory-default UDL) and RISK-017 (repo publish fingerprint) are recorded; ready-to-arm
does not add a new auth boundary. Performance beyond RISK-004: none new. MQTT broker and HA
Supervisor Add-on Store remain ordinary standing dependencies with known contracts. How we'll
know on `spec-ready-to-arm` ACs 1–7 name FakePanel / fake MQTT client; AC8 is honest
manual HomeKit/iOS.

## Section 2 — Dismissed candidates

| Item | Source | Rationale |
|---|---|---|
| Whether the new integration can expose the alarm as a more natively-modeled HA alarm (removing the `house_alarm_panel` wrapper) vs keeping two-layer architecture | spec-alarm-control.md § Spike Candidates | Covered by ADR-003 — MQTT discovery from an App; wrapper collapse is not this app's decision |
| Exact byte-level command framing for `arm_home` / surviving triggered events without TX/RX collision crash | spec-alarm-control.md § Spike Candidates | Covered by ADR-008 (confirmed shared arm/disarm; Away full arm) and ADR-013/ADR-019 (dedicated module + single-interval reconnect, supersede ADR-002's frame-resync/asymmetric-reconnect); SPIKE-002 and SPIKE-005 Validated |
| Whether/how the Texecom Connect protocol supports enumerating the zone list programmatically | spec-zone-monitoring.md § Spike Candidates | Covered by ADR-001 — dynamic panel enumeration; SPIKE-001 Validated |
| Whether `GETAREADETAILS` (`cmd=35`) exposes each Part-Arm slot's configured name/role | spec-alarm-control.md § Spike Candidates | Not a genuine open unknown — exercised live 2026-08-04; returns area identity only, not Part-Arm roles; Home/Night→slot remains manual install mapping (Away is full arm, not a Part-Arm option) |
| Whether a stable numeric panel serial can be read for device/`unique_id` namespacing | spec-zone-monitoring.md § Spike Candidates | Not required by Accepted zone-monitoring — zone-stable `unique_id` without panel serial is the decided scheme; serial remains optional later, not a current unknown to spike |
| How to detect silent panel-path death reliably… | spec-panel-link-liveness.md § Spike Candidates | Covered by ADR-016 (supersedes ADR-010) — command-reject/timeout + keepalive failure, narrowed by ADR-020's patience window; SPIKE-008 Validated (was RISK-012) |
| Whether renaming the friendly name alone is enough… vs `unique_id` / Entity ID | spec-panel-link-liveness.md § Spike Candidates | Settled 2026-08-09 with heal-spec rename — clean refactor to **Alarm Panel Connection** including id change; RISK-013 / RISK-020 |
| How mid-run health-check timeout should join clean-disconnect recovery | spec-panel-session-heal.md § Spike Candidates | Settled 2026-08-09 — treat as dead session; same keep-trying reconnect heal; RISK-019 → `/adr` then build (no spike) |
| Whether trust-degrade heal requires session tear-down / re-login | spec-panel-session-heal.md § Spike Candidates | Settled 2026-08-09 — corroboration first; tear-down/re-login if stuck after bounded window; RISK-019 → `/adr` (no spike) |
| Whether Connection rename needs unique_id / Entity ID change | spec-panel-session-heal.md § Spike Candidates | Settled 2026-08-09 — yes, clean refactor; no backwards compat (RISK-013) |
| How the three ready controls and the blocked-arm signal should appear as ordinary Home Assistant entities | spec-ready-to-arm.md § Spike Candidates | Not a genuine unknown — MQTT switch discovery is first-party HA and this app already publishes MQTT entities; honouring on/off before arm is ordinary subscribe-and-gate. Blocked-arm signal flavour (e.g. event) is a small `/adr` or architecture choice, not a spike |

**Note:** Com Port isolation remains RISK-011 (not dismissed). Continuous-operation,
diagnostics-logging, and startup-login-backoff have no Spike Candidates sections;
residuals are RISK-015 / RISK-016.

## Section 3 — Ordered spike list

No new research spikes for session heal (decisions recorded; `/adr` then architecture/build).
No spike for ready-to-arm entity shape (dismissed — known MQTT switch discovery).
No active research spike: SPIKE-009 closed 2026-08-23 (ADR-013 / ADR-008). SPIKE-008 is
complete (below). Historical spikes remain for traceability.

### Historical spikes (complete or dismissed — retained for traceability)

### SPIKE-008: Prove silent panel-path death detection without false degraded flaps — Validated ✅

| Field | Value |
|---|---|
| Resolves | RISK-012 |
| Depends on | None |
| Outcome | ADR-016 (supersedes ADR-010) |

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
| Outcome | ADR-019 (supersedes ADR-002, via ADR-014) |

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
| Outcome | ADR-008 (supersedes ADR-005) |

### SPIKE-009: Validate ResetArea (cmd 9) before disarm when the panel is in alarm — Closed ✅

| Field | Value |
|---|---|
| Resolves | RISK-018 |
| Depends on | SPIKE-005 (disarm framing known); preferably after a controlled trigger (SPIKE-002) |
| Outcome | Closed 2026-08-23 — not a production unknown. ADR-008 records cmd 8 disarm; ADR-013 records HA Disarm during live alarm on the dedicated local module. Cmd 9 is SmartCom-era follow-on at most, not a required send-path. |

**Closed — no further experiment required for production disarm-when-triggered.** See RISK-018.

### SPIKE-006: Startup zone-state snapshot read — Validated ✅

| Field | Value |
|---|---|
| Resolves | Startup re-sync (parked after ADR-001) |
| Depends on | SPIKE-001 |
| Outcome | ADR-006 |

### SPIKE-007: Startup area-flags / alarm-state snapshot read — Validated ✅

| Field | Value |
|---|---|
| Resolves | Alarm startup re-sync (parked after ADR-006) |
| Depends on | SPIKE-006 |
| Outcome | ADR-009 (supersedes ADR-007) |

## Review

| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-01 | Clear | — |
| 2 | 2026-08-04 | Clear | — |
| 3 | 2026-08-08 | Issues found | 8 |
| 4 | 2026-08-08 | Clear | — |
| 5 | 2026-08-08 | Clear | — |
| 6 | 2026-08-08 | Clear | — |
| 7 | 2026-08-09 | Issues found | 1 |
| 8 | 2026-08-09 | Clear | — |
| 9 | 2026-08-23 | Issues found | 2 |
| 10 | 2026-08-23 | Clear | — |
