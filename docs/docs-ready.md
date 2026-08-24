# Docs ready

**Date:** 2026-08-24
**State:** Accepted ✅
<!-- State: Draft 📝 | Accepted ✅ — no docs-defer in v1 -->

**Accept caveat:** Accept Accepted

## Coverage

| Type | Path(s) | Required / N/A | Status | Notes |
|------|---------|----------------|--------|-------|
| Tutorials | README Getting started | Required | ready | HA first-success plus local recipe from `docs/run.md`. Repo file links in README/`DOCS.md` are GitHub URLs so they work in the Supervisor App UI (relative paths do not). Getting started now also looks for the three Ready to arm switches. |
| How-to | `docs/how-to/configure-part-arm.md`; `docs/how-to/use-ready-to-arm.md`; `docs/how-to/stop-other-connect-clients.md`; `docs/ha-loses-panel-during-alarm.md` | Required | ready | Operators configure Part-Arm, refuse unready arms, free the Connect slot, and diagnose the wrong-module lockout |
| Explanation | `docs/concepts/availability-and-connection.md`; `docs/protocol-overview.md` | Required | ready | Availability vs Connection and Connect-session shape are easy to confuse |
| Reference | `texecom_alarm/DOCS.md`; `docs/reference/mqtt.md`; `docs/protocol-reference.md` | Required | ready | Supervisor options, MQTT topics (including Arming then current on refuse), observational protocol lookup |
| Licence | `LICENSE` | Required | ready | MIT; copyright notice kept (author identity, not a layout/credential leak) |

Consumer-facing pages above were written or sanitised for public Home Assistant distribution: no LAN IPs, no personal zone names, no “this install still uses factory UDL”. Generic note that UDL is *often* `1234` remains. Working-tree Critical/High fingerprint inventory closed (RISK-017); git history remains Track 3 pending. See `TODO.md` / `docs/ship.md`.

Community extras (`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`) sit beside the Diátaxis set; they are not a fifth documentation type.

**Update 2026-08-24:** After product accept of ready-to-arm refuse, added `docs/how-to/use-ready-to-arm.md`, documented the Arming snap-back in MQTT reference and Supervisor docs, and linked it from README Getting started / Documentation.

## Cold-start
- Via `/run`: pass — `./scripts/ha-cold-start.sh` exited 0 (already up). Core `GET http://127.0.0.1:8123/` → 200. MQTT `{prefix}/status` `online`, Alarm Panel Connection `ON`, alarm `disarmed`. Open **`http://localhost:7123/`** on the laptop (Docker `7123`→`8123`); 7123 is not listening inside the remote.

## How-to spot-check
- `docs/how-to/use-ready-to-arm.md` with the app up: MQTT discovery present for Ready to arm Away / Home / Night and the Blocked arm event. Live switch payloads on this sim were `OFF` (left that way after the 24 Aug accept walk); they start `ON` on a fresh publish. Part-Arm Configuration schema remains **Home / Night / Unused** only (Away excluded).

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-21 | Clear | — |
| 2 | 2026-08-24 | Clear | — |
