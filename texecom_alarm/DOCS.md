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
[Home Assistant loses your Texecom panel the moment the alarm goes off](https://github.com/michaelmarconi/texecom_alarm/blob/main/docs/ha-loses-panel-during-alarm.md).

- Stop anything else that already holds a **Connect login** to the *same*
  module before you **start** this add-on (one Connect session per module).
  Once this add-on is logged in, you can normally use the official Texecom
  smartphone app at the same time if that app uses a *different* module.

## Installation

1. Add `https://github.com/michaelmarconi/texecom_alarm#app` under
   **Settings → Add-ons → Add-on store → ⋮ → Repositories**
   (`#app` is the thin store catalogue, CI-synced from `main`).
2. Install **Texecom Alarm** from that repository.
3. Open **Configuration** and fill in the options below.
4. Start the add-on and check the log for a successful panel login.

## Configuration

### Panel

| Option | What it is |
|--------|------------|
| **Panel host** | IP address or hostname of the **dedicated local network module** this add-on should use (typically a ComIP reserved for Home Assistant). Not the module used for the Texecom app or monitoring-station signalling. Both often answer on port 10001 — picking the signalling box is a common trap. See **Before you start** above. **Required.** |
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

If the panel connection drops, the add-on retries automatically using the
same wait interval no matter what caused the disconnect — an ordinary drop
and a drop that follows a real alarm are treated the same way. It keeps
retrying indefinitely until the panel answers again.

You can leave the default unless you have a reason to change it.

If Home Assistant is locked out **only during a real alarm** (Disarm does
nothing; the Texecom app and keypad still work), you may be talking to the
wrong network module — see
[Home Assistant loses your Texecom panel the moment the alarm goes off](https://github.com/michaelmarconi/texecom_alarm/blob/main/docs/ha-loses-panel-during-alarm.md).

| Option | Default | Meaning |
|--------|---------|---------|
| Reconnection delay | `5` seconds | Wait before retrying after any panel disconnect |

### Soft trust recovery

If the panel path looks connected but is untrustworthy (for example a routine
keepalive check-in fails, or an arm/disarm command is rejected or times out),
**Alarm Panel Connection** goes off while zone and alarm entities keep their
last-known state. A successful keepalive can restore the link. If it stays off
longer than the window below, the add-on tears down the session and logs in
again (without restarting the add-on, and without silently re-trying the
failed arm/disarm).

| Option | Default | Meaning |
|--------|---------|---------|
| Force reconnect after | `90` seconds | How long Connection may stay off before tear-down / re-login |

You can leave the default unless live walks suggest a different window.

### Check-in cadence and patience

The add-on checks in with the panel on a fixed schedule to confirm the
connection is still alive, regardless of how busy the panel is. A single
refused or unanswered check-in does not end the session — **Alarm Panel
Connection** stays healthy until check-ins have failed continuously for the
patience period below, at which point the add-on reconnects and logs in
again automatically.

| Option | Default | Meaning |
|--------|---------|---------|
| Check-in interval | `15` seconds | How often the add-on checks in with the panel |
| Check-in patience | `45` seconds (about three check-ins) | How long continuous check-in failure is tolerated before the session is treated as dead |

Check-in patience must be at least the check-in interval. You can leave the
defaults unless live use suggests otherwise.

### Reconciliation poll

Separately from Connection, the add-on periodically double-checks the alarm
state against the panel and corrects it if they disagree — this is a
belt-and-braces check, not a connectivity signal. A slow or failed
reconciliation check does **not** affect Alarm Panel Connection; that stays
driven only by keepalives and arm/disarm outcomes above.

| Option | Default | Meaning |
|--------|---------|---------|
| Recheck interval | `300` seconds (5 minutes) | How often the add-on re-checks alarm state against the panel |

You can leave the default unless you have a reason to change it.

### Logging

| Level | When to use it |
|-------|----------------|
| **WARNING** | Quiet — warnings and errors only |
| **INFO** | Everyday use (default) |
| **DEBUG** | More detail when something looks wrong |
| **TRACE** | Full panel traffic — for diagnosing tricky connection issues |

## What appears in Home Assistant

- An **alarm control panel** (Away, Night, Home, and Disarm)
- Three **ready-to-arm** switches (Away, Home, Night) that start **on**
- A **Blocked arm** event when an arm is refused because the matching switch is off
- A **sensor for each zone** the panel reports as in use
- **Alarm Panel Connection** — shows whether the link to the panel is healthy
- A short **last-trigger** summary of what happened just before an alarm

Zone names come from the panel when the add-on starts — you do not maintain a
zone list by hand.

If the panel link drops, alarm and zone entities stay available with their last
known state. Use **Alarm Panel Connection** to tell live data from a stale link.

If a ready-to-arm switch is **off**, that arm is not sent to the panel — even
when Home Assistant itself requested it. The alarm card shows a brief **Arming**,
then returns to the state it already was. **Disarm** always works. Turning a
ready switch off while the house is already armed does not disarm. Household
rules (open doors, guests, time of day) belong in your own automations that
flip those switches. Walkthrough:
[Refuse an arm that is not ready](https://github.com/michaelmarconi/texecom_alarm/blob/main/docs/how-to/use-ready-to-arm.md).

The **Blocked arm** event names the mode (`away`, `home`, or `night`) and does
not include a reason, so a notify automation can speak for the household.

## Automations stay in Home Assistant

Notifications, HomeKit, and household arming rules belong in your own Home
Assistant setup — not inside this add-on. Use the ready-to-arm switches and
the blocked-arm event as the generic refuse mechanism.

## Further reading

These open the GitHub repository — Home Assistant does not serve the extra
markdown files from this App.

- [Getting started](https://github.com/michaelmarconi/texecom_alarm/blob/main/README.md#getting-started)
- [Configure Home and Night](https://github.com/michaelmarconi/texecom_alarm/blob/main/docs/how-to/configure-part-arm.md)
- [Refuse an arm that is not ready](https://github.com/michaelmarconi/texecom_alarm/blob/main/docs/how-to/use-ready-to-arm.md)
- [Stop other Connect clients](https://github.com/michaelmarconi/texecom_alarm/blob/main/docs/how-to/stop-other-connect-clients.md)
- HA locked out only while the alarm is sounding:
  [wrong network module / COM-port signalling](https://github.com/michaelmarconi/texecom_alarm/blob/main/docs/ha-loses-panel-during-alarm.md)
- [Availability vs panel connection](https://github.com/michaelmarconi/texecom_alarm/blob/main/docs/concepts/availability-and-connection.md)
- [MQTT topics](https://github.com/michaelmarconi/texecom_alarm/blob/main/docs/reference/mqtt.md)

## Support

- Overview: [README](https://github.com/michaelmarconi/texecom_alarm/blob/main/README.md)
- Issues: [open with a template](https://github.com/michaelmarconi/texecom_alarm/issues/new/choose)
  (do not paste UDL or MQTT passwords)
- Contributing: [CONTRIBUTING.md](https://github.com/michaelmarconi/texecom_alarm/blob/main/CONTRIBUTING.md)

## Credits

Add-on icon: [Home security icons created by juicy_fish - Flaticon](https://www.flaticon.com/free-icons/home-security).

## License

Copyright © 2026 Michael Marconi.

Code is licensed under the [MIT License](https://github.com/michaelmarconi/texecom_alarm/blob/main/LICENSE). The add-on icon remains under
Flaticon terms (see Credits).
