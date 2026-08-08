# Texecom Alarm

Connect a Texecom Premier Elite alarm panel to Home Assistant over MQTT.

Arm and disarm from Home Assistant (including **Home** and **Night**), see which
zones are open or closed, and tell whether the link to the panel is healthy.

## Before you start

- A Texecom Premier Elite panel with a network module (ComIP / Texecom Connect)
- An MQTT broker Home Assistant can use (for example the Mosquitto add-on)
- Stop anything else that already holds a **Connect/ComIP login** to the panel
  before you **start** this add-on (the panel’s network module only accepts one
  of those sessions at a time). Once this add-on is logged in, you can normally
  use the official Texecom smartphone app at the same time — it does not
  monopolise the link. Commands may occasionally be slower or rejected under
  heavy concurrent use; that is not the same as the app “taking over” the channel.

## Installation

1. Install **Texecom Alarm**.
2. Open **Configuration** and fill in the options below.
3. Start the add-on and check the log for a successful panel login.

## Configuration

### Panel

| Option | What it is |
|--------|------------|
| **Panel host** | IP address or hostname of the panel’s network module on your LAN. **Required.** |
| **Panel port** | Network port for the panel connection. Default: `10001`. |
| **Panel UDL password** | Password used to log in to the panel (same idea as Wintex / Connect). Default is often `1234` — ask your installer if login fails. |

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
disconnect it retries more quickly; after a real alarm trigger it waits longer
and tries more times (panels often block the network briefly while sirens run).

You can leave the defaults unless you have a reason to change them.

| Option | Default | Meaning |
|--------|---------|---------|
| Reconnect attempts (normal) | `4` | How many quick retries after an ordinary drop |
| Reconnect interval (normal) | `2.5` seconds | Wait between those retries |
| Reconnect attempts (after trigger) | `18` | Longer retry budget after an alarm |
| Reconnect interval (after trigger) | `5` seconds | Wait between those retries |

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
- **Alarm Panel Connected** — shows whether the link to the panel is healthy
- A short **last-trigger** summary of what happened just before an alarm

Zone names come from the panel when the add-on starts — you do not maintain a
zone list by hand.

If the panel link drops, alarm and zone entities stay available with their last
known state. Use **Alarm Panel Connected** to tell live data from a stale link.

## Automations stay in Home Assistant

Notifications, HomeKit, and household arming rules belong in your own Home
Assistant setup — not inside this add-on.

## Support

- Overview: [README](README.md)
- Issues: use the GitHub repository linked from the add-on store listing

## Credits

Add-on icon: [Home security icons created by juicy_fish - Flaticon](https://www.flaticon.com/free-icons/home-security).

## License

Copyright © 2026 Michael Marconi.

Code is licensed under the [MIT License](LICENSE). The add-on icon remains under
Flaticon terms (see Credits).
