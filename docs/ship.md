# Ship

**Date:** 2026-08-27
**State:** Draft 📝
<!-- Terminals: N/A | Accepted ✅ | Deferred ⏸️ -->
**Applicability:** yes

**Reason / Deferral:**

## Checklist

Risk-scaled for a LAN panel App (UDL + MQTT credentials in Supervisor options; no internet-facing API). Pen-test not warranted.

| Item | Status | Notes |
|------|--------|-------|
| Docs-ready Accepted | pass | `docs/docs-ready.md` Accepted 2026-08-24 |
| Product accept | pass | `docs/acceptance.md` Accepted, last updated 2026-08-27 (keepalive-NAK reconnect fix accepted on merged automated evidence) |
| Secrets in runtime config | pass | Unchanged: UDL / MQTT username+password are Supervisor options (`password` schema) |
| Secrets hygiene (captures) | pass | `docs/captures/` gitignored; no pcaps in tree |
| Support path | pass | GitHub issues (templates), `SECURITY.md`, `CONTRIBUTING.md` |
| Observability | pass | `log_level` WARNING/INFO/DEBUG/TRACE; session lifecycle in app logs |
| CI security scans | pass | `bandit` + `pip-audit` in `.github/workflows/ci.yml` |
| Backups | n/a | No extra datastore; HA backup of add-on options is sufficient |
| Official HA Apps store | n/a | Community GitHub repository is the intended path |
| Store-shaped repository | pass | Root `repository.yaml` + App in `texecom_alarm/`; store URL uses generated `#app` branch |
| Pre-built images (GHCR) | pending | `image: ghcr.io/michaelmarconi/texecom-alarm` in `texecom_alarm/config.yaml`; version bumped to `0.2.1` — tag/build/publish happens on deploy authorization below |
| RISK-017 fingerprint | pass | Working tree + history rewrite complete (recorded 2026-08-23) |
| CHANGELOG vs product | pass | `[0.2.1]` records the keepalive-NAK reconnect fix (TASK-45/46) |
| Licence label consistency | pass | `Dockerfile` OCI label is MIT |
| Version bump policy | pass | 0.2.0 → 0.2.1 (patch) for the keepalive-NAK bug fix — no behaviour removal or config-panel change |
| Store Update rehearsal | pass | 2026-08-26: redesigned mechanism (`#app-previous` permanent branch, one release behind `#app` — see `docs/run.md` and this skill's Gate). `./scripts/ha-store-upgrade-smoke.sh` → `STORE_UPGRADE_SMOKE_PASS from=0.1.2 to=0.2.0 slug=d05f66f6_texecom_alarm`. Seeded the rehearsal slug with the real panel/MQTT credentials (distinct `mqtt_topic_prefix=texecom-rehearsal` so it can't collide with `local_texecom_alarm`'s discovery) and confirmed real panel login + zone enumeration + MQTT discovery **both before and after** the Update — a functional proof, not just version/options metadata. Options-persistence check relaxed to "every pre-existing key keeps its value" (new keys from a changed schema are expected, not a failure). `local_texecom_alarm` stayed stopped throughout (single ComIP), then was rebuilt + restarted at the end, which reclaims the shared MQTT discovery `unique_id` namespace back from the rehearsal slug (confirmed: `homeassistant/alarm_control_panel/texecom_alarm_arm_status/config` points at `texecom/...` topics again, not `texecom-rehearsal/...`). Retained `texecom-rehearsal/#` state cleared after each run. |

## Deploy

- Authorized: yes — 2026-08-24 (practitioner chose Authorize deploy); re-confirmed 2026-08-26 for the 0.2.0 bump (practitioner chose Authorize deploy)
- Step performed: yes — pushed `main` (`1d4b552` 0.2.0); Tag version created `v0.2.0`; Builder published GHCR `0.2.0`; Sync app branch refreshed `#app` (catalogue `version: "0.2.0"` + `image:`)
- 0.2.1 (keepalive-NAK fix): yes — 2026-08-27 (practitioner chose Authorize deploy)

## Live smoke

- `/run --target`: pending — Store Update rehearsal passed against the real released 0.2.0
  artifact with a functional (real-panel) proof; still owes a `/run --target` household smoke
  against the live install. Now also carries the 0.2.1 patch — smoke and rehearsal should target
  0.2.1 once it's built and published.

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
