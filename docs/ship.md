# Ship

**Date:** 2026-09-01
**State:** Draft 📝
<!-- Terminals: N/A | Accepted ✅ | Deferred ⏸️ -->
**Applicability:** yes

## Checklist

Risk-scaled for a LAN panel App (UDL + MQTT credentials in Supervisor options; no internet-facing API). Pen-test not warranted.

| Item | Status | Notes |
|------|--------|-------|
| Docs-ready Accepted | pass | `docs/docs-ready.md` Accepted 2026-08-27 |
| Product accept | pass | `docs/acceptance.md` Accepted 2026-09-01; iOS arm/disarm on the local module published `arming` → `armed_away` → `disarmed` with Connection still on. Household HA card walk still required as live smoke |
| Secrets in runtime config | pass | Unchanged: UDL / MQTT username+password are Supervisor options (`password` schema) |
| Secrets hygiene (captures) | pass | `docs/captures/` gitignored; no pcaps in tree |
| Support path | pass | GitHub issues (templates), `SECURITY.md`, `CONTRIBUTING.md` |
| Observability | pass | `log_level` WARNING/INFO/DEBUG/TRACE; session lifecycle in app logs; decode-miss logs reason + leading hex; process start logs the add-on version at INFO |
| CI security scans | pass | `bandit` + `pip-audit` in `.github/workflows/ci.yml` |
| Backups | n/a | No extra datastore; HA backup of add-on options is sufficient |
| Official HA Apps store | n/a | Community GitHub repository is the intended path |
| Store-shaped repository | pass | Root `repository.yaml` + App in `texecom_alarm/`; store URL uses generated `#app` branch |
| Pre-built images (GHCR) | pass | `0.3.4` published (`docker manifest inspect` amd64 + arm64; Builder run 33528827986) |
| RISK-017 fingerprint | pass | Working tree + history rewrite complete (recorded 2026-08-23) |
| CHANGELOG vs product | pass | `[0.3.4]` records ignoring a queued duplicate Disarm while the panel is busy; `[0.3.2]` records Connection stay-on after a successful tap when flags are starved, plus INFO boot version — abstract household language, no pipeline IDs, no scene-specific events |
| Licence label consistency | pass | `Dockerfile` OCI label is MIT |
| Version bump policy | pass | 0.3.3 → 0.3.4 (patch) — same duplicate-Disarm product as 0.3.3 with abstract changelog. No new Configuration settings |
| Store Update rehearsal | skipped | Practitioner asked to skip rehearsal this cut. Last pass remains 2026-09-01 `STORE_UPGRADE_SMOKE_PASS from=0.3.0 to=0.3.1`. Cannot Accept ship without a 0.3.4 rehearsal pass |

## Deploy

- Authorized: yes — 2026-09-01 (practitioner chose Authorize deploy; skip store rehearsal; rewrite `main` so the current changelog history stays abstract)
- Step performed: yes — bumped to `0.3.4` (`1d9986a`); force-pushed `main` (dropped the 0.3.3-era commits whose changelog named a household scene); Tag version created `v0.3.4`; Sync app branch refreshed `#app` (`version: "0.3.4"` + `image:`). Builder dispatched (`gh workflow run builder.yml --ref v0.3.4 -f version=0.3.4`) — succeeded, GHCR `0.3.4` amd64 + arm64 confirmed. Store Update rehearsal skipped this cut. Local add-on left stopped so household HA can take the panel slot. Tag `v0.3.3` was not moved.

Prior Authorized deploy (kept for history):
- 0.3.3 — 2026-09-01: published (`v0.3.3`; Builder 33527751875; GHCR amd64 + arm64). Store Update rehearsal skipped. Local add-on left stopped. Tag `v0.3.3` is not moved.
- 0.3.2 — 2026-09-01: bumped (`de1d51c`); pushed `main`; Tag version created `v0.3.2`; Sync app branch refreshed `#app` (`version: "0.3.2"` + `image:`). Builder dispatched (`gh workflow run builder.yml --ref v0.3.2 -f version=0.3.2`) — succeeded, GHCR `0.3.2` amd64 + arm64 confirmed. Store Update rehearsal skipped this cut. Local add-on left stopped so household HA can take the panel slot.
- 0.3.1 — 2026-09-01: bumped (`bdfe239`); pushed `main`; Tag version created `v0.3.1`; Sync app branch refreshed `#app` (`version: "0.3.1"` + `image:`). Builder dispatched (`gh workflow run builder.yml --ref v0.3.1 -f version=0.3.1`) — succeeded, GHCR `0.3.1` amd64 + aarch64 confirmed. Store Update rehearsal `STORE_UPGRADE_SMOKE_PASS from=0.3.0 to=0.3.1`. Local add-on left stopped so household HA can take the panel slot.
- 0.3.0 — 2026-08-29: bumped (`a99eaf4`); pushed `main`; Tag version `v0.3.0`; `#app` synced; Builder dispatched; GHCR `0.3.0` amd64 + arm64 confirmed. Store Update rehearsal `STORE_UPGRADE_SMOKE_PASS from=0.2.0 to=0.3.0`.

Prior Accepted ship (kept for history):
- 0.2.2 Accepted 2026-08-28 — household Supervisor Update confirmed live

## Live smoke

- `/run --target`: pending — household Home Assistant (not sim `localhost:7123`). Ordinary arm / disarm and Connection name on the household card.

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
