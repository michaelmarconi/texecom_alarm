# Docs ready

**Date:** 2026-08-27
**State:** Accepted ✅
<!-- State: Draft 📝 | Accepted ✅ — no docs-defer in v1 -->

**Accept caveat:** Accept Accepted

## Coverage

| Type | Path(s) | Required / N/A | Status | Notes |
|------|---------|----------------|--------|-------|
| Tutorials | README Getting started | Required | ready | HA first-success plus local recipe from `docs/run.md`. Repo file links in README/`DOCS.md` are GitHub URLs so they work in the Supervisor App UI (relative paths do not). Getting started now also looks for the three Ready to arm switches. |
| How-to | `docs/how-to/configure-part-arm.md`; `docs/how-to/use-ready-to-arm.md`; `docs/how-to/expose-alarm-to-homekit.md`; `docs/how-to/stop-other-connect-clients.md`; `docs/ha-loses-panel-during-alarm.md` | Required | ready | Operators configure Part-Arm, refuse unready arms, expose Apple Home via a template facade, free the Connect slot, and diagnose the wrong-module lockout |
| Explanation | `docs/concepts/availability-and-connection.md`; `docs/protocol-overview.md` | Required | ready | Availability vs Connection and Connect-session shape are easy to confuse. Re-synced 27 Aug against ADR-016/018/019 (reconciliation poll no longer drives Connection; no line-noise resync path; single reconnect interval for every disconnect cause) — both had drifted since the 26 Aug connection-simplification wave. |
| Reference | `texecom_alarm/DOCS.md`; `docs/reference/mqtt.md`; `docs/protocol-reference.md` | Required | ready | Supervisor options, MQTT topics (including Arming then current on refuse), observational protocol lookup. 27 Aug: added the missing Recheck interval option row and renamed Trust fail window → Force reconnect after to match the live UI label. |
| Licence | `LICENSE` | Required | ready | MIT; copyright notice kept (author identity, not a layout/credential leak) |

Consumer-facing pages above were written or sanitised for public Home Assistant distribution: no LAN IPs, no personal zone names, no “this install still uses factory UDL”. Generic note that UDL is *often* `1234` remains. Working-tree Critical/High fingerprint inventory closed (RISK-017); git history remains Track 3 pending. See `TODO.md` / `docs/ship.md`.

Community extras (`CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`) sit beside the Diátaxis set; they are not a fifth documentation type.

**Update 2026-08-24:** After product accept of ready-to-arm refuse, added `docs/how-to/use-ready-to-arm.md`, documented the Arming snap-back in MQTT reference and Supervisor docs, and linked it from README Getting started / Documentation.

**Update 2026-08-27:** Re-entered docs after three waves landed since the 24 Aug round (connection-simplification ADR-016–019, the keepalive-NAK reconnect fix, and the same-day keepalive-retry-budget follow-up). Found and fixed Explanation/Reference drift: `docs/protocol-overview.md` and `docs/concepts/availability-and-connection.md` still described the retired skip-and-resync / asymmetric-reconnect-budget behaviour and listed the reconciliation poll as a Connection trigger; `texecom_alarm/DOCS.md` was missing the Recheck interval option entirely and still used the pre-rename "Trust fail window" label. No new Tutorial/How-to content needed — none of these waves changed a user-facing workflow, only internal robustness and one config-panel simplification already covered.

**Update 2026-09-03:** Added `docs/how-to/expose-alarm-to-homekit.md` (Home Assistant template facade so Apple Home does not map `arming` to Away). Linked from README / `DOCS.md` / MQTT reference / ready-to-arm how-to. Config-only; no add-on behaviour change.

## Cold-start
- Via `/run`: pass — `./scripts/ha-cold-start.sh` exited 0 (already up); `ha apps update`/`ha apps rebuild local_texecom_alarm` brought it to `0.2.1` (matches source `config.yaml`). Core `GET http://127.0.0.1:8123/` → 302 (onboarding/login redirect, expected). Add-on state is `error` this session because `panel_host` is empty (no `TEXECOM_PANEL_HOST` set) — that is the documented required-option gate (README Getting started step 4 / `DOCS.md`), not a defect; the 24 Aug round's fuller live walk (Connection `ON`, alarm `disarmed`) already covers the configured-panel path.

## How-to spot-check
- `docs/how-to/use-ready-to-arm.md` with the app up: MQTT discovery present for Ready to arm Away / Home / Night and the Blocked arm event. Live switch payloads on this sim were `OFF` (left that way after the 24 Aug accept walk); they start `ON` on a fresh publish. Part-Arm Configuration schema remains **Home / Night / Unused** only (Away excluded).

## Review
| # | Date | Verdict | Issues |
|---|------|---------|--------|
| 1 | 2026-08-21 | Clear | — |
| 2 | 2026-08-24 | Clear | — |
| 3 | 2026-08-27 | Clear | — |
