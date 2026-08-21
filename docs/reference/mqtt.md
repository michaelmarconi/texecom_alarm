# MQTT topics and payloads

Default topic prefix is `texecom`. Replace it with your **MQTT topic prefix**
option if you changed it.

This is lookup for automations and debugging. For install options see
[Documentation](../../DOCS.md).

## App liveness

| Topic | Retained | Payload |
|-------|----------|---------|
| `{prefix}/status` | yes | `online` while the app runs; MQTT last-will `offline` when the process dies |

Alarm, zone, and **Alarm Panel Connection** discovery all use this as
`availability_topic`. Panel-link health is **not** this topic.

## Panel connection

| Topic | Retained | Payload |
|-------|----------|---------|
| `{prefix}/panel_connection/state` | yes | `ON` = link live and trusted; `OFF` = degraded or reconnecting |

Entity: `binary_sensor.texecom_alarm_panel_connection` (name: Alarm Panel
Connection). See [Availability vs panel connection](../concepts/availability-and-connection.md).

## Alarm control panel

| Topic | Role | Payload |
|-------|------|---------|
| `{prefix}/alarm/state` | State (retained) | `disarmed`, `arming`, `pending`, `armed_away`, `armed_home`, `armed_night`, `triggered` |
| `{prefix}/alarm/command` | Command (Home Assistant → app) | `ARM_AWAY`, `ARM_HOME`, `ARM_NIGHT`, `DISARM` |
| `{prefix}/alarm/attributes` | Last-trigger snapshot (retained) | JSON: `last_trigger_zone` (int or `null`), `last_trigger_time` (ISO-8601 UTC) |

Entity: `alarm_control_panel.texecom_alarm_arm_status`.

`ARM_HOME` / `ARM_NIGHT` are ignored (logged, not sent) if that mode is not
mapped to a Part-Arm slot. `ARM_AWAY` always uses full arm.

Home Assistant MQTT discovery config:
`homeassistant/alarm_control_panel/texecom_alarm_arm_status/config`.

## Zones

| Topic | Role | Payload |
|-------|------|---------|
| `{prefix}/zone/{n}/state` | State (retained) | `1` = open / active; `0` = closed / secure |

`{n}` is the panel zone number (1-based). Unused slots are not published.

Entity IDs look like `binary_sensor.texecom_alarm_front_door_1` — slug from the
panel zone name plus the zone number. Two zones with the same name stay
distinct because of the number suffix.

Discovery: `homeassistant/binary_sensor/{object_id}/config`.

Zones do not get a device class from the panel. Set **Show as** in Home
Assistant if you want door/window/motion icons.

## Device grouping

Discovery payloads share one MQTT device (`identifiers: ["texecom_alarm"]`,
name **Texecom Alarm**, manufacturer Texecom, model Premier Elite) so Home
Assistant groups the alarm, connection sensor, and zones together.
