# How to map Home and Night to Part-Arm slots

Texecom **Away** is always the panel’s full arm. **Home** and **Night** in Home
Assistant are labels for engineer-programmed **Part-Arm** slots. Every
installation is different — this app does not guess the mapping.

## What you need

- The add-on installed, with **Panel host** pointed at your dedicated local
  module (see [Documentation](../../texecom_alarm/DOCS.md)).
- A note from your installer, or a few minutes on the keypad in engineer mode,
  of which Part-Arm slots exist (1, 2, and/or 3) and what each one is for.

## Set the options

In the add-on **Configuration** tab, each of **Part-Arm slot 1**, **slot 2**,
and **slot 3** is one of:

| Choice | Meaning |
|--------|---------|
| **Home** | This slot is the Home Assistant **Home** button |
| **Night** | This slot is the Home Assistant **Night** button |
| **Unused** | This slot is not used (or you do not want it in Home Assistant) |

Rules:

- **Away** is not a Part-Arm choice. It always uses full arm.
- Do not assign Home (or Night) to more than one slot.
- Leave unused slots as **Unused**.

Example: if your engineer set Part-Arm 1 as night-time downstairs-only, and
Part-Arm 2 as “people home, perimeter set”, choose **Night** on slot 1 and
**Home** on slot 2. Slot 3 stays **Unused** unless you actually use it.

Save, then restart the add-on (or rebuild, on a local App) so discovery picks
up which arm buttons to offer.

## Check it

1. Confirm **Alarm Panel Connection** is on.
2. Arm **Night** from Home Assistant — the panel should enter that Part-Arm,
   not full Away.
3. Disarm, then try **Home** the same way.
4. **Away** should still fully arm the panel.

If Home or Night does nothing, the slot mapping is wrong or that Part-Arm is
not programmed. If Away is wrong, you are not looking at Part-Arm options —
Away is not configured there.

## Related

- Option reference: [Documentation](../../texecom_alarm/DOCS.md#part-arm-slots-home-and-night)
- Why Away is never a Part-Arm slot: [protocol overview](../protocol-overview.md#arm-part-arm-and-disarm)
