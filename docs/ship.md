# Ship

**Date:** 2026-08-21
**State:** Draft 📝
<!-- Terminals: N/A | Accepted ✅ | Deferred ⏸️ -->
<!-- Draft only: -->
**Applicability:** yes
<!-- Applicability on Draft is only yes|pending — never no (use State: N/A) -->

**Reason / Deferral:** Applicable — architecture names a public Home Assistant App for other Premier Elite households; GitHub is already the publish URL; the practitioner wants this App on a real HA OS host. Not N/A.

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
| Store-shaped repository | pass | Root `repository.yaml` + App in `texecom_alarm/` (catalogue layout). Local apps-devcontainer dual-binds the app subfolder to `/mnt/supervisor/apps/local/texecom_alarm` so `local_texecom_alarm` still works. |
| Pre-built images (GHCR) | pass | `image: ghcr.io/michaelmarconi/texecom-alarm` in `texecom_alarm/config.yaml`; builder workflow on `v*` tags (amd64 + aarch64 → multi-arch manifest) |
| RISK-017 fingerprint | pass | Working tree + history rewrite complete; Critical/High LAN/name/UDL fingerprint purged from `main` |
| CHANGELOG vs product | pass | `CHANGELOG.md` `[0.1.0]` describes the real App; `[0.0.1]` retained as historical scaffold only |
| Licence label consistency | pass | `Dockerfile` OCI label is MIT (matches `LICENSE`) |
| Version bump policy | pass | Single SemVer `0.1.0` (canonical `config.yaml`); CI `sync-version.sh check`; bump-on-main + tag workflow; see `docs/addon-versioning.md` |

## Deploy

- Authorized: no — waiting on pre-deploy Ask
- Step performed: none. Catalogue layout is in place (`repository.yaml` + `texecom_alarm/`); GHCR/`image:` still open. GitHub host alone is not treated as a completed publish.

## Live smoke

- `/run --target {url}`: not run — no production/install URL yet. Local `/run` (sim HA on 7123) is not live smoke.

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
