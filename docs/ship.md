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
| Product accept | pass | `docs/acceptance.md` Accepted 2026-09-01. 0.3.2 then turned Connection off on garage return (~13:31 BST) after a second `SETAREADISARM` into the post-ACK `M` burst — that is the 0.3.3 fix. Household HA card walk still live smoke |
| Secrets in runtime config | pass | Unchanged: UDL / MQTT username+password are Supervisor options (`password` schema) |
| Secrets hygiene (captures) | pass | `docs/captures/` gitignored; no pcaps in tree |
| Support path | pass | GitHub issues (templates), `SECURITY.md`, `CONTRIBUTING.md` |
| Observability | pass | `log_level` WARNING/INFO/DEBUG/TRACE; session lifecycle in app logs; decode-miss logs reason + leading hex; process start logs the add-on version at INFO; duplicate Disarm logs `alarm_command_disarm_ignored` |
| CI security scans | pass | `bandit` + `pip-audit` in `.github/workflows/ci.yml` |
| Backups | n/a | No extra datastore; HA backup of add-on options is sufficient |
| Official HA Apps store | n/a | Community GitHub repository is the intended path |
| Store-shaped repository | pass | Root `repository.yaml` + App in `texecom_alarm/`; store URL uses generated `#app` branch |
| Pre-built images (GHCR) | pending | `0.3.2` published. `0.3.3` cut locally; GHCR not confirmed yet |
| RISK-017 fingerprint | pass | Working tree + history rewrite complete (recorded 2026-08-23) |
| CHANGELOG vs product | pass | `[0.3.3]` records ignoring a second Disarm while already unset — household language, no pipeline IDs |
| Licence label consistency | pass | `Dockerfile` OCI label is MIT |
| Version bump policy | pass | 0.3.2 → 0.3.3 (patch) — do not TX a queued duplicate Disarm into garage-return chatter. No new Configuration settings. No ADR supersede (ADR-021 skip-and-resync still forbidden) |
| Store Update rehearsal | skipped | Practitioner skipped rehearsal on 0.3.2; same for this cut so the household panel slot stays free. Last pass remains 2026-09-01 `STORE_UPGRADE_SMOKE_PASS from=0.3.0 to=0.3.1`. Cannot Accept ship without a rehearsal pass |

## Deploy

- Authorized: yes — 2026-09-01 (practitioner chose ship 0.3.3; skip store rehearsal)
- Step performed: in progress — bumped to `0.3.3`

Prior Authorized deploy (kept for history):
- 0.3.2 — 2026-09-01: bumped (`de1d51c`); pushed `main`; Tag version created `v0.3.2`; Sync app branch refreshed `#app`; Builder dispatched (`gh workflow run builder.yml --ref v0.3.2 -f version=0.3.2`) — succeeded, GHCR `0.3.2` amd64 + arm64. Store rehearsal skipped. Local add-on left stopped.
- 0.3.1 — 2026-09-01: bumped (`bdfe239`); Tag `v0.3.1`; `#app` synced; Builder succeeded; Store Update rehearsal `STORE_UPGRADE_SMOKE_PASS from=0.3.0 to=0.3.1`.
- 0.3.0 — 2026-08-29: bumped (`a99eaf4`); Tag `v0.3.0`; `#app` synced; Builder succeeded; Store Update rehearsal `STORE_UPGRADE_SMOKE_PASS from=0.2.0 to=0.3.0`.

Prior Accepted ship (kept for history):
- 0.2.2 Accepted 2026-08-28 — household Supervisor Update confirmed live

## Live smoke

- `/run --target`: pending — household Home Assistant (not sim `localhost:7123`). Garage-return: one Disarm on the wire, Connection stays on; a duplicate should log `already=disarmed`.

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
