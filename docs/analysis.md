# Analysis

<!-- Synthesised by /analyse on 2026-08-31 from: spec-alarm-control.md, spec-zone-monitoring.md, spec-panel-link-liveness.md, spec-continuous-operation.md, spec-diagnostics-logging.md, spec-startup-login-backoff.md, spec-panel-session-heal.md, spec-ready-to-arm.md -->

**Date:** 2026-08-31  
**State:** Accepted ✅

Medium-scope register. Closed IDs stay so spec-candidate backlinks and `docs/spikes/` `Resolves:` lines still resolve. Spike reports live under `docs/spikes/`; this file does not reprint them.

## Section 1 — Risk register

### RISK-001: Arm/disarm and triggered-event byte-level framing is unknown

| Field | Value |
|---|---|
| Source | spec-alarm-control.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | Closed — SPIKE-002 / SPIKE-005 Validated; ADR-008 is the production mapping. Residual is implementation fidelity, not an open framing unknown. |
| Spike required | No |

FakePanel covers protocol paths in CI. Real-panel edge cases stay live-only / accept-walk. Do not restore client-side skip-and-resync; the dedicated local module is the install requirement (ADR-013).

### RISK-002: Two-layer vs. collapsed HA entity architecture is undecided

| Field | Value |
|---|---|
| Source | spec-alarm-control.md § Spike Candidates |
| Category | Scope and sequencing |
| Severity | Low |
| Severity rationale | Dismissed — the project is an App + MQTT discovery path (ADR-003); collapsing the household wrapper was never this app’s decision. |
| Spike required | No |

### RISK-003: Programmatic zone-list enumeration capability is unknown

| Field | Value |
|---|---|
| Source | spec-zone-monitoring.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | Closed — SPIKE-001 Validated; ADR-001 requires dynamic discovery. Residual is implementation fidelity plus the still-open cached-fallback follow-on. |
| Spike required | No |

Unused slots must not become entities. A last-known-good cached zone list at startup is an ADR-001 open follow-on — ask a human before building it. Enumeration in CI is FakePanel; real ComIP cutover is live-only.

### RISK-004: 2-second zone-state latency target is unvalidated against protocol/timing constraints

| Field | Value |
|---|---|
| Category | Performance and scale assumptions |
| Severity | Low |
| Severity rationale | Dismissed — push ZONE events have no client-tunable poll; household automations tolerate multi-second slack. |
| Spike required | No |

Informal latency checks during live use are live-only. No hermetic timing stand-in is claimed.

### RISK-005: Entity naming/migration decision is open in both specs

| Field | Value |
|---|---|
| Category | Requirements clarity |
| Severity | Low |
| Severity rationale | Closed — Accepted specs lock `texecom_alarm_*` naming. Residual is household automation retarget at `/accept`, not an open naming fork. |
| Spike required | No |

Naming is decided; cutover still needs a household migration checklist at `/accept`.

### RISK-006: Broad, multi-consumer regression surface with no automated safety net

| Field | Value |
|---|---|
| Category | Scope and sequencing |
| Severity | Medium |
| Severity rationale | ~40 in-use zones and one alarm entity feed aggregates, roughly 10 automations/scripts, and HomeKit — all must keep working unmodified, with no automated tests on the live house. |
| Spike required | No |

FakePanel covers protocol paths in CI, not household automation wiring. Missing an implicit consumer is a silent behaviour change. Cutover regression is live-only / accept-walk.

### RISK-007: Phase 1 is single-point, in-person, and disruptive with no fixed timeline

| Field | Value |
|---|---|
| Category | Scope and sequencing |
| Severity | Low |
| Severity rationale | Closed as a research bottleneck — SPIKE-001 / 002 / 005 Validated. Residual in-person work is cutover, still disruptive, not an unbounded decode path. |
| Spike required | No |

That residual cutover/verification is live-only.

### RISK-008: Reused prior-art protocol knowledge originates from NDA-covered reverse engineering

| Field | Value |
|---|---|
| Category | Integration and external dependencies |
| Severity | Low |
| Severity rationale | Brief records that distributing *this* project’s code is acceptable; the protocol reference is written from this project’s own captures. |
| Spike required | No |

Do not copy Texecom’s NDA-covered protocol documentation into the public repo. Stance: [legal-stance.md](legal-stance.md). No CI stand-in applies; publish judgment is live-only / author accept-walk.

### RISK-009: Panel/ComIP authentication often still uses the factory-default password

| Field | Value |
|---|---|
| Category | Security surface |
| Severity | Low |
| Severity rationale | LOGIN rejects an empty UDL and accepts a configured password; many panels still use factory `1234`. LAN-only reachability limits exposure; a known default on an alarm control plane remains worth recording. |
| Spike required | No |

This app does not change panel authentication. FakePanel is the CI login stand-in; real credential behaviour is live-only.

### RISK-010: Team capability gap in binary wire-protocol reverse engineering

| Field | Value |
|---|---|
| Category | Team capability gaps |
| Severity | Low |
| Severity rationale | Closed — capture/decode methodology is proven in-repo. Residual is ordinary engineering against a known protocol. |
| Spike required | No |

### RISK-011: Com Port isolation may or may not shorten trigger-time forced disconnect

| Field | Value |
|---|---|
| Source | spec-alarm-control.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | Not an open code gap — dedicated local-control module is a hard install requirement (ADR-013). Residual is whether a given install is actually on that module, and whether trigger-time disconnect still occurs there. |
| Spike required | No |

The app does not detect or warn about sharing a module with alarm reporting. CI does not stand in for module topology — FakePanel cannot prove Com Port isolation or a shared-module misconfiguration. Whether a given install is on the dedicated local module, and whether trigger-time disconnect still occurs there, remains live-only / accept-walk.

### RISK-012: Silent panel-path death detection mechanism is unproven

| Field | Value |
|---|---|
| Source | spec-panel-link-liveness.md § Spike Candidates |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | Closed as a detection fork — SPIKE-008 Validated. Command-reject/timeout and check-in failure (patience window, not one miss) are the triggers; the reconciliation poll does not feed Connection. |
| Spike required | No |

Quiet-house / zombie corroboration remains live-only / accept-walk. Heal after death is RISK-019.

### RISK-013: Connectivity rename may need unique_id / Entity ID change

| Field | Value |
|---|---|
| Source | spec-panel-link-liveness.md § Spike Candidates; also spec-panel-session-heal.md § Spike Candidates |
| Category | Requirements clarity |
| Severity | Low |
| Severity rationale | Settled — friendly name **Alarm Panel Connection**; change ids as needed; no backwards-compat soft path. |
| Spike required | No |

Discovery tests assert the new name/ids. Live cutover may need entity reset / automation retarget (accept-walk).

### RISK-014: Part-Arm config surface still allows Away (lags ADR-008)

| Field | Value |
|---|---|
| Category | Requirements clarity |
| Severity | Low |
| Severity rationale | Closed in shipping schema — Part-Arm radios are Home / Night / Unused only; Away is full arm. Residual is live Away-arm accept-walk, not an open config fork. |
| Spike required | No |

FakePanel/unit tests claim mode-byte selection. Do not put Away back on a Part-Arm option.

### RISK-015: Continuous operation / startup backoff residual vs live ComIP contention

| Field | Value |
|---|---|
| Category | Integration and external dependencies |
| Severity | Low |
| Severity rationale | Specs name FakePanel for CI; residual is live ComIP contention timing under real Supervisor, already labelled optional manual corroboration. |
| Spike required | No |

Hermetic FakePanel covers login-fail-then-succeed and backoff. Live contention remains live-only / accept-walk.

### RISK-016: Diagnostics TRACE live hunt is live-only

| Field | Value |
|---|---|
| Category | Integration and external dependencies |
| Severity | Low |
| Severity rationale | ACs 1–6 are unit/integration + FakePanel; AC7 (correlate TRACE with a known live zone event) is honest live-only and does not block hermetic coverage of the logging contract. |
| Spike required | No |

### RISK-017: Repository contains live household security fingerprint

| Field | Value |
|---|---|
| Category | Security surface |
| Severity | Low |
| Severity rationale | Working-tree Critical/High inventory closed 2026-08-21; `main` history rewritten the same day. Residual is copies of the old history on other clones/forks. |
| Spike required | No |

Re-clone after the rewrite. Do not put LAN IPs, personal notify targets, or household zone names back into the tree or into consumer docs.

### RISK-018: Post-alarm disarm may require a dedicated ResetArea command (cmd 9)

| Field | Value |
|---|---|
| Source | Protocol research candidate (cmd 9); related open product question in ADR-002 / SPIKE-002 (“alarm reset” as a signal) |
| Category | Technology unknowns |
| Severity | Low |
| Severity rationale | Closed for production disarm — ADR-008 cmd 8; ADR-013 HA Disarm during a live alarm on the dedicated local module. Cmd 9 is not a production prerequisite. |
| Spike required | No |

Do not treat ResetArea as an open production decision. A dedicated HA “alarm reset” entity/signal remains an ADR-002 stop — ask a human before that product path. FakePanel need not model cmd 9 for the current disarm contract.

### RISK-019: Mid-run session heal still needs live corroboration

| Field | Value |
|---|---|
| Source | spec-panel-session-heal.md § Spike Candidates |
| Category | Scope and sequencing |
| Severity | Medium |
| Severity rationale | Heal-without-restart and Connection on/off rules are specified; CI can cover FakePanel shapes, but quiet-house / zombie / garage-return torn-frame behaviour is live-only and still the accept gap. |
| Spike required | No |

Heal without a human restart is required. **Alarm Panel Connection** stays on through the health-check patience window and through a first-attempt re-login after a successful command whose later housekeeping read did not parse. It goes off only when we cannot talk (hung up, end of session, patience exceeded, or a refused/timed-out arm or disarm). Do not silently re-issue a failed arm or disarm. Check-in patience and the command-reject fail window stay separate. FakePanel must cover fail-then-heal in CI; it must not be treated as proof that a refusing session starts answering again without re-login, or that a real torn-frame stays quiet on Connection.

### RISK-020: Panel-link-liveness naming still says Connected

| Field | Value |
|---|---|
| Category | Requirements clarity |
| Severity | Low |
| Severity rationale | Closed 2026-08-31 — `spec-panel-link-liveness` now uses **Alarm Panel Connection**, matching the heal spec and shipping discovery. |
| Spike required | No |

### Categories scanned and clear of additional entries

Team capability gaps beyond RISK-010: none. Security surface: RISK-009 and RISK-017. Performance beyond RISK-004: none. MQTT broker and HA Supervisor Add-on Store are ordinary standing dependencies. `spec-ready-to-arm` ACs 1–7 name FakePanel / fake MQTT client; AC8 is honest manual HomeKit/iOS.

## Section 2 — Dismissed candidates

| Item | Source | Rationale |
|---|---|---|
| Native HA alarm vs two-layer wrapper | spec-alarm-control.md § Spike Candidates | Covered by ADR-003 — MQTT discovery from an App; wrapper collapse is not this app’s decision |
| Byte-level `arm_home` / trigger framing without TX/RX collision crash | spec-alarm-control.md § Spike Candidates | Covered by ADR-008 (commands; Away = full arm) and ADR-013 (dedicated module). SPIKE-002 / SPIKE-005 Validated. Do not restore skip-and-resync. Com Port residual is RISK-011, not dismissed. |
| Programmatic zone-list enumeration | spec-zone-monitoring.md § Spike Candidates | Covered by ADR-001; SPIKE-001 Validated. Cached-fallback follow-on stays an ADR-001 stop (RISK-003). |
| `GETAREADETAILS` (cmd 35) Part-Arm slot names/roles | spec-alarm-control.md § Spike Candidates | Not a genuine unknown — live 2026-08-04: area identity only, not Part-Arm roles. Home/Night→slot stays install mapping. |
| Stable numeric panel serial for `unique_id` | spec-zone-monitoring.md § Spike Candidates | Not required — zone-stable `unique_id` is the decided scheme. |
| Silent panel-path death detection | spec-panel-link-liveness.md § Spike Candidates | SPIKE-008 Validated. Detection closed (RISK-012). |
| Friendly-name rename vs `unique_id` / Entity ID | spec-panel-link-liveness.md § Spike Candidates | Settled — **Alarm Panel Connection** including id change (RISK-013). Spec wording aligned 2026-08-31 (RISK-020 closed). |
| Mid-run health-check timeout vs clean-disconnect recovery | spec-panel-session-heal.md § Spike Candidates | Same keep-trying reconnect heal once the session is declared dead. Unanswered check-in starts patience; Connection off only after that window (RISK-019). |
| Trust-degrade heal: tear-down / re-login? | spec-panel-session-heal.md § Spike Candidates | Corroboration first; tear-down if still stuck after the command-reject window. Do not auto-retry the failed tap (RISK-019). |
| Connection rename needs unique_id / Entity ID change | spec-panel-session-heal.md § Spike Candidates | Yes — clean refactor, no backwards compat (RISK-013). |
| Ready controls and blocked-arm as ordinary HA entities | spec-ready-to-arm.md § Spike Candidates | Not a genuine unknown — MQTT switch discovery plus a blocked-arm event. Household rules stay in HA automations. |

Specs with no Spike Candidates section: `spec-continuous-operation.md`, `spec-diagnostics-logging.md`, `spec-startup-login-backoff.md` (residuals RISK-015 / RISK-016).

## Section 3 — Ordered spike list

No spikes required. All identified risks are low or medium residual, or already addressed by existing ADRs. Validated/closed spike reports remain under `docs/spikes/`.

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
| 11 | 2026-08-31 | Issues found | 1 |
| 12 | 2026-08-31 | Clear | — |

