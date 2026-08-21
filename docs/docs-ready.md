# Docs ready

**Date:** 2026-08-21
**State:** Accepted ✅
<!-- State: Draft 📝 | Accepted ✅ — no docs-defer in v1 -->

**Accept caveat:** Accept Accepted

## Coverage

| Type | Path(s) | Required / N/A | Status | Notes |
|------|---------|----------------|--------|-------|
| Tutorials | README Getting started | Required | ready | HA first-success plus local recipe from `docs/run.md`. Repo file links in README/`DOCS.md` are GitHub URLs so they work in the Supervisor App UI (relative paths do not). |
| How-to | `docs/how-to/configure-part-arm.md`; `docs/how-to/stop-other-connect-clients.md`; `docs/ha-loses-panel-during-alarm.md` | Required | ready | Operators configure, free the Connect slot, and diagnose the wrong-module lockout |
| Explanation | `docs/concepts/availability-and-connection.md`; `docs/protocol-overview.md` | Required | ready | Availability vs Connection and Connect-session shape are easy to confuse |
| Reference | `DOCS.md`; `docs/reference/mqtt.md`; `docs/protocol-reference.md` | Required | ready | Supervisor options, MQTT topics, observational protocol lookup |
| Licence | `LICENSE` | Required | ready | MIT; copyright notice kept (author identity, not a layout/credential leak) |

Consumer-facing pages above were written or sanitised for public Home Assistant distribution: no LAN IPs, no personal zone names, no “this install still uses factory UDL”. Generic note that UDL is *often* `1234` remains. Pipeline artefacts (spikes, brief, acceptance, analysis) still carry household fingerprint — RISK-017 / `TODO.md` redact gate for `/ship`, not claimed closed here.

Community extras (`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`) sit beside the Diátaxis set; they are not a fifth documentation type.

**Update 2026-08-21:** Re-audit found no coverage gaps. Tutorial still matches `docs/run.md`. How-to / explanation / reference / licence rows unchanged.

## Cold-start
- Via `/run`: pass — `./scripts/ha-cold-start.sh` exited 0 (already up). Core `GET http://127.0.0.1:8123/` → 200. MQTT `{prefix}/status` `online`, Alarm Panel Connection `ON`, alarm `disarmed`. Open **`http://localhost:7123/`** on the laptop (Docker `7123`→`8123`); 7123 is not listening inside the remote.

## How-to spot-check
- `docs/how-to/configure-part-arm.md` with the app up: Configuration schema is **Home / Night / Unused** only (Away excluded). Live options used those three labels; no slot set to Away.

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-21 | Clear | — |
