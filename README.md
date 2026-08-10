# Texecom Alarm

Connect a Texecom Premier Elite alarm panel to Home Assistant over MQTT.

Arm and disarm from Home Assistant (including Home and Night modes), see zone
open/closed status, and tell whether the panel link is healthy.

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

## What you get

- An **alarm control panel** in Home Assistant (Away, Night, Home, disarm)
- A **sensor per zone** reported by the panel (unused zones are skipped)
- A **panel connection** sensor so you can tell live data from a dropped link
- A short **last-trigger snapshot** of what happened just before an alarm

Zones and names come from the panel when the add-on starts — you do not maintain
a zone list by hand.

## Reliability

Built to keep working when the panel link gets messy — for example during an
alarm, when other apps share the network path, or when the connection drops.

- Ignores unexpected panel chatter instead of crashing
- Reconnects on its own (and waits longer after a real alarm, when the panel
  often blocks the network briefly)
- Keeps your last known alarm and zone states in Home Assistant; a separate
  **panel connection** sensor shows whether the link is live or catching up
- Recovers stuck sessions without a manual add-on restart

## Before you start

- A Texecom Premier Elite panel with a network module (ComIP / Texecom Connect)
- An MQTT broker Home Assistant can use (for example the Mosquitto add-on)
- Only **one** app may talk to the panel at a time — stop anything else using
  that network connection before you start this add-on

## Setup

1. Install **Texecom Alarm**.
2. Open **Configuration** and set the panel address, UDL password, MQTT
   settings, and which Part-Arm slots mean Home / Night on your panel.
3. Start the add-on and check the log for a successful panel login.

Full option descriptions: [Documentation](DOCS.md).

## Optional: nicer names and icons in Home Assistant

Zone entities use the panel’s labels and ship without a device class (the panel
does not say “door” vs “PIR” vs “shock”). That is enough for automations; tidy
presentation is optional.

In Home Assistant, open an entity → **Settings** (gear):

- **Name** — short display name (for example `Front door`). A custom name also
  avoids the long `Texecom Alarm …` prefix on entity cards.
- **Show as** — device class (`door`, `window`, `motion`, `vibration`, …) for
  icons and open/closed vs detected/clear wording.

Other options: set a **name** on individual Lovelace cards only, or leave the
defaults and use entity IDs in automations.

## Credits

Add-on icon: [Home security icons created by juicy_fish - Flaticon](https://www.flaticon.com/free-icons/home-security).

## License

Code is licensed under the [MIT License](LICENSE). The add-on icon remains under
Flaticon terms (see Credits). Protocol notes are observational — see
[legal stance](docs/legal-stance.md).

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
