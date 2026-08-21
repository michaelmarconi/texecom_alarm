# TODO

Product ideas and follow-ons — not committed backlog work until planned.

## Product ideas

- **HA panic / trigger button** — Expose Home Assistant’s alarm `TRIGGER` control (MQTT `payload_trigger`) so the household can initiate a panel panic/PA from HA. Blocked on proving a Connect command (or other safe path) that actually starts PA / force-trigger on the Premier Elite; today we only detect physical Silent PA zones and report live/triggered state from real alarms, with no validated network-side panic opcode.

## Before public release

- **Redact household security fingerprint** (was DRAFT-2) — Gate before public GitHub / Add-on publish (RISK-017).
  - **Working tree:** Critical + High + cheap Medium **closed** (2026-08-21).
  - **History:** **closed** (2026-08-21) — `main` rewritten; re-clone any other checkouts.
  - **Keep:** Generic “household” product language; consumer note that UDL is *usually* `1234`; FakePanel/`1234` test doubles; author/LICENSE; protocol facts without install fingerprint.
  - **Done when:** Critical/High redacted ✅; history purged ✅.
- **Store-shaped App repository (community publish path)** — Official HA Apps store won't take this; distribute as a public GitHub App repository (not HACS).
  - **Catalogue layout:** **done** — root `repository.yaml` + App in `texecom_alarm/`; apps-devcontainer dual-binds the subfolder to `local_texecom_alarm`.
  - **GHCR / `image:`:** **done** — `image: ghcr.io/michaelmarconi/texecom-alarm`; builder on `v*` tags (multi-arch).
  - **Packaging smoke (same test HA is fine):** Add the GitHub URL under App Store → Repositories; install/update that copy. Do **not** run `local_*` and the store-installed copy together (single ComIP + MQTT discovery clashes). Exercise install, options, and a version-bump Update path. Rebuild/reopen the apps container after dual-bind.
  - **Discoverability later:** README `my.home-assistant.io` add-repo link; Community forum post. Product gate remains `/accept` → `/docs` → `/ship`; store shape is packaging, not product accept.
