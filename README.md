# Home Assistant App: Texecom Alarm

_Bootstrap skeleton for a from-scratch Texecom Premier Elite <-> MQTT bridge, intended
as a replacement for [`the prior MQTT bridge`](a prior MQTT bridge)._

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

This is currently just the minimum viable app skeleton, bootstrapped from the
official [`home-assistant/apps-example`](https://github.com/home-assistant/apps-example)
template (see `developers.home-assistant.io/docs/apps/`). It doesn't talk to the
alarm panel yet — see `/config/docs/texecom_replacement_addon_brief.md` in the main
Home Assistant config repo for the background and plan.

## Local development

This repo is set up for the official Home Assistant apps devcontainer:

1. Open this folder in VS Code / Cursor.
2. Reopen in container when prompted (or Command Palette -> "Rebuild and Reopen in
   Container").
3. Run the "Start Home Assistant" task (Terminal -> Run Task) to boot a local
   Supervisor + Home Assistant with this app mounted as a Local App.
4. Access the instance at `http://localhost:7123/` and install/start the app from
   Settings -> Add-ons -> Local Add-ons.

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
