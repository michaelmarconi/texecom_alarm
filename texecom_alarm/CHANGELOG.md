# Changelog

All notable changes to this Add-on are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-08-27

### Fixed

- A rejected keepalive reply (panel answers but refuses the health check) now
  degrades **Alarm Panel Connection** and triggers reconnect + re-sync, the
  same as an unanswered one. Previously only a silent/unanswered keepalive
  was treated as a dead session, so a panel that kept rejecting check-ins
  while the TCP connection stayed open could leave Connection stuck showing
  online with live monitoring silently stopped.

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
