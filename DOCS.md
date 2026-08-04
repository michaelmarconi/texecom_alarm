# Texecom Alarm

Bridge a Texecom Premier Elite panel (ComIP / Texecom Connect) to Home Assistant
over MQTT discovery — with reliable reconnect behaviour and Home arm mode support.

> **Status:** under active development. The Add-on shell and configuration surface
> are wired; panel protocol and MQTT entity publishing land via the implementation
> plan.

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

All options below are Supervisor `config.yaml` / `options.json` keys. Required
fields must be non-empty before the bridge can start.

### Option: `panel_host`

Hostname or IP address of the panel's ComIP / Texecom Connect module on the LAN.
**Required.**

### Option: `panel_port`

TCP port for the ComIP / Connect session. Default: `10001`.

### Option: `udl_password`

Panel UDL login password. Change this from the factory default on any panel still
using it. **Required.** Treated as a secret in the Supervisor UI.

### Option: `mqtt_host`

MQTT broker hostname or IP. Standing runtime dependency for discovery and state
publishing. **Required.**

### Option: `mqtt_port`

MQTT broker port. Default: `1883`.

### Option: `mqtt_username`

Optional MQTT username. Leave empty when the broker allows anonymous clients.

### Option: `mqtt_password`

Optional MQTT password. Leave empty when unused. Treated as a secret in the
Supervisor UI.

### Option: `mqtt_topic_prefix`

Root prefix for discovery and state topics this Add-on publishes. Default:
`texecom`.

### Option: `part_arm_away`

Mode byte sent with the shared arm command for Home Assistant **Away**. Integer
`0`–`255`. Default: `0`. Must match this installation's engineer Part-Arm layout
— do not assume another household's mapping.

### Option: `part_arm_night`

Mode byte for Home Assistant **Night**. Integer `0`–`255`. Default: `1`.

### Option: `part_arm_home`

Mode byte for Home Assistant **Home**. Integer `0`–`255`. Default: `2`.

Part-Arm slot roles are install-specific and cannot be auto-detected from
`GETAREADETAILS`; set these three fields to the mode bytes your panel expects.

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
