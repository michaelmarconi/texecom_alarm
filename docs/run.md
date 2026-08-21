---
command: ./scripts/ha-cold-start.sh
cwd: .
stop: Ctrl+C the supervisor_run terminal (or kill the pid in /tmp/ha-cold-start.supervisor_run.pid), then docker rm -f hassio_supervisor homeassistant hassio_cli hassio_dns hassio_audio hassio_multicast hassio_observer
url: http://localhost:7123/
---

## How ports square (HA docs ↔ Cursor)

One Core process listens on **8123 inside the remote**. Two laptop doors open onto it:

| Path | Laptop URL | Mechanism | Role |
|------|------------|-----------|------|
| **Official (HA docs)** | [http://localhost:7123/](http://localhost:7123/) | Docker `appPort: ["7123:8123"]` — stock template | Prefer this |
| **Cursor Ports** | [http://localhost:8123/](http://localhost:8123/) | IDE `forwardPorts: [8123]` | Same Core when 7123 isn’t published |

They are not competing schemes. **7123** remaps via Docker; **8123** is a same-number IDE tunnel. Both hit the same UI.

**Critical:** never let Cursor **Auto Forward 7123**. That tunnels laptop `:7123` → remote `:7123` (nothing listens) and steals the official URL from Docker’s `7123→8123` publish. `.devcontainer.json` sets `onAutoForward: "ignore"` for **7123** and **80**. If a ghost **7123** row appears anyway, stop-forward it.

**Do not forward or open port 80.** Supervisor beta defaults Core to `:80` and turns `:8123` into a redirect to bare `http://localhost/`, which loops under Cursor. `ha-cold-start.sh` pins `http.server_port` to **8123** so stock `7123:8123` stays valid.

After rebuild + cold-start, Ports should show **8123** (Home Assistant) and **4357** (Observer). Open **7123** in a normal browser (Docker publish) or **8123** via the Ports globe.

Sanity check inside the remote: `curl -sI http://127.0.0.1:8123/` → relative `location: /…` or 200 — never `Location: http://localhost/`.

## Cold start (deterministic)

From the repo root in the apps devcontainer:

```bash
./scripts/ha-cold-start.sh
```

Same as VS Code / Cursor task **Start Home Assistant** (wired to this script).

What it does:

1. Bring up Supervisor/Core if needed; pin `http.server_port` to **8123**.
2. Ensure **Mosquitto** (`core_mosquitto`) is installed, has the local-sim MQTT login, and is started.
3. Ensure **Texecom Alarm** (`local_texecom_alarm`) is installed; if `panel_host` is empty, apply sim defaults from `TEXECOM_*` (or the script’s local placeholders): Part-Arm Night/Home/Unused, MQTT → `core-mosquitto`; start it.
4. Print UI URLs. Prefer **`http://localhost:7123/`**; if that fails, use **`http://localhost:8123/`**.

Idempotent: re-run is safe (no DB/registry wipe). Override panel/MQTT via `TEXECOM_PANEL_HOST`, `TEXECOM_UDL_PASSWORD`, `TEXECOM_MQTT_*`, `TEXECOM_PART_ARM_{1,2,3}`.

Does **not** complete HA onboarding for you. Panel must be free (ADR-001 single ComIP connection) or Texecom may enter `error`.


## Entity reset (no duplicate / suffixed MQTT IDs)

When discovery left orphans or `_2` entity IDs, wipe registries + MQTT retain **without** full re-onboarding:

```bash
./scripts/ha-entity-reset.sh --yes
```

(`--yes` is required so a mistype cannot wipe the sim.)

What it does:

1. Stop Texecom Alarm.
2. Clear retained `homeassistant/#` + `texecom/#` (if Mosquitto is up); delete `mosquitto.db`.
3. Stop Core; delete `home-assistant_v2.db*` + entity/device/area registries + restore_state.
4. Start Mosquitto (if installed) + Core; **leave Texecom stopped**.
5. Keep auth, onboarding, `config_entries`, Mosquitto `options.json`.

Then hard-refresh `http://localhost:8123/`, start Texecom when you want a clean rediscovery.

**Expected leftovers:** Supervisor add-on metrics (`binary_sensor.texecom_alarm_running`, etc.) — not MQTT zone entities. Prefixed zones like `binary_sensor.texecom_alarm_front_door_1` after a **fresh** start are normal panel inventory (`_1` = zone number), not wipe dirt.

## Disk space (Supervisor ≥2 GiB gate)

Supervisor refuses install / rebuild / update under **2 GiB** free. Cold-start enforces the same when it must start/pull.

```bash
ha host info | grep disk_
df -h /mnt/supervisor
```

This apps devcontainer shares a **Docker Desktop VM disk**. Reclaim stale host volumes when low — see historical reclaim recipe in git history / ask — do **not** delete Supervisor/anonymous volumes used by this stack.

## Refresh local add-on (without a version bump)

**Do not bump `config.yaml` `version` to force a UI refresh.** Policy: [addon-versioning.md](addon-versioning.md).

```bash
ha store reload
ha apps info local_texecom_alarm | grep -E '^(version|version_latest):'
# same version → rebuild; mismatched installed vs disk → update
ha apps rebuild local_texecom_alarm
# or: ha apps update local_texecom_alarm
```

After rebuild, Configuration Part-Arm radios should show **Home / Night / Unused**
only (Away excluded — ADR-008). If an older options file still has Away on a
slot, the app coerces that slot to Unused at load and logs a warning; Away
continues to arm via full-arm mode byte `0`.

## Down

1. Stop `supervisor_run` (Ctrl+C in its terminal, or kill the pid recorded by cold-start).
2. Remove Supervisor-managed containers:

```bash
docker rm -f hassio_supervisor homeassistant hassio_cli hassio_dns hassio_audio hassio_multicast hassio_observer 2>/dev/null
```

Confirm: `http://localhost:7123/` should not respond.
