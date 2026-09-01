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
| Product accept | pass | `docs/acceptance.md` Accepted 2026-09-01; iOS arm/disarm on the local module published `arming` → `armed_away` → `disarmed` with Connection still on. Household HA card walk (coming home, ordinary arm, Connection name) still required as live smoke. 0.3.1 then turned Connection off on garage return (~11:51 BST) after a starved flags follow-up — that is the 0.3.2 fix |
| Secrets in runtime config | pass | Unchanged: UDL / MQTT username+password are Supervisor options (`password` schema) |
| Secrets hygiene (captures) | pass | `docs/captures/` gitignored; no pcaps in tree |
| Support path | pass | GitHub issues (templates), `SECURITY.md`, `CONTRIBUTING.md` |
| Observability | pass | `log_level` WARNING/INFO/DEBUG/TRACE; session lifecycle in app logs; decode-miss logs reason + leading hex; process start logs the add-on version at INFO |
| CI security scans | pass | `bandit` + `pip-audit` in `.github/workflows/ci.yml` |
| Backups | n/a | No extra datastore; HA backup of add-on options is sufficient |
| Official HA Apps store | n/a | Community GitHub repository is the intended path |
| Store-shaped repository | pass | Root `repository.yaml` + App in `texecom_alarm/`; store URL uses generated `#app` branch |
| Pre-built images (GHCR) | pass | `0.3.2` published (`docker manifest inspect` amd64 + arm64; Builder run 33506407255) |
| RISK-017 fingerprint | pass | Working tree + history rewrite complete (recorded 2026-08-23) |
| CHANGELOG vs product | pass | `[0.3.2]` records garage-return Connection stay-on and INFO boot version — household language, no pipeline IDs |
| Licence label consistency | pass | `Dockerfile` OCI label is MIT |
| Version bump policy | pass | 0.3.1 → 0.3.2 (patch) — Connection stay-on after a successful tap when flags are starved; INFO boot version. No new Configuration settings |
| Store Update rehearsal | skipped | Practitioner asked to skip `0.3.1` → `0.3.2` rehearsal this cut. Last pass remains 2026-09-01 `STORE_UPGRADE_SMOKE_PASS from=0.3.0 to=0.3.1`. Cannot Accept ship without a 0.3.2 rehearsal pass |

## Deploy

- Authorized: yes — 2026-09-01 (practitioner chose Authorize deploy; skip store rehearsal)
- Step performed: yes — bumped to `0.3.2` (`de1d51c`); pushed `main`; Tag version created `v0.3.2`; Sync app branch refreshed `#app` (`version: "0.3.2"` + `image:`). Builder dispatched (`gh workflow run builder.yml --ref v0.3.2 -f version=0.3.2`) — succeeded, GHCR `0.3.2` amd64 + arm64 confirmed. Store Update rehearsal skipped this cut. Local add-on left stopped so household HA can take the panel slot.

Prior Authorized deploy (kept for history):
- 0.3.1 — 2026-09-01: bumped (`bdfe239`); pushed `main`; Tag version created `v0.3.1`; Sync app branch refreshed `#app` (`version: "0.3.1"` + `image:`). Builder dispatched (`gh workflow run builder.yml --ref v0.3.1 -f version=0.3.1`) — succeeded, GHCR `0.3.1` amd64 + aarch64 confirmed. Store Update rehearsal `STORE_UPGRADE_SMOKE_PASS from=0.3.0 to=0.3.1`. Local add-on left stopped so household HA can take the panel slot.
- 0.3.0 — 2026-08-29: bumped (`a99eaf4`); pushed `main`; Tag version `v0.3.0`; `#app` synced; Builder dispatched; GHCR `0.3.0` amd64 + arm64 confirmed. Store Update rehearsal `STORE_UPGRADE_SMOKE_PASS from=0.2.0 to=0.3.0`.

Prior Accepted ship (kept for history):
- 0.2.2 Accepted 2026-08-28 — household Supervisor Update confirmed live

## Live smoke

- `/run --target`: pending — household Home Assistant (not sim `localhost:7123`). Coming home / ordinary arm / Connection name on the household card. Garage-return Connection staying on is the 0.3.2 check.

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
