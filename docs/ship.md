# Ship

**Date:** 2026-08-28
**State:** Accepted ✅
<!-- Terminals: N/A | Accepted ✅ | Deferred ⏸️ -->
**Applicability:** yes

## Checklist

Risk-scaled for a LAN panel App (UDL + MQTT credentials in Supervisor options; no internet-facing API). Pen-test not warranted.

| Item | Status | Notes |
|------|--------|-------|
| Docs-ready Accepted | pass | `docs/docs-ready.md` Accepted 2026-08-27 (re-synced Explanation/Reference docs against ADR-016/018/019) |
| Product accept | pass | `docs/acceptance.md` Accepted 2026-08-27 (keepalive-retry-budget fix, TASK-47/48, accepted on merged automated evidence) |
| Secrets in runtime config | pass | Unchanged: UDL / MQTT username+password are Supervisor options (`password` schema) |
| Secrets hygiene (captures) | pass | `docs/captures/` gitignored; no pcaps in tree |
| Support path | pass | GitHub issues (templates), `SECURITY.md`, `CONTRIBUTING.md` |
| Observability | pass | `log_level` WARNING/INFO/DEBUG/TRACE; session lifecycle in app logs |
| CI security scans | pass | `bandit` + `pip-audit` in `.github/workflows/ci.yml` |
| Backups | n/a | No extra datastore; HA backup of add-on options is sufficient |
| Official HA Apps store | n/a | Community GitHub repository is the intended path |
| Store-shaped repository | pass | Root `repository.yaml` + App in `texecom_alarm/`; store URL uses generated `#app` branch |
| Pre-built images (GHCR) | pass | `0.2.2` published (`docker manifest inspect`, amd64 + arm64) — see Deploy |
| RISK-017 fingerprint | pass | Working tree + history rewrite complete (recorded 2026-08-23) |
| CHANGELOG vs product | pass | `[0.2.2]` records the keepalive-retry-budget fix, rewritten in plain terms for the HA community (no task IDs / byte-level detail / incident-report framing — practitioner flagged the first draft as leaking internal context) |
| Licence label consistency | pass | `Dockerfile` OCI label is MIT |
| Version bump policy | pass | 0.2.1 → 0.2.2 (patch) — bug fix only, no behaviour removal or config-panel change, same policy as the last two rounds |
| Store Update rehearsal | pass (prior round) | Last rehearsed 2026-08-26/27 for the 0.1.2 → 0.2.0 → 0.2.1 path; the mechanism (`#app-previous`, `./scripts/ha-store-upgrade-smoke.sh`) is unchanged for this round — see prior log below |

## Deploy

- Authorized: yes — 2026-08-27 (practitioner chose Authorize deploy)
- Step performed: yes — bumped `config.yaml`/`__init__.py`/`pyproject.toml` to `0.2.2` and cut
  `CHANGELOG.md` (`895d92c`; a version-sync CI failure on the first push, `pyproject.toml` left at
  `0.2.1`, was caught and fixed with `./scripts/sync-version.sh sync` before the second push — CI
  green after). Pushed `main`; Tag version workflow created `v0.2.2`; Sync app branch refreshed `#app`
  (`version: "0.2.2"` + `image:` confirmed on `origin/app`). Builder's `on: push: tags` did not fire
  automatically (same `GITHUB_TOKEN` limitation as 0.2.0/0.2.1), so dispatched manually
  (`gh workflow run builder.yml --ref v0.2.2 -f version=0.2.2`) — succeeded, GHCR `0.2.2` confirmed via
  `docker manifest inspect` (amd64 + arm64).

Prior round (kept for history):
- Authorized: yes — 2026-08-24 (practitioner chose Authorize deploy); re-confirmed 2026-08-26 for the 0.2.0 bump (practitioner chose Authorize deploy)
- Step performed: yes — pushed `main` (`1d4b552` 0.2.0); Tag version created `v0.2.0`; Builder published GHCR `0.2.0`; Sync app branch refreshed `#app` (catalogue `version: "0.2.0"` + `image:`)
- 0.2.1 (keepalive-NAK fix): yes — 2026-08-27 (practitioner chose Authorize deploy). Pushed `main`
  (`f18025d` 0.2.1); Tag version created `v0.2.1`; Sync app branch refreshed `#app` immediately (both
  auto-triggered by the push). The Tag-version workflow's tag push uses the default `GITHUB_TOKEN`,
  which GitHub does not let trigger further workflow runs — Builder's `on: push: tags` didn't fire
  automatically (same as the 0.2.0 round), so it was dispatched manually
  (`gh workflow run builder.yml --ref v0.2.1 -f version=0.2.1`) and published GHCR `0.2.1` (confirmed
  via `docker manifest inspect`, amd64+arm64).

## Live smoke

- `/run --target`: pass — 2026-08-28: practitioner performed the real Supervisor Update on the
  household's live Home Assistant install (store `#app` slug) to `0.2.2` and confirmed it came up
  and is functioning as expected.

Prior round (kept for history):
- `/run --target`: pass — 2026-08-27: practitioner performed the real Supervisor Update on the
  household's live Home Assistant install (store `#app` slug) to `0.2.1` and confirmed it completed
  cleanly, matching the automated Store Update rehearsal's functional proof (real panel login, zone
  enumeration, MQTT discovery) with an actual household-side outcome.

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
