# Current Home Assistant usage of the Texecom alarm integration

## Purpose

This is a functional spec of everything the existing `the prior MQTT bridge` add-on + the
Marconi household's Home Assistant config layer does today with the Texecom alarm
system. It's meant to be handed to whoever (human or agent) designs/builds the
`texecom_alarm` replacement app, as the "must not regress" checklist. See
`docs/brief.md` in this same repo for the background/problem statement.

Source repo for this analysis: the main HA config repo (`/config`), specifically
`configuration/automations/`, `configuration/scripts/`, `configuration/templates/`,
`configuration/homekit/bridges.yaml`, `automations.yaml`, and the `.storage/lovelace.*`
dashboards.

## Entity architecture (two-layer)

1. **Raw entity** `alarm_control_panel.texecom_alarm_arm_status` — created by
   `the prior MQTT bridge`'s MQTT discovery. Reflects the panel's real state.
2. **Wrapper entity** `alarm_control_panel.house_alarm_panel` — a Template Alarm
   Control Panel (`configuration/templates/house_alarm.yaml`) that is the entity
   **every single automation, script, and HomeKit exposure actually targets.** It:
   - Adds guard conditions before arming: blocks `arm_away` unless `binary_sensor.all_doors`
     and `binary_sensor.windows_with_sensors` are all off; blocks `arm_night` unless
     doors + `binary_sensor.ground_floor_windows_excluding_velux` are off, it's after
     dark (`sun.sun` below horizon), and no guests (`input_boolean.guests_toggle` off).
   - On a blocked arm attempt, disarms (safety) and sends a push notification via
     `script.notify_actor` explaining *why* (doors open / windows open / daytime /
     guests present), falling back to `notify.notify_michael_talia`.
   - Forwards successful arm/disarm calls straight through to
     `alarm_control_panel.texecom_alarm_arm_status` with a dummy `code: 0` (real add-on
     doesn't need a code; `code_arm_required: false`).
   - **Only exposes `arm_away` and `arm_night` handlers.** There is no `arm_home`
     handler defined at all today — consistent with Home arm never having worked.
3. **Zone entities**: ~35 `binary_sensor.texecom_alarm_<zone_slug>` entities (door
   contacts, window contacts, shock sensors, PIR motion sensors) — full inventory
   below.

**No raw MQTT topics** (`the prior MQTT bridge/...`) are consumed directly anywhere in the
config — everything goes through HA's MQTT-discovered entities. This gives some
flexibility on wire-level topic design for the replacement, as long as it still ends
up creating equivalent HA entities (via MQTT discovery or a native integration).

## Full zone entity inventory

Pulled from the entities actually shown on the "Security" Lovelace dashboard
(`.storage/lovelace.dashboard_security`):

**Door contacts**
`front_door`, `utility_door`, `kitchen_l_slide`, `kitchen_r_slide`,
`living_rm_fr_sld`, `living_rm_l_slde`, `guest_bed_slide`

**Window contacts**
`utility_l_window`, `utility_r_window`, `pantry_r_window`, `guest_bed_l_wind`,
`guest_bed_wind_r`, `guest_bath_wind`, `mstr_bed_l_wind_2`, `mstr_bath_big_l`,
`mstr_bath_big_r`, `mstr_bath_sml_l`, `mstr_bath_sml_s`, `ethans_rm_l_wind`,
`ethans_rm_r_wind`

**Shock sensors** (separate from the open/close contacts on the same openings)
`ethan_l_win_shk`, `ethan_r_win_shk`, `guest_bd_l_w_shk`, `guest_bd_w_r_shk`,
`mstr_bed_l_shk`, `mstr_bth_bg_l_sh`, `mstr_bth_bg_r_sh`

**PIR motion sensors**
`ff_hallway_pir`, `gf_hallway_pir`, `guest_bed_pir`, `kitchen_pir`, `living_rm_pir`,
`michael_stdy_pir`, `playroom_pir`, `utility_pir`

**Other**
`garage_mir` (garage mirror/PIR-type sensor)

All are `binary_sensor.texecom_alarm_<slug>`. Only a subset of these (mostly doors +
some windows) are referenced directly by name in automations/scripts — the rest exist
for dashboard visibility/monitoring only, but should still be provided by the
replacement so the dashboard keeps working.

## Aggregate / derived sensors built on top of the zone entities

- `binary_sensor.all_doors` (`configuration/templates/doors.yaml`) — any texecom door
  contact "on", or `cover.garage_door` open.
- `binary_sensor.ground_floor_windows`, `ground_floor_windows_excluding_velux`,
  `all_windows`, `windows_with_sensors` (`configuration/templates/windows.yaml`) —
  layered OR-combinations of the window contacts plus VELUX cover states.
- `binary_sensor.all_motion_sensors` — a UI-managed helper (not in YAML, lives in
  `.storage`) aggregating the PIR sensors; used to cancel the auto-arm countdown if
  motion is detected.

These aggregates, not the raw zone entities, are what actually gate arming in the
template alarm panel — so the replacement mainly needs to keep the raw zone entity
names/states stable; the aggregation logic itself doesn't need to move.

## Behaviors / automations relying on the alarm entities

1. **Auto-arm when house empties** (`configuration/automations/house_alarm.yaml`) —
   when `binary_sensor.presence_in_the_house` goes off and auto-arm is enabled, starts
   a 60s countdown with a Sonos TTS warning, then arms away, turns off all lights, and
   notifies on success. Cancelled (and auto-arm disabled) if motion is detected during
   the countdown, or door/garage opens.
2. **Auto-disarm when someone returns to an armed/pending house**
   (`house_alarm.yaml`, `configuration/automations/garage.yaml`, `automations.yaml`
   UI automation) — triggered by the front door opening, the garage door opening, or
   (UI-managed) garage door "opening" device trigger, gated on presence and an
   `input_boolean.automatically_disarm_the_house_alarm` toggle. Includes a spoken "The
   alarm is being disarmed..." announcement.
3. **Guest-mode interaction** — auto-arm is disabled while
   `input_boolean.guests_toggle` is on, and re-enabled when guests leave or presence
   returns (in the absence of guests).
4. **"I'm leaving" / "Cancel leaving" scripts**
   (`configuration/scripts/security.yaml`) — the most complex consumer. Checks a fixed
   list of ~20 named door/window `binary_sensor.texecom_alarm_*` entities plus the
   garage door and VELUX covers, announces via TTS what's still open, auto-closes
   VELUX windows, plays a repeating warning tone until either the doors/windows are
   closed or a timeout fires, then **waits specifically for
   `binary_sensor.texecom_alarm_front_door` to transition on→off** before arming away.
   Exposed to HomeKit as its own accessory bridge (see below).
5. **Garage integration**
   (`configuration/automations/garage.yaml`, `configuration/scripts/garage.yaml`,
   `automations.yaml` UI automation) — disarms the alarm before opening the garage
   door (Porsche Flic button single-click, or the `open_garage_door` script), and
   re-arms to away after the garage closes (Flic button long-press, or the
   `close_garage_arm_alarm` script).
6. **Blinds** (`configuration/automations/blinds.yaml`) — kitchen sliding-door contact
   sensors (`texecom_alarm_kitchen_l_slide`/`_r_slide`) gate an unrelated auto-close-blinds
   automation; not alarm-state-dependent, just reuses the door contact sensors.
7. **Windows** (`configuration/automations/windows.yaml`) — closes all VELUX windows
   automatically whenever `alarm_control_panel.house_alarm_panel` transitions to
   `armed_home`, `armed_away`, or `armed_night` (already anticipates Home mode
   working, even though it doesn't today).
8. **House number light flash** — flashes the exterior house-number light whenever the
   alarm reaches `armed_away` (`house_alarm.yaml`).
9. **HomeKit exposure** (`configuration/homekit/bridges.yaml`) — `alarm_control_panel.house_alarm_panel`
   is exposed as its own HomeKit accessory bridge (port 21064); `script.im_leaving` /
   `script.cancel_leaving` are exposed via a separate "Security scripts" bridge (port
   21067).
10. **Notifications** — arm-failure explanations go through the shared
    `script.notify_actor` (resolves the initiating user's phone, falls back to
    `notify.notify_michael_talia`, downgrades "critical" pushes to normal after
    sunset); most other alarm-related notices use `notify.notify_michael` /
    `notify.notify_michael_talia` directly.

## Arm-mode mapping currently configured in the `the prior MQTT bridge` add-on

| Texecom mode | Home Assistant state | Wired into `house_alarm_panel`? |
|---|---|---|
| `full_arm`   | `armed_away` | Yes |
| `part_arm_1` | `armed_night` | Yes |
| `part_arm_2` | `armed_home` | **No** — not implemented in the template, and crashes the add-on when attempted directly |

## Implications / requirements for the replacement app

- Must produce (via MQTT discovery or otherwise) an alarm_control_panel entity that
  can play the role of today's `alarm_control_panel.texecom_alarm_arm_status`,
  supporting at least `disarmed` / `armed_away` / `armed_night` / **`armed_home`
  (working this time)** / `triggered` / `pending` / `arming` states — or a clear
  migration plan for renaming/adjusting `configuration/templates/house_alarm.yaml`.
- Must produce all ~35 zone `binary_sensor.texecom_alarm_*` entities (or equivalents)
  covering doors, windows, shock sensors, and PIRs — both the ones directly
  referenced by name in automations/scripts (see inventory above) and the rest, which
  feed dashboards.
- Should support arming/disarming reliably without crashing, including a working Home
  mode, since automations already assume it works (`windows.yaml`'s VELUX auto-close)
  and the household actively wants it.
- No dependency on raw MQTT topic structure exists elsewhere in the config, so the
  wire/topic schema is flexible as long as it results in compatible HA entities (or
  the template/automation layer is updated to match new entity names as part of the
  migration).
- The template alarm panel's guard-condition and notification logic
  (`configuration/templates/house_alarm.yaml`, `script.notify_actor`) does not need to
  be reimplemented in the new app — it operates purely on the HA-side entities and
  will keep working as long as entity names/states are preserved or remapped.

## Related docs

- `docs/brief.md` (this repo) — problem statement, current add-on/network setup, and
  the packet-capture reverse-engineering plan.
