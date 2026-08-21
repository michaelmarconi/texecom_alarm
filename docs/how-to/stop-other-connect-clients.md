# How to free the panel module for this app

The panel’s network module accepts **one Connect login at a time**. You cannot
run this app and another Connect client against the **same** module together.

Typical other clients: Wintex, another Home Assistant MQTT bridge, or the
Texecom smartphone app if it is using **this** module rather than a separate
signalling board.

## Before you start

- MQTT broker already running (this app talks to Home Assistant over MQTT
  discovery).
- **Panel host** is the dedicated local module, not the installer signalling
  module — see
  [Home Assistant loses your Texecom panel the moment the alarm goes off](../ha-loses-panel-during-alarm.md).

## Cut over

1. Note any Home Assistant automations, dashboards, or HomeKit exposures that
   target the current alarm or zone entities. Those stay in **your** Home
   Assistant configuration; this app does not copy them.
2. Stop and uninstall anything else logged into the same module. Wait until that
   client is fully stopped — a lingering login blocks this app.
3. Install **Texecom Alarm**, fill [Configuration](../../DOCS.md#configuration)
   (panel, MQTT, Part-Arm slots).
4. Start this app. Check the log for a successful login, then zone enumeration.
5. Confirm **Alarm Panel Connection** is on, the alarm entity is present, and
   in-use zones appear (names come from the panel).

If discovery left orphan or `_2`-suffixed MQTT entities from a previous bridge,
remove those in Home Assistant (or, in the local sim, use the entity-reset
script in [`docs/run.md`](../run.md#entity-reset-no-duplicate--suffixed-mqtt-ids)).

## After cut over

- Point automations at the new entity IDs if they changed. Zone `unique_id`s
  are `texecom_alarm_{slug}_{zone_number}` from the panel name; they will not
  match another bridge’s IDs.
- Keep household rules (auto-arm, notifications, wrappers) in Home Assistant.
  This app only bridges the panel.

## Related

- [Getting started](../../README.md#getting-started)
- [Configure Home and Night](configure-part-arm.md)
