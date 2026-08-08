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

**Panel UDL password** — the panel login used by Wintex / Connect clients
(UDL = User Data Link). Default is usually `1234`, but check with your engineer if
login fails. Default in the Add-on schema: `1234`. Treated as a secret in the
Supervisor UI.

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

### Option: `part_arm_1` / `part_arm_2` / `part_arm_3`

Which HA arm button (Home / Night / Away) each engineer-configured **Part-Arm
slot** should use — or Unused if the slot isn't configured on your panel.

Supervisor `list(...)` tokens are the Configuration radio labels (there is no
separate label/value). Schema options are therefore the display tokens
`Home 🏠`, `Night 🌙`, `Away 🔒`, or `Unused` (defaults `Unused`). Python still
canonicalises those selections — and any legacy lowercase `home` / `night` /
`away` / `unused` values — to `home|night|away|unused` for shared arm-command
mapping (`cmd=6`).

Defaults (map each slot for your installation — do not assume a household layout):

| Option | Default |
|--------|---------|
| `part_arm_1` | `Unused` |
| `part_arm_2` | `Unused` |
| `part_arm_3` | `Unused` |

Under the hood the Add-on still issues the confirmed shared arm command (`cmd=6`)
with mode byte equal to the Part-Arm slot number (slot 1 → byte `1`, slot 2 →
byte `2`, slot 3 → byte `3`). Away that is not assigned to any Part-Arm slot uses
the confirmed full-arm mode byte `0`. Unused slots are not offered as HA arm
targets. Part-Arm roles cannot be auto-detected from `GETAREADETAILS` — set these
fields to match your panel's engineer layout. Do not assign the same HA mode to
more than one slot.

### Option: `reconnect_normal_attempts`

How many reconnect tries are treated as the "normal" budget after an ordinary
panel disconnect (for example around arm/disarm). Integer ≥ `1`. Default: `4`.
Tunable — not a final hardcoded value (ADR-002). After this many attempts the
Add-on keeps retrying at the same interval rather than exiting.

### Option: `reconnect_normal_interval_seconds`

Seconds to wait between normal-budget reconnect attempts. Default: `2.5`
(about 10s for the default attempt count). May be a fraction.

### Option: `reconnect_trigger_attempts`

Reconnect try count for the longer budget used when the last decoded alarm
state was `triggered` before the disconnect. Integer ≥ `1`. Default: `18`.
Tunable — based on a single observed trigger recovery window.

### Option: `reconnect_trigger_interval_seconds`

Seconds between trigger-budget reconnect attempts. Default: `5` (about 90s for
the default attempt count).

### Option: `log_level`

How much detail the Add-on writes to its logs. Supervisor `list(...)` tokens are
the Configuration radio labels: `WARNING`, `INFO`, `DEBUG`, or `TRACE`. Default:
`INFO`.

| Level | Typical use |
|-------|-------------|
| `WARNING` | Quiet production — warnings and errors only |
| `INFO` | Day-to-day (default) — start, enumerate, reconnect, connectivity |
| `DEBUG` | App-meaningful zone/area/command handling |
| `TRACE` | Full panel session traffic (below DEBUG severity) |

Choosing a level includes that level and all more severe messages. Changing this
option follows the Add-on's existing options-apply rules (restart when required).

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

## Credits

Add-on icon: [Home security icons created by juicy_fish - Flaticon](https://www.flaticon.com/free-icons/home-security).

## License

See the repository licence (to be added before public Store distribution).
