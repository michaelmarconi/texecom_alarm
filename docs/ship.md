# Ship

**Date:** 2026-08-23
**State:** Accepted ✅
<!-- Terminals: N/A | Accepted ✅ | Deferred ⏸️ -->

**Reason / Deferral:** Go-live Accepted 2026-08-23 — checklist pass (including store Update rehearsal 0.1.0→0.1.1), deploy authorized and performed on household HA from `#app`, live smoke pass (practitioner confirmation).

## Checklist

Risk-scaled for a LAN panel App (UDL + MQTT credentials in Supervisor options; no internet-facing API). Pen-test not warranted.

| Item | Status | Notes |
|------|--------|-------|
| Docs-ready Accepted | pass | `docs/docs-ready.md` Accepted 2026-08-21 |
| Product accept | pass | `docs/acceptance.md` Accepted; live sim + dedicated ComIP walked |
| Secrets in runtime config | pass | UDL / MQTT username+password are Supervisor options (`password` schema); not hardcoded household values. Default MQTT host/user/password empty. Default UDL `1234` is the documented factory-often value, not a committed live secret file. |
| Secrets hygiene (captures) | pass | `docs/captures/` gitignored; no pcaps in tree |
| Support path | pass | GitHub issues (templates), `SECURITY.md` private advisories, `CONTRIBUTING.md` |
| Observability | pass | `log_level` WARNING/INFO/DEBUG/TRACE; session lifecycle in app logs (DoD ops tracing) |
| CI security scans | pass | `bandit` + `pip-audit` in `.github/workflows/ci.yml` |
| Backups | n/a | No extra datastore; HA backup of add-on options is sufficient |
| Official HA Apps store | n/a | Will not take this; community GitHub repository is the intended path (`TODO.md`) |
| Store-shaped repository | pass | Root `repository.yaml` + App in `texecom_alarm/` (catalogue layout). Store URL uses generated `#app` branch (thin tree; no `backlog/`). Local apps-devcontainer dual-binds the app subfolder to `/mnt/supervisor/apps/local/texecom_alarm` so `local_texecom_alarm` still works. |
| Pre-built images (GHCR) | pass | `image: ghcr.io/michaelmarconi/texecom-alarm` in `texecom_alarm/config.yaml`; builder workflow on `v*` tags (amd64 + aarch64 → multi-arch manifest) |
| RISK-017 fingerprint | pass | Working tree + history rewrite complete; Critical/High LAN/name/UDL fingerprint purged from `main` |
| CHANGELOG vs product | pass | `CHANGELOG.md` `[0.1.0]` describes the real App; `[0.0.1]` retained as historical scaffold only |
| Licence label consistency | pass | `Dockerfile` OCI label is MIT (matches `LICENSE`) |
| Version bump policy | pass | Supervisor SemVer only for notable product releases; CI checks copies match; tag `vX.Y.Z` when that version first lands on `main` |
| Store Update rehearsal | pass | 2026-08-23: `./scripts/ha-store-upgrade-smoke.sh --from 0.1.0` → `STORE_UPGRADE_SMOKE_PASS from=0.1.0 to=0.1.1 slug=ebb3b885_texecom_alarm`. GHCR tag `0.1.1` was missing (only `0.1.0`/`latest`); re-published via Builder workflow_dispatch before the smoke. Options marker `mqtt_username=texecom-store-smoke` survived Update. |

## Deploy

- Authorized: yes — 2026-08-22 (practitioner authorized community GitHub App install on a real HA OS host)
- Step performed: yes — household HA install/Update from `https://github.com/michaelmarconi/texecom_alarm#app` (practitioner-confirmed 2026-08-23)

## Live smoke

- Store catalogue smoke (apps-devcontainer, 2026-08-22): added `…/texecom_alarm#app`; clone at `apps/git/ebb3b885` is allowlist-only (no `backlog/`); Supervisor shows `ebb3b885_texecom_alarm` v0.1.1 with Documentation; **no** `Invalid app config` for the git clone (remaining warnings are from the **local** monorepo mount’s `backlog/config.yml`, expected until local dual-bind changes). Did not install the store copy alongside `local_texecom_alarm`.
- Store Update rehearsal: pass 2026-08-23 — see checklist row (not Live smoke).
- `/run --target`: pass — 2026-08-23 practitioner walked household HA after store Install/Update; App working well (agent has no LAN reach — smoke recorded from practitioner confirmation, not an in-session URL fetch). Local `/run` (sim HA on 7123) is not live smoke.

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
