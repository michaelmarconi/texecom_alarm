# Ship

**Date:** 2026-09-03
**State:** Draft 📝
<!-- Terminals: N/A | Accepted ✅ | Deferred ⏸️ -->
**Applicability:** yes

## Checklist

Risk-scaled for a LAN panel App (UDL + MQTT credentials in Supervisor options; no internet-facing API). Pen-test not warranted.

| Item | Status | Notes |
|------|--------|-------|
| Docs-ready Accepted | pass | `docs/docs-ready.md` Accepted 2026-08-27 |
| Product accept | pass | `docs/acceptance.md` Accepted 2026-09-01. 0.3.7 is the Night double-submit / torn-follow-up cut; household Update + live smoke is the exposure path |
| Secrets in runtime config | pass | Unchanged: UDL / MQTT username+password are Supervisor options (`password` schema) |
| Secrets hygiene (captures) | pass | `docs/captures/` gitignored; no pcaps in tree |
| Support path | pass | GitHub issues (templates), `SECURITY.md`, `CONTRIBUTING.md` |
| Observability | pass | `log_level` WARNING/INFO/DEBUG/TRACE; session lifecycle in app logs; decode-miss logs reason + leading hex; process start logs the add-on version at INFO |
| CI security scans | pass | `bandit` + `pip-audit` in `.github/workflows/ci.yml` |
| Backups | n/a | No extra datastore; HA backup of add-on options is sufficient |
| Official HA Apps store | n/a | Community GitHub repository is the intended path |
| Store-shaped repository | pass | Root `repository.yaml` + App in `texecom_alarm/`; store URL uses generated `#app` branch |
| Pre-built images (GHCR) | pending | `0.3.6` published. `0.3.7` not confirmed yet |
| RISK-017 fingerprint | pass | Working tree + history rewrite complete (recorded 2026-08-23) |
| CHANGELOG vs product | pass | `[0.3.7]` records duplicate-arm ignore, post-ACK resync, and lagging-unset reconnect; abstract household language, no pipeline IDs |
| Licence label consistency | pass | `Dockerfile` OCI label is MIT |
| Version bump policy | pass | 0.3.6 → 0.3.7 (patch) — ignore a second identical Arm; torn follow-up is a resync not a failed tap; reconnect must not flash Off or forget the in-flight arm. No new Configuration settings |
| Store Update rehearsal | skipped | Practitioner will walk household HA Update instead of sim `./scripts/ha-store-upgrade-smoke.sh`. Last pass remains 2026-09-01 `STORE_UPGRADE_SMOKE_PASS from=0.3.0 to=0.3.1`. Cannot Accept ship without a 0.3.7 rehearsal pass |

## Deploy

- Authorized: yes — 2026-09-03 (practitioner chose bump and publish so household HA can Update; skip store rehearsal; live smoke is household `--target`, not sim `/accept`)
- Step performed: pending — bump `0.3.7`; push `main`; Tag version `v0.3.7`; Sync `#app`; Builder `v0.3.7`

Prior Authorized deploy (kept for history):
- 0.3.6 — 2026-09-02: bumped (`946a86b`); pushed `main`; Tag version created `v0.3.6`; Sync app branch refreshed `#app`. Builder 33630276344; GHCR amd64 + arm64. Store Update rehearsal skipped. Local add-on left stopped.
- 0.3.5 — 2026-09-01: bumped (`a065651`); pushed `main`; Tag version created `v0.3.5`; Sync app branch refreshed `#app`. Builder succeeded, GHCR `0.3.5` amd64 + arm64. Store Update rehearsal skipped this cut. Local add-on left stopped so household HA can take the panel slot.
- 0.3.4 — 2026-09-01: bumped (`1d9986a`); force-pushed `main`; Tag version `v0.3.4`; `#app` synced; Builder 33528827986; GHCR amd64 + arm64. Store Update rehearsal skipped. Local add-on left stopped. Tag `v0.3.3` was not moved.
- 0.3.3 — 2026-09-01: published (`v0.3.3`; Builder 33527751875; GHCR amd64 + arm64). Store Update rehearsal skipped. Local add-on left stopped. Tag `v0.3.3` is not moved.
- 0.3.2 — 2026-09-01: bumped (`de1d51c`); pushed `main`; Tag version created `v0.3.2`; Sync app branch refreshed `#app` (`version: "0.3.2"` + `image:`). Builder dispatched (`gh workflow run builder.yml --ref v0.3.2 -f version=0.3.2`) — succeeded, GHCR `0.3.2` amd64 + arm64 confirmed. Store Update rehearsal skipped this cut. Local add-on left stopped so household HA can take the panel slot.
- 0.3.1 — 2026-09-01: bumped (`bdfe239`); pushed `main`; Tag version created `v0.3.1`; Sync app branch refreshed `#app` (`version: "0.3.1"` + `image:`). Builder dispatched (`gh workflow run builder.yml --ref v0.3.1 -f version=0.3.1`) — succeeded, GHCR `0.3.1` amd64 + aarch64 confirmed. Store Update rehearsal `STORE_UPGRADE_SMOKE_PASS from=0.3.0 to=0.3.1`. Local add-on left stopped so household HA can take the panel slot.
- 0.3.0 — 2026-08-29: bumped (`a99eaf4`); pushed `main`; Tag version `v0.3.0`; `#app` synced; Builder dispatched; GHCR `0.3.0` amd64 + arm64 confirmed. Store Update rehearsal `STORE_UPGRADE_SMOKE_PASS from=0.2.0 to=0.3.0`.

Prior Accepted ship (kept for history):
- 0.2.2 Accepted 2026-08-28 — household Supervisor Update confirmed live

## Live smoke

- `/run --target`: pending — household Home Assistant (not sim `localhost:7123`). Night (or Home/Away) from HomeKit or the card: a double-submit must not flash Off or take **Alarm Panel Connection** off; the house should stay in exit / that armed mode. Hang-up / `+++` still turns Connection off.

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
