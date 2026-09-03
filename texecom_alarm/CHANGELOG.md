# Changelog

All notable changes to this Add-on are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.7] - 2026-09-03

### Fixed

- A second identical Arm after that mode already succeeded (or while the card
  shows that armed mode, or generic `arming` for this same gesture) is ignored,
  so a queued duplicate does not talk to the panel during the exit event burst.
  A different arm mode still goes through, including during exit. Once the
  house is unset (including from the keypad), a later same-mode Arm is a new
  tap and is sent.
- Unreadable follow-up bytes after a successful Arm are treated as a session
  resync, not a failed arm, including while the card still shows Off; **Alarm
  Panel Connection** stays on if the first re-login works. A hang-up or
  `+++` is still a lost session, not that resync, even if the card already
  shows `arming` or a prior arm already succeeded.
- A reconnect flags snapshot that still looks unset does not flash Off over an
  alarm card that already shows exit or entry (`arming` / `pending`), and does
  not forget an in-flight arm while the card is still Off.

## [0.3.6] - 2026-09-02

### Fixed

- If Arm or Disarm gets no reply while the panel is still sending ordinary
  updates, the add-on retries that tap as a fresh request and **Alarm Panel
  Connection** stays on. Connection goes off at once if the panel refuses,
  if the wait is silent, or if those retries get no reply.

## [0.3.5] - 2026-09-01

### Fixed

- After a successful arm, the add-on does not ask the panel for flags while it
  is busy sending events. Live updates carry exit and armed; a follow-up read
  there can tear the session. Disarm still reads flags when the card has not
  yet gone unset.

## [0.3.4] - 2026-09-01

### Fixed

- A second Disarm while the house is already unset is ignored, so a queued
  duplicate does not talk to the panel while it is busy sending events.

## [0.3.3] - 2026-09-01

### Fixed

- A second Disarm while the house is already unset is ignored, so a queued
  duplicate does not talk to the panel while it is busy sending events.

## [0.3.2] - 2026-09-01

### Added

- On start, the add-on logs its version at the default log level so a Supervisor
  log dump identifies which release is running.

### Fixed

- After a successful disarm (or arm), a flags follow-up that times out or is
  rejected no longer turns **Alarm Panel Connection** off. The tap already
  succeeded; the panel is busy, not gone. Live events that arrived during the
  ACK are used so the extra flags read is skipped while the panel is busy.

## [0.3.1] - 2026-09-01

### Changed

- After a successful arm or disarm, the add-on no longer asks the panel again
  for alarm flags when live events already updated the card, so the session
  stays quieter while the panel is busy.

### Fixed

- A garbled follow-up read after a successful arm or disarm is treated as a
  session collision (reconnect; **Alarm Panel Connection** stays on if the
  first re-login works), not as a failed tap that turns Connection off.
- When a panel message cannot be read, the log now includes why and the
  leading bytes, so a torn message can be told from a hang-up.

## [0.3.0] - 2026-08-29

### Added

- **Check-in interval** (default 15 seconds) and **Check-in patience**
  (default 45 seconds) in Configuration, so you can see how often the add-on
  confirms the panel is still answering and how long a refused check-in is
  tolerated before it reconnects.

### Changed

- The add-on now checks in with the panel on a fixed schedule, even when the
  panel is busy sending zone activity. A single refused check-in no longer
  turns **Alarm Panel Connection** off or drops the session — that only
  happens after check-ins have failed continuously for the patience period.
- **Reconnection delay** must be at least 2 seconds. The panel needs a
  moment to free its only connection slot; an immediate retry is refused.

### Removed

- **Force reconnect after** (the 90-second setting). It did not change
  behaviour at any value a household would actually use, so it has been
  dropped from Configuration. A leftover value from an older install is
  ignored.

### Fixed

- If the panel dropped the connection at the exact moment the add-on was
  sending a command, Home Assistant could keep showing green entities with
  frozen values. The add-on now reconnects, or exits so Supervisor can
  restart it.

## [0.2.2] - 2026-08-27

### Fixed

- Fixed a regression from 0.2.1 that could disconnect and reconnect the panel
  unnecessarily during busy periods (for example a burst of motion activity).
  A brief, otherwise-harmless hiccup in the panel's routine health-check reply
  is now retried before being treated as a problem; a genuinely unresponsive
  panel is still caught and reconnected just as quickly as before.

## [0.2.1] - 2026-08-27

### Fixed

- **Alarm Panel Connection** could get stuck showing connected even though the
  panel had stopped responding properly to routine health checks. The app now
  detects this and reconnects, instead of only reacting to a fully silent
  connection.

## [0.2.0] - 2026-08-26

### Changed

- Reconnect settings simplified: the four separate reconnect-attempts/interval
  settings (for ordinary vs. trigger disconnects) are replaced by a single
  **Reconnection delay** (default 5 seconds), used for every disconnect.
- **Alarm Panel Connection** health no longer depends on the background
  recheck poll — only missed keepalives, a dropped connection, or a
  rejected/timed-out arm/disarm command can turn it off.
- The background recheck poll interval is now configurable (**Recheck
  interval**, default 5 minutes) — was fixed at 30 seconds, which could cause
  audible panel pips.
- Clearer config labels: **Trust fail window seconds** → **Force reconnect
  after**; **Reconciliation poll interval seconds** → **Recheck interval**.

### Removed

- The app no longer skips unexpected/garbage bytes on the panel connection.
  Any unexpected data now ends the session and reconnects — this relies on
  the panel's dedicated local-control module (already a documented install
  requirement), not on the app tolerating a noisy shared line.

## [0.1.2] - 2026-08-24

### Added

- Ready-to-arm switches (Away, Home, Night) that start on. When a switch is
  off, that arm is not sent to the panel — including from Home Assistant —
  and the alarm entity stays as it was. On refuse the app briefly publishes
  Arming, then the current alarm state, so the Home Assistant alarm card can
  drop an optimistic Away, Home, or Night tap. Disarm is never blocked;
  turning a switch off while already armed does not disarm.
- A **Blocked arm** MQTT event that names the refused mode (`away`, `home`,
  or `night`) so automations can notify. The payload does not include a
  household reason.

## [0.1.1] - 2026-08-22

### Changed

- Improved logging: Supervisor add-on logs now include panel metadata in the
  message text (zone names and Secure/Active status, AREA state labels, named
  LOG events such as Alarm Active, panel identification on start, and command
  labels on TRACE tx/rx) so DEBUG/INFO/TRACE are readable without a separate
  sniffer.

## [0.1.0] - 2026-08-21

### Added

- Home Assistant App that connects to a Texecom Premier Elite panel over
  ComIP/Texecom Connect and publishes MQTT discovery entities.
- Alarm control panel with Away (full arm), Home / Night (Part-Arm slots via
  install-time configuration), and Disarm.
- Zone binary sensors enumerated from the panel (unused slots skipped).
- Alarm Panel Connection sensor for panel-link health; zone and alarm entities
  stay available with last-known state when the link drops.
- Startup zone-state and area-flags snapshots after login; silent-death
  detection and automatic session recovery without a manual App restart.
- Last-trigger snapshot attributes for recent activity before an alarm.

### Notes

- Point **Panel host** at a dedicated local network module, not the installer
  signalling module used for the Texecom app and monitoring station.
- Only one Connect login per module — stop other clients on that address first.

## [0.0.1] - 2026-08-04

### Added

- Repository scaffold and empty App shell (historical; not a product release).
