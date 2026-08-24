# TODO

Product ideas and follow-ons — not committed backlog work until planned.

## Product ideas

- **HA panic / trigger button** — Expose Home Assistant’s alarm `TRIGGER` control (MQTT `payload_trigger`) so the household can initiate a panel panic/PA from HA. Blocked on proving a Connect command (or other safe path) that actually starts PA / force-trigger on the Premier Elite; today we only detect physical Silent PA zones and report live/triggered state from real alarms, with no validated network-side panic opcode.

## Before public release

Store layout is already in place (`repository.yaml`, `texecom_alarm/`, `#app` catalogue branch, GHCR `image:`). Left:

- **Packaging smoke (same test HA is fine):** Add the `#app` URL under App Store → Repositories; install/update that copy. Do **not** run `local_*` and the store-installed copy together (single ComIP + MQTT discovery clashes). **Version-bump Update path** is gated by `/ship`: run `./scripts/ha-store-upgrade-smoke.sh` and record **Store Update rehearsal** in `docs/ship.md` (not a second ad-hoc procedure). Rebuild/reopen the apps container after dual-bind.
- **Discoverability later:** README `my.home-assistant.io` add-repo link; Community forum post. Product gate remains `/accept` → `/docs` → `/ship`; store shape is packaging, not product accept.
