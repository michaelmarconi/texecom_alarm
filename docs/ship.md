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
| Product accept | pass | `docs/acceptance.md` Accepted 2026-09-01; iOS arm/disarm on the local module published `arming` → `armed_away` → `disarmed` with Connection still on. Household HA card walk (coming home, ordinary arm, Connection name) still required as live smoke |
| Secrets in runtime config | pass | Unchanged: UDL / MQTT username+password are Supervisor options (`password` schema) |
| Secrets hygiene (captures) | pass | `docs/captures/` gitignored; no pcaps in tree |
| Support path | pass | GitHub issues (templates), `SECURITY.md`, `CONTRIBUTING.md` |
| Observability | pass | `log_level` WARNING/INFO/DEBUG/TRACE; session lifecycle in app logs; decode-miss now logs reason + leading hex |
| CI security scans | pass | `bandit` + `pip-audit` in `.github/workflows/ci.yml` |
| Backups | n/a | No extra datastore; HA backup of add-on options is sufficient |
| Official HA Apps store | n/a | Community GitHub repository is the intended path |
| Store-shaped repository | pass | Root `repository.yaml` + App in `texecom_alarm/`; store URL uses generated `#app` branch |
| Pre-built images (GHCR) | pending | `0.3.0` is published; busy-versus-dead follow-on (post-ACK flags skip, collision vs failed tap, decode-miss log) is on `main` after `v0.3.0` and is not in GHCR yet |
| RISK-017 fingerprint | pass | Working tree + history rewrite complete (recorded 2026-08-23) |
| CHANGELOG vs product | pending | `[Unreleased]` is empty; household notes for the follow-on belong in the next cut (likely `0.3.1`) |
| Licence label consistency | pass | `Dockerfile` OCI label is MIT |
| Version bump policy | pending | Do not ship the follow-on as another `0.3.0`; needs a new Supervisor version |
| Store Update rehearsal | pending | Prior pass 2026-08-29 `0.2.0` → `0.3.0`. A new cut needs `./scripts/ha-store-upgrade-smoke.sh` FROM `0.3.0` TO the new version — not a local rebuild |

## Deploy

- Authorized: no — waiting on authorize for a new cut after `0.3.0` (busy-versus-dead follow-on on `main` is not in the published `0.3.0` image)
- Step performed: no for this cut

Prior Authorized deploy (kept for history):
- 0.3.0 — 2026-08-29: bumped (`a99eaf4`); pushed `main`; Tag version `v0.3.0`; `#app` synced; Builder dispatched; GHCR `0.3.0` amd64 + arm64 confirmed. Store Update rehearsal `STORE_UPGRADE_SMOKE_PASS from=0.2.0 to=0.3.0`.

Prior Accepted ship (kept for history):
- 0.2.2 Accepted 2026-08-28 — household Supervisor Update confirmed live

## Live smoke

- `/run --target`: pending — household Home Assistant (not sim `localhost:7123`). Coming home / ordinary arm / Connection name on the household card.

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
