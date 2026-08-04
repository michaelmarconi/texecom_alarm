---
command: supervisor_run
cwd: .
stop: Ctrl+C supervisor_run, then docker rm -f hassio_supervisor homeassistant hassio_cli hassio_dns hassio_audio hassio_multicast hassio_observer
url: http://localhost:8123/
---

## Up

From the repo root in the apps devcontainer:

```bash
supervisor_run
```

Same as the VS Code / Cursor task **Start Home Assistant**.

Wait until [http://localhost:8123/](http://localhost:8123/) responds (first boot downloads Supervisor plugins + Home Assistant Core and can take several minutes). This environment serves HA on **8123** (not the older docs example of 7123).

Then in the HA UI: complete onboarding if needed → **Settings → Add-ons → Local add-ons** → install / start **Texecom Alarm**. The Add-on still needs panel TCP + MQTT configuration before the bridge does real work.

## Down

1. Stop `supervisor_run` with **Ctrl+C** in its terminal (or kill that process).
2. Remove the Supervisor-managed containers so nothing is left listening:

```bash
docker rm -f hassio_supervisor homeassistant hassio_cli hassio_dns hassio_audio hassio_multicast hassio_observer 2>/dev/null
```

Confirm down: `http://localhost:8123/` should not respond.
