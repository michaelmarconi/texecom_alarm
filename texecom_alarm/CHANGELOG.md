# Changelog

All notable changes to this Add-on are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-08-21

### Changed

- Require SemVer in the PR; stop post-merge robot bumps; main is PR-only

## [0.1.2] - 2026-08-21

### Changed

- build(deps-dev): bump ruff (#5)

## [0.1.1] - 2026-08-21

### Changed

- fix: bump SemVer via PR under branch protection

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
