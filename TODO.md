# TODO

Product ideas and follow-ons — not committed backlog work until planned.

## Product ideas

- **HA panic / trigger button** — Expose Home Assistant’s alarm `TRIGGER` control (MQTT `payload_trigger`) so the household can initiate a panel panic/PA from HA. Blocked on proving a Connect command (or other safe path) that actually starts PA / force-trigger on the Premier Elite; today we only detect physical Silent PA zones and report live/triggered state from real alarms, with no validated network-side panic opcode.

## Before public release

- **Redact household security fingerprint** (was DRAFT-2) — Gate before public GitHub / Add-on publish (RISK-017). Product code is largely clean; risk is docs/spikes/captures/run scripts exposing this install.
  - **Goal:** Safe to publish without revealing alarm layout, credential confirmation, or LAN topology; keep protocol value, ADRs, FakePanel tests, and consumer docs usable.
  - **Keep:** Generic “household” product language; consumer note that UDL is *usually* `1234`; FakePanel/`1234` test doubles; author/LICENSE unless decided separately; protocol facts without install fingerprint.
  - **Critical inventory:** `docs/ha-alarm-usage-spec.md`; SPIKE-001 full zone dump + login password; `docs/captures/*.pcap`; brief “Current setup” LAN topology; spike `experiment.py` IP/UDL defaults.
  - **High:** acceptance/run/cold-start personal zones + live IP/`1234`; spikes 002/005/006/007; protocol-reference / architecture / analysis RISK-009 “this panel still uses factory UDL”; spec-zone-monitoring Ethan example; household-ops detail in alarm/zone specs.
  - **Medium:** ADRs naming this household/Elite 88/password; handovers; git history after working-tree cleanse (history rewrite is an explicit sub-decision at execute time).
  - **Done when:** Critical/High redacted or removed; dev/spike defaults and `docs/run.md` / cold-start use env-required or non-identifying placeholders; fictional entity examples in specs; RISK-017 updated/closed; `/ship` stops if Critical/High residual remains.
  - **Re-enter backlog:** `/plan` Update or `/refine` when ready to execute — not a blocker for product `/accept`.
- **Store-shaped App repository (community publish path)** — Official HA Apps store won't take this; distribute as a public GitHub App repository (not HACS). Today the repo is **local-app** layout (`config.yaml` at root → `local_texecom_alarm` via apps-devcontainer mount). Strangers need **catalogue** layout: root `repository.yaml` + app in a subfolder with its own `config.yaml`/`Dockerfile`. Prefer pre-built multi-arch images (GHCR + HA builder) and `image:` in `config.yaml`; local-build-from-git is OK only for early interest.
  - **Day-to-day:** Keep fast local by mounting the *app subfolder* as `apps/local/…` (or keep iterating on current local layout until packaging).
  - **Packaging smoke (same test HA is fine):** Add the GitHub URL under App Store → Repositories; install/update that copy. Do **not** run `local_*` and the store-installed copy together (single ComIP + MQTT discovery clashes). Exercise install, options, and a version-bump Update path.
  - **Discoverability later:** README `my.home-assistant.io` add-repo link; Community forum post. Product gate remains `/accept` → `/docs` → `/ship`; store shape is packaging, not product accept.
