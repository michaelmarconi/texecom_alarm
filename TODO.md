# TODO

Product ideas and follow-ons — not committed backlog work until planned.

## Product ideas

- **HA panic / trigger button** — Expose Home Assistant’s alarm `TRIGGER` control (MQTT `payload_trigger`) so the household can initiate a panel panic/PA from HA. Blocked on proving a Connect command (or other safe path) that actually starts PA / force-trigger on the Premier Elite; today we only detect physical Silent PA zones and report live/triggered state from real alarms, with no validated network-side panic opcode.
- **Stamp the version into the log on startup** — Log the running app version (`__version__`) as the first line (or among the first) when the app starts, so a household log dump (or a support/incident report) says which release produced it without cross-referencing the Supervisor UI or `config.yaml`.
