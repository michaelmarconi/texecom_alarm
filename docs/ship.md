# Ship

**Date:** 2026-08-24
**State:** Draft 📝
<!-- Terminals: N/A | Accepted ✅ | Deferred ⏸️ -->
**Applicability:** yes

**Reason / Deferral:**

## Checklist

Risk-scaled for a LAN panel App (UDL + MQTT credentials in Supervisor options; no internet-facing API). Pen-test not warranted.

| Item | Status | Notes |
|------|--------|-------|
| Docs-ready Accepted | pass | `docs/docs-ready.md` Accepted 2026-08-24 |
| Product accept | pass | `docs/acceptance.md` Accepted 2026-08-24 (ready-to-arm refuse walked on local rebuild) |
| Secrets in runtime config | pass | Unchanged: UDL / MQTT username+password are Supervisor options (`password` schema) |
| Secrets hygiene (captures) | pass | `docs/captures/` gitignored; no pcaps in tree |
| Support path | pass | GitHub issues (templates), `SECURITY.md`, `CONTRIBUTING.md` |
| Observability | pass | `log_level` WARNING/INFO/DEBUG/TRACE; session lifecycle in app logs |
| CI security scans | pass | `bandit` + `pip-audit` in `.github/workflows/ci.yml` |
| Backups | n/a | No extra datastore; HA backup of add-on options is sufficient |
| Official HA Apps store | n/a | Community GitHub repository is the intended path |
| Store-shaped repository | pass | Root `repository.yaml` + App in `texecom_alarm/`; store URL uses generated `#app` branch |
| Pre-built images (GHCR) | pass | `image: ghcr.io/michaelmarconi/texecom-alarm` in `texecom_alarm/config.yaml`; tag `v0.1.2`; Builder published GHCR `0.1.2`. Sim store container is `ghcr.io/michaelmarconi/texecom-alarm:0.1.2` |
| RISK-017 fingerprint | pass | Working tree + history rewrite complete (recorded 2026-08-23) |
| CHANGELOG vs product | pass | `[0.1.2]` records ready-to-arm refuse and Arming snap-back |
| Licence label consistency | pass | `Dockerfile` OCI label is MIT |
| Version bump policy | pass | 0.1.1 → 0.1.2 for notable product change (`f6f4fe1`) |
| Store Update rehearsal | pass | 2026-08-24: `./scripts/ha-store-upgrade-smoke.sh --from 0.1.1 --no-restart-local` → `STORE_UPGRADE_SMOKE_PASS from=0.1.1 to=0.1.2 slug=ebb3b885_texecom_alarm`. Practitioner then Updated the sim store copy from the GHCR image (not local rebuild) and confirmed it working. Local `local_texecom_alarm` stayed stopped so the two copies did not share ComIP. |

## Deploy

- Authorized: yes — 2026-08-24 (practitioner chose Authorize deploy)
- Step performed: yes — pushed `main` (`f6f4fe1` 0.1.2); Tag version created `v0.1.2`; Builder published GHCR `0.1.2`; Sync app branch refreshed `#app` (catalogue `version: "0.1.2"` + `image:`)

## Live smoke

- `/run --target`: pending — after store Update rehearsal pass

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
