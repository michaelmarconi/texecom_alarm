# How to refuse an arm that is not ready

The add-on publishes three **Ready to arm** switches — Away, Home, and Night —
that start **on**. Turn a switch **off** when that mode must not set the panel.
Household rules (open doors, guests, time of day) stay in your Home Assistant
automations; this add-on only honours the switches.

## What you need

- The add-on running and logged into the panel (see
  [Documentation](../../texecom_alarm/DOCS.md)).
- The three switches and the **Blocked arm** event in Home Assistant.

## Use the switches

1. Confirm **Ready to arm Away**, **Home**, and **Night** are on after a fresh
   start (they start on so arming works until you turn one off).
2. Turn off the mode you want to block. Turning a switch off while the house
   is already armed does **not** disarm.
3. Tap that mode on the alarm card (or from HomeKit / the iOS app if those
   still show the button). The panel must not arm. The card shows a brief
   **Arming**, then returns to the state it already was.
4. **Disarm** still works even if every ready switch is off.

HomeKit and the iOS app may still offer a mode whose switch is off. Choosing
it must still refuse — do not treat a missing button as the safety mechanism.

## Notify on a blocked arm

When an arm is refused, Home Assistant gets a **Blocked arm** event that names
the mode (`away`, `home`, or `night`) and does not include a reason. Use that
event in an automation if you want a notification; write the wording yourself.

MQTT lookup: [MQTT reference](../reference/mqtt.md#blocked-arm-event).

## Related

- Option and entity overview: [Documentation](../../texecom_alarm/DOCS.md#what-appears-in-home-assistant)
- Topics and payloads: [MQTT reference](../reference/mqtt.md#ready-to-arm)
