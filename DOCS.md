# Texecom Alarm

Connect a Texecom Premier Elite alarm panel to Home Assistant over MQTT.

Arm and disarm from Home Assistant (including **Home** and **Night**), see which
zones are open or closed, and tell whether the link to the panel is healthy.

## Before you start

- A Texecom Premier Elite panel
- An MQTT broker Home Assistant can use (for example the Mosquitto add-on)
- A **dedicated local network module** for this add-on — usually a **ComIP**
  (or equivalent Ethernet board) that is *not* the same module the installer
  fitted for the Texecom smartphone app and the monitoring station

Premier Elite systems often have two IP-capable boards: one for alarm
reporting and the vendor app, and optionally a second for local LAN control.
Each COM port on the panel can only do one job at a time. If Home Assistant
logs into the reporting module, a real alarm will seize that port, kick HA
off, and Disarm from the dashboard will do nothing until signalling finishes.
Hayes modem commands (`ATH0`, `ATZ`) in the add-on log are a strong sign you
are on that path.

**Buy and fit a ComIP (or keep HA on one you already have that is unused for
reporting)** so this add-on has a clean Connect channel. Leave the installer's
module for the app and monitoring. Point **Panel host** at the dedicated
module’s IP. If you only have the signalling module, day-to-day arm and zone
status can still work; disarm-during-alarm probably will not. More detail:
[Home Assistant loses your Texecom panel the moment the alarm goes off](docs/ha-loses-panel-during-alarm.md).

- Stop anything else that already holds a **Connect login** to the *same*
  module before you **start** this add-on (one Connect session per module).
  Once this add-on is logged in, you can normally use the official Texecom
  smartphone app at the same time if that app uses a *different* module.

## Installation

1. Install **Texecom Alarm**.
2. Open **Configuration** and fill in the options below.
3. Start the add-on and check the log for a successful panel login.

## Configuration

### Panel

| Option | What it is |
|--------|------------|
| **Panel host** | IP address or hostname of the **dedicated local network module** this add-on should use (typically a ComIP reserved for Home Assistant). Not the module used for the Texecom app or monitoring-station signalling. Both often answer on port 10001 — picking the signalling box is a common trap. See [Before you start](#before-you-start). **Required.** |
| **Panel port** | Network port for the panel connection. Default: `10001`. |
| **Panel UDL password** | Password used to log in to the panel (same idea as Wintex / Connect). Default is often `1234` — ask your installer if login fails. Treat this as a LAN credential: anyone who can reach the panel’s network module on this port can Connect-login with the same password, so change the factory UDL on the panel (and match it here) if your LAN is not fully trusted. |

### MQTT

| Option | What it is |
|--------|------------|
| **MQTT host** | Your MQTT broker (for example `core-mosquitto`). **Required.** |
| **MQTT port** | Broker port. Default: `1883`. |
| **MQTT username / password** | Optional. Leave blank if your broker does not need a login. |
| **MQTT topic prefix** | Root name for topics this add-on publishes. Default: `texecom`. |

### Part-Arm slots (Home and Night)

Your engineer may have set up **Part-Arm** modes on the panel (for example “at
home” or “night”). These three options tell the add-on which Part-Arm slot
matches which Home Assistant button:

| Option | Choose |
|--------|--------|
| **Part-Arm slot 1** | **Home 🏠**, **Night 🌙**, or **Unused** |
| **Part-Arm slot 2** | Same choices |
| **Part-Arm slot 3** | Same choices |

Defaults are all **Unused**. Set them to match how your panel was programmed —
every installation is different.

**Away** is always full arm on the panel. You do not map Away to a Part-Arm slot.

Do not assign the same Home Assistant mode (Home or Night) to more than one slot.

### Reconnect behaviour

If the panel connection drops, the add-on retries automatically. After a normal
disconnect it retries more quickly; after a drop that follows a real alarm it
waits longer and tries more times. That longer wait is a safety net for when
Home Assistant still shares the panel’s alarm-reporting module. A dedicated
ComIP used only for local control is not expected to drop at trigger.

You can leave the defaults unless you have a reason to change them.

If Home Assistant is locked out **only during a real alarm** (Disarm does
nothing; the Texecom app and keypad still work), you may be talking to the
wrong network module — see
[Home Assistant loses your Texecom panel the moment the alarm goes off](docs/ha-loses-panel-during-alarm.md).

| Option | Default | Meaning |
|--------|---------|---------|
| Reconnect attempts (normal) | `4` | How many quick retries after an ordinary drop |
| Reconnect interval (normal) | `2.5` seconds | Wait between those retries |
| Reconnect attempts (after trigger) | `18` | Longer retry budget after an alarm |
| Reconnect interval (after trigger) | `5` seconds | Wait between those retries |

### Soft trust recovery

If the panel path looks connected but is untrustworthy (for example an arm
command is rejected, or a periodic house-state check fails), **Alarm Panel
Connection** goes off while zone and alarm entities keep their last-known state.
A successful house-state check can restore the link. If it stays off longer than
the trust fail window, the add-on tears down the session and logs in again
(without restarting the add-on, and without silently re-trying the failed
arm/disarm).

| Option | Default | Meaning |
|--------|---------|---------|
| Trust fail window | `90` seconds | How long Connection may stay off before tear-down / re-login |

You can leave the default unless live walks suggest a different window.

### Logging

| Level | When to use it |
|-------|----------------|
| **WARNING** | Quiet — warnings and errors only |
| **INFO** | Everyday use (default) |
| **DEBUG** | More detail when something looks wrong |
| **TRACE** | Full panel traffic — for diagnosing tricky connection issues |

## What appears in Home Assistant

- An **alarm control panel** (Away, Night, Home, and Disarm)
- A **sensor for each zone** the panel reports as in use
- **Alarm Panel Connection** — shows whether the link to the panel is healthy
- A short **last-trigger** summary of what happened just before an alarm

Zone names come from the panel when the add-on starts — you do not maintain a
zone list by hand.

If the panel link drops, alarm and zone entities stay available with their last
known state. Use **Alarm Panel Connection** to tell live data from a stale link.

## Automations stay in Home Assistant

Notifications, HomeKit, and household arming rules belong in your own Home
Assistant setup — not inside this add-on.

## Further reading

- [Getting started](README.md#getting-started)
- [Configure Home and Night](docs/how-to/configure-part-arm.md)
- [Stop other Connect clients](docs/how-to/stop-other-connect-clients.md)
- HA locked out only while the alarm is sounding:
  [wrong network module / COM-port signalling](docs/ha-loses-panel-during-alarm.md)
- [Availability vs panel connection](docs/concepts/availability-and-connection.md)
- [MQTT topics](docs/reference/mqtt.md)

## Support

- Overview: [README](README.md)
- Issues: use the GitHub repository linked from the add-on store listing

## Credits

Add-on icon: [Home security icons created by juicy_fish - Flaticon](https://www.flaticon.com/free-icons/home-security).

## License

Copyright © 2026 Michael Marconi.

Code is licensed under the [MIT License](LICENSE). The add-on icon remains under
Flaticon terms (see Credits).
