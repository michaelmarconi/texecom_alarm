# Ship

**Date:** 2026-08-29
**State:** Draft 📝
<!-- Terminals: N/A | Accepted ✅ | Deferred ⏸️ -->
**Applicability:** yes

## Checklist

Risk-scaled for a LAN panel App (UDL + MQTT credentials in Supervisor options; no internet-facing API). Pen-test not warranted.

| Item | Status | Notes |
|------|--------|-------|
| Docs-ready Accepted | pass | `docs/docs-ready.md` Accepted 2026-08-27 |
| Product accept | pass | `docs/acceptance.md` Accepted 2026-08-27; ADR-020 wave signed off on the ledger (TASK-52) with live corroboration still `/accept`/overnight |
| Secrets in runtime config | pass | Unchanged: UDL / MQTT username+password are Supervisor options (`password` schema) |
| Secrets hygiene (captures) | pass | `docs/captures/` gitignored; no pcaps in tree |
| Support path | pass | GitHub issues (templates), `SECURITY.md`, `CONTRIBUTING.md` |
| Observability | pass | `log_level` WARNING/INFO/DEBUG/TRACE; session lifecycle in app logs |
| CI security scans | pass | `bandit` + `pip-audit` in `.github/workflows/ci.yml` |
| Backups | n/a | No extra datastore; HA backup of add-on options is sufficient |
| Official HA Apps store | n/a | Community GitHub repository is the intended path |
| Store-shaped repository | pass | Root `repository.yaml` + App in `texecom_alarm/`; store URL uses generated `#app` branch |
| Pre-built images (GHCR) | pass | `0.3.0` published (`docker manifest inspect`, amd64 + arm64) |
| RISK-017 fingerprint | pass | Working tree + history rewrite complete (recorded 2026-08-23) |
| CHANGELOG vs product | pass | `[0.3.0]` records scheduled check-ins, patience, removed Force-reconnect-after, send-side reconnect — household language, no pipeline IDs |
| Licence label consistency | pass | `Dockerfile` OCI label is MIT |
| Version bump policy | pass | 0.2.2 → 0.3.0 (minor) — new Configuration settings and a removed setting; same class as 0.2.0 |
| Store Update rehearsal | pass | 2026-08-29: `STORE_UPGRADE_SMOKE_PASS from=0.2.0 to=0.3.0` on `d05f66f6_texecom_alarm` — real panel login, zone enumeration, MQTT discovery before and after Update |

## Deploy

- Authorized: yes — 2026-08-29 (practitioner chose Authorize deploy)
- Step performed: yes — bumped to `0.3.0` (`a99eaf4`); pushed `main`; Tag version created `v0.3.0`; Sync app branch refreshed `#app` (`version: "0.3.0"` + `image:`). Builder `on: push: tags` did not fire automatically (same `GITHUB_TOKEN` limitation as 0.2.x), so dispatched (`gh workflow run builder.yml --ref v0.3.0 -f version=0.3.0`) — succeeded, GHCR `0.3.0` amd64 + arm64 confirmed.

Prior Accepted ship (kept for history):
- 0.2.2 Accepted 2026-08-28 — household Supervisor Update confirmed live

## Live smoke

- `/run --target`: pending

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
