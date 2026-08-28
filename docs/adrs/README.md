# ADR index

ADRs are immutable once accepted — a decision that changes gets a new ADR that
supersedes the old one, never an edit to the old one's own text. This index is
the fast way to find the *current* word on a topic without walking a
supersession chain by hand.

## Live (current word)

| ADR | Date | Decision |
|-----|------|----------|
| [001](adr-001-use-dynamic-panel-enumeration-for-zone-discovery.md) | 2026-08-01 | Use dynamic panel enumeration for zone discovery |
| [003](adr-003-use-mqtt-discovery-not-native-integration-for-entity-surfacing.md) | 2026-08-03 | Use MQTT discovery (not a native integration) for entity surfacing |
| [004](adr-004-use-app-liveness-unavailability-and-trigger-snapshots-for-panel-link-outages.md) | 2026-08-03 | Use app-liveness unavailability and trigger snapshots for panel-link outages |
| [006](adr-006-use-panel-zone-state-snapshot-for-startup-re-sync.md) | 2026-08-04 | Use panel zone-state snapshot for startup re-sync |
| [008](adr-008-use-confirmed-shared-arm-disarm-with-away-full-arm-and-home-night-part-arm-mapping.md) | 2026-08-08 | Use confirmed shared arm/disarm commands with Away as full arm and configurable Home/Night Part-Arm mapping (supersedes [005](adr-005-use-confirmed-shared-arm-disarm-commands-with-configurable-part-arm-mapping.md)) |
| [009](adr-009-use-panel-area-flags-snapshot-for-alarm-startup-re-sync.md) | 2026-08-08 | Use panel area-flags snapshot for alarm startup re-sync (supersedes [007](adr-007-use-panel-area-flags-snapshot-for-alarm-startup-re-sync.md)) |
| [011](adr-011-use-automatic-session-recovery-for-mid-run-panel-path-failures.md) | 2026-08-09 | Use automatic session recovery for mid-run panel path failures |
| [012](adr-012-use-python-3-for-the-texecom-alarm-app.md) | 2026-08-10 | Use Python 3 for the Texecom Alarm App |
| [013](adr-013-use-dedicated-local-network-module-for-home-assistant-panel-access.md) | 2026-08-21 | Use the dedicated local network module for Home Assistant panel access |
| [015](adr-015-use-ready-to-arm-switches-and-mqtt-blocked-arm-event-for-unready-arm-refusal.md) | 2026-08-23 | Use ready-to-arm switches and an MQTT blocked-arm event for refusing unready arm commands |
| [016](adr-016-use-keepalive-failure-and-command-reject-events-for-panel-connection-detection.md) | 2026-08-25 | Use keepalive failure and command-reject events for panel-connection detection (supersedes [010](adr-010-use-command-reject-events-and-periodic-house-state-polling-for-silent-panel-path-death-detection.md)) |
| [017](adr-017-use-a-configurable-5-minute-interval-for-the-panel-reconciliation-poll.md) | 2026-08-25 | Use a configurable 5-minute interval for the panel reconciliation poll |
| [018](adr-018-use-interval-only-reconnect-budgets-for-panel-disconnects.md) | 2026-08-26 | Use interval-only reconnect budgets for panel disconnects |
| [019](adr-019-use-a-single-reconnect-interval-and-no-line-noise-defense-for-panel-disconnects.md) | 2026-08-26 | Use a single reconnect interval and no line-noise defense for panel disconnects (supersedes [014](adr-014-use-host-scoped-trigger-disconnect-assumptions-for-panel-reconnect-design.md), which superseded [002](adr-002-use-frame-resync-and-asymmetric-reconnect-for-panel-protocol-collisions.md)) |
| [020](adr-020-use-scheduled-check-ins-and-a-patience-window-for-panel-session-recovery.md) | 2026-08-28 | Use scheduled check-ins and a patience window for panel session recovery |

## Superseded (historical record only — do not cite as current behaviour)

| ADR | Superseded by | Decision at the time |
|-----|----------------|-----------------------|
| [002](adr-002-use-frame-resync-and-asymmetric-reconnect-for-panel-protocol-collisions.md) | 014 → 019 | Frame resync and asymmetric reconnect for panel protocol collisions |
| [005](adr-005-use-confirmed-shared-arm-disarm-commands-with-configurable-part-arm-mapping.md) | 008 | Confirmed shared arm/disarm commands with configurable Part-Arm mapping |
| [007](adr-007-use-panel-area-flags-snapshot-for-alarm-startup-re-sync.md) | 009 | Panel area-flags snapshot for alarm startup re-sync |
| [010](adr-010-use-command-reject-events-and-periodic-house-state-polling-for-silent-panel-path-death-detection.md) | 016 | Command-reject events and periodic house-state polling for silent panel-path death detection |
| [014](adr-014-use-host-scoped-trigger-disconnect-assumptions-for-panel-reconnect-design.md) | 019 | Host-scoped trigger-disconnect assumptions for panel reconnect design |

See `AGENTS.md` for the synthesised, currently-binding constraints and stop
conditions across all live ADRs — this index is for navigating the ADRs
themselves, not a substitute for reading `AGENTS.md`.
