# TODO

Product ideas and follow-ons — not committed backlog work until planned.

## Product ideas

- **HA panic / trigger button** — Expose Home Assistant’s alarm `TRIGGER` control (MQTT `payload_trigger`) so the household can initiate a panel panic/PA from HA. Blocked on proving a Connect command (or other safe path) that actually starts PA / force-trigger on the Premier Elite; today we only detect physical Silent PA zones and report live/triggered state from real alarms, with no validated network-side panic opcode.

## Before public release

- **Redact household security fingerprint** (was DRAFT-2) — Gate before public GitHub / Add-on publish (RISK-017).
  - **Working tree:** Critical + High + cheap Medium **closed** (2026-08-21) — household usage spec deleted; brief/acceptance/spikes/ADRs/architecture/analysis/tests/cold-start/experiment defaults cleansed; TEST-NET / env-required placeholders; captures remain gitignored.
  - **Keep:** Generic “household” product language; consumer note that UDL is *usually* `1234`; FakePanel/`1234` test doubles; author/LICENSE; protocol facts without install fingerprint.
  - **Track 3 (open):** git history may still contain pre-cleanse fingerprint — rewrite is an explicit sub-decision; not claimed closed by the working-tree pass.
  - **Done when (tree):** Critical/High redacted or removed ✅; `/ship` RISK-017 row may pass for working tree with history noted pending.
- **Store-shaped App repository (community publish path)** — Official HA Apps store won't take this; distribute as a public GitHub App repository (not HACS). Today the repo is **local-app** layout (`config.yaml` at root → `local_texecom_alarm` via apps-devcontainer mount). Strangers need **catalogue** layout: root `repository.yaml` + app in a subfolder with its own `config.yaml`/`Dockerfile`. Prefer pre-built multi-arch images (GHCR + HA builder) and `image:` in `config.yaml`; local-build-from-git is OK only for early interest.
  - **Day-to-day:** Keep fast local by mounting the *app subfolder* as `apps/local/…` (or keep iterating on current local layout until packaging).
  - **Packaging smoke (same test HA is fine):** Add the GitHub URL under App Store → Repositories; install/update that copy. Do **not** run `local_*` and the store-installed copy together (single ComIP + MQTT discovery clashes). Exercise install, options, and a version-bump Update path.
  - **Discoverability later:** README `my.home-assistant.io` add-repo link; Community forum post. Product gate remains `/accept` → `/docs` → `/ship`; store shape is packaging, not product accept.
