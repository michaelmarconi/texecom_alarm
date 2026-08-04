# Texecom Alarm

Bridge a Texecom Premier Elite panel (ComIP / Texecom Connect) to Home Assistant
over MQTT discovery — with reliable reconnect behaviour and Home arm mode support.

> **Status:** under active development. The Add-on shell runs; panel protocol and
> MQTT entity publishing land via the implementation plan. Configuration options
> below mark **available now** vs **planned**.

## Installation

1. Add this repository as a Local Add-on (Supervisor Local Apps / apps
   development) or, once published, install from the Add-on Store repository URL.
2. Install **Texecom Alarm**, then open **Configuration** and set the options
   below.
3. Start the Add-on and confirm it reaches `started` in the logs.

**Important — single panel TCP session:** the ComIP / Connect network module
accepts only **one** client connection. Stop any other bridge (for example
`the prior MQTT bridge`) before starting this Add-on, or login and zone enumeration will
fail.

## Configuration

### Option: `message` _(temporary bootstrap)_

Placeholder string written to the log on start to prove the Supervisor
`options.json` → `bashio::config` path. Removed once real options are wired.

### Planned options

These will replace `message` and are required for a working install (exact keys
may shift slightly before first public release — this section stays the source of
truth for the Supervisor docs tab):

| Option | Purpose |
| --- | --- |
| Panel host / port | ComIP / Connect TCP endpoint on the LAN |
| UDL password | Panel login credential (change from the factory default) |
| MQTT broker host, port, credentials, topic prefix | Standing runtime dependency for discovery and state |
| Part-Arm slot → HA mode map | Which panel Part-Arm slot means Away / Night / Home for this installation (required — slot roles are install-specific and cannot be auto-detected from `GETAREADETAILS`) |
| Log level | Prefer `debug` while validating stability so every connect / login / enumerate / subscribe / arm / disarm / resync / reconnect step is traceable from Add-on logs alone |

## What it publishes (MQTT discovery)

Once implemented, the Add-on will create entities that behave like any other
MQTT-discovered device:

- One `alarm_control_panel` (Away / Night / Home / disarm)
- One `binary_sensor` per **used** zone reported by the panel (unused slots are
  omitted)
- A dedicated **panel-link connectivity** sensor (separate from entity
  availability)
- A short **last-trigger snapshot** of recent activity before a trigger

Entity availability follows the Add-on process (MQTT Last-Will). A dropped panel
link must **not** mark the alarm or zone entities unavailable — use the
connectivity sensor to tell live data from stale data.

## Household automations stay in Home Assistant

Arming rules, notifications, and HomeKit exposure belong in your own Home
Assistant configuration — not inside this Add-on.

## Support

- Project docs: [README](README.md), [architecture](docs/architecture.md),
  [protocol reference](docs/protocol-reference.md)
- Issues: use the GitHub repository linked from `config.yaml` `url`

## Changelog & Releases

See [CHANGELOG.md](CHANGELOG.md). Versions follow Semantic Versioning.

## License

See the repository licence (to be added before public Store distribution).
