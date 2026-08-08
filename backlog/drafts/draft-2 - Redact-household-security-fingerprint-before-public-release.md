---
id: DRAFT-2
title: Redact household security fingerprint before public release
status: Draft
assignee: []
created_date: '2026-08-08 10:00'
labels:
  - 'container:texecom-alarm-app'
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
**Background:** A full-repo review found live-install security detail in docs/spikes/captures/run scripts (zone inventory with personal names, LAN IPs/MACs, confirmed factory UDL on this panel, household automations/HomeKit/notify targets). Product code is largely clean; risk is publish exposure, not feature correctness.
**Goal:** Repo is safe to publish without revealing this household's alarm layout, credentials confirmation, or LAN topology, while keeping protocol value, ADRs, FakePanel tests, and consumer docs usable.
**Why now:** Gate before public GitHub / Add-on release (pairs with RISK-017). Do after product release-readiness work; do before making the remote broadly public.
**Out of scope / keep:** Generic "household" product language; consumer note that UDL is *usually* `1234`; FakePanel/`1234` test doubles; author/LICENSE identity unless separately decided; protocol cmd/framing facts without install fingerprint.
**Audit inventory (do not lose):**
Critical — `docs/ha-alarm-usage-spec.md`; SPIKE-001 full zone dump + login password; `docs/captures/*.pcap`; brief "Current setup" LAN topology; spike `experiment.py` IP/UDL defaults.
High — acceptance/run/cold-start personal zones + `192.0.2.10`/`1234`; spikes 002/005/006/007; protocol-reference / architecture / analysis RISK-009 "this panel still uses factory UDL"; spec-zone-monitoring Ethan example; household-ops detail in alarm/zone specs.
Medium — ADRs naming this household/Elite 88/password; handovers; git history retention after working-tree cleanse.
**Note:** Working-tree cleanse ≠ git history; history rewrite is an explicit sub-decision at execute time.
**Acceptance criteria (for /refine later — max 3):**
1. Critical/High inventory items removed or redacted (no live IPs, personal zone names, household automation map, or "this install's UDL is 1234" confirmation); pcaps deleted or replaced with anonymized excerpts.
2. Dev/spike defaults no longer point at the live panel/password; `docs/run.md` / cold-start use env-required or non-identifying placeholders; specs use fictional entity examples.
3. RISK-017 updated/closed with what remains (incl. whether git history rewrite was done); `/ship` (or publish checklist) treats residual exposure as an explicit stop/ask if anything Critical/High remains.
<!-- SECTION:DESCRIPTION:END -->
