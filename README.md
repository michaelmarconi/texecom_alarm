# Texecom Alarm — HA Integration Replacement

A ground-up, self-built Home Assistant Add-on for a Texecom Premier Elite alarm
panel (via ComIP/Texecom Connect), replacing `the prior MQTT bridge` with something that
doesn't crash and finally supports Home arm mode — published for other Premier
Elite households to install and configure.

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

## Project structure

- `texecom-alarm-app/` — Texecom Alarm App: Python 3 process that speaks Texecom
  Connect to the panel and publishes MQTT discovery/state to Home Assistant
  (ADR-003). Packaged for HA OS via the repo-root `Dockerfile` / `rootfs/` /
  `config.yaml` Add-on shell.
- **Technology:** Python 3 (HA App / Docker + s6-overlay).
- **Delivery:** run as a Home Assistant Add-on (Supervisor Local Apps or Add-on
  Store); local CI via `pytest` / `ruff` in `texecom-alarm-app/`.
- **Consumes:** panel ComIP TCP session; MQTT broker; Supervisor
  `options.json` (panel host/port, UDL password, MQTT settings, Part-Arm
  mode mapping).
- **Exposes:** MQTT discovery + state/command topics for
  `alarm_control_panel`, per-zone `binary_sensor`s, connectivity sensor, and
  last-trigger snapshot (ADR-004).

## Documentation

- [Brief](docs/brief.md)
- [Architecture](docs/architecture.md)
- [Protocol reference](docs/protocol-reference.md)
- [Definition of Done](docs/definition-of-done.md)
- Add-on docs tab: [DOCS.md](DOCS.md) (Home Assistant Supervisor convention)

## Getting started

### Local development (HA apps devcontainer)

1. Open this folder in VS Code / Cursor and reopen in the Home Assistant apps
   devcontainer.
2. Run the "Start Home Assistant" task to boot Supervisor + Home Assistant with
   this app mounted as a Local App.
3. Open `http://localhost:7123/` and install/start the app from
   Settings → Add-ons → Local Add-ons.

### App package (unit / E2E tests)

```bash
cd texecom-alarm-app
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest --cov=texecom_alarm --cov-fail-under=90
ruff check . && ruff format --check .
```

Panel traffic in tests must use a mock — never the live household panel in CI.

## Configuration

Install-time options (Supervisor `config.yaml` / `options.json`) will include
panel host/port, UDL password, MQTT broker settings, and the Part-Arm
slot-to-HA-mode mapping (ADR-005). See [DOCS.md](DOCS.md) as options land.

## License

TODO: Add licence (required before public Add-on Store distribution).

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
