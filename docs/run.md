---
command: supervisor_run
cwd: .
stop: Ctrl+C supervisor_run, then docker rm -f hassio_supervisor homeassistant hassio_cli hassio_dns hassio_audio hassio_multicast hassio_observer
url: http://localhost:8123/
pre:
  - |
    python3 -c "import shutil,sys; free=shutil.disk_usage('/mnt/supervisor').free/(1024**3); print(f'Disk free: {free:.1f} GiB');
    sys.exit(0 if free>=2.0 else 1)" || { echo "Supervisor needs ≥2 GiB free for install/rebuild/update. See docs/run.md § Disk space."; exit 1; }
---

## Up

From the repo root in the apps devcontainer:

```bash
supervisor_run
```

Same as the VS Code / Cursor task **Start Home Assistant**.

Wait until [http://localhost:8123/](http://localhost:8123/) responds (first boot downloads Supervisor plugins + Home Assistant Core and can take several minutes). This environment serves HA on **8123** (not the older docs example of 7123).

Then in the HA UI: complete onboarding if needed → **Settings → Add-ons → Local add-ons** → install / start **Texecom Alarm**. The add-on still needs panel TCP + MQTT configuration before the bridge does real work.

### Ready check (CLI)

```bash
ha host info | grep disk_free    # must be ≥ 2 (GiB) before rebuild/update
ha apps info local_texecom_alarm | grep -E '^(version|version_latest|state):'
```

Expect `state: started` and `version` == `version_latest` matching `config.yaml` (currently `0.0.1`). If they differ, run the refresh steps below — do **not** bump `version`.

## Disk space (Supervisor ≥2 GiB gate)

Supervisor refuses install / rebuild / update when free space on the data disk is under **2 GiB**:

`AppManager.rebuild blocked … not enough free space (XGB) left on the device`

Check:

```bash
ha host info | grep disk_
df -h /mnt/supervisor
```

This apps devcontainer shares a **Docker Desktop VM disk** with other projects. `df` reports that whole VM — not just this repo. When free space is low, reclaim **stale host Docker volumes** (caches from other worktrees), not HA Core itself.

Typical reclaim (from inside this environment; only removes named cache volumes from other projects):

```bash
sudo unshare -m bash -c '
  mount --make-rprivate /
  mkdir -p /tmp/hostfs && mount /dev/vda1 /tmp/hostfs
  VOLS=/tmp/hostfs/docker/volumes
  # List large named volumes first: du -sh "$VOLS"/* | sort -hr | head
  rm -rf "$VOLS"/mailbot-*_pnpm-store \
         "$VOLS"/search_pnpm-store \
         "$VOLS"/mailbot-devcontainer_*node_modules
  fstrim /tmp/hostfs 2>/dev/null || true
  df -h /tmp/hostfs
'
```

Do **not** delete anonymous volumes used by this stack (Supervisor / inner Docker / containerd data). Prefer Docker Desktop → **Troubleshoot → Clean / purge data** or raising the disk image size when the VM is chronically full.

Re-check: `ha host info | grep disk_free` should show **≥ 2**.

## Refresh local add-on (without a version bump)

Supervisor caches add-on metadata (schema, translations, `version`) against the last successful install/rebuild. **Do not bump `config.yaml` `version` to force a UI refresh** — that invents a fake release. Policy: [addon-versioning.md](addon-versioning.md).

After changing `config.yaml` schema/options, `translations/`, or image contents (`Dockerfile`, `texecom-alarm-app/`, `rootfs/`):

```bash
# 1. Re-read config + translations from disk into the store cache
ha store reload

# 2. Ensure ≥2 GiB free (see above)

# 3a. Same version string on disk as installed → Rebuild
ha apps info local_texecom_alarm | grep -E '^(version|version_latest):'
ha apps rebuild local_texecom_alarm

# 3b. If Rebuild says versions differ, use Update instead
#     (e.g. an old mistaken bump left installed 0.0.3 while git is 0.0.1)
ha apps update local_texecom_alarm
```

Then:

1. Hard-refresh the browser (Ctrl+F5) on **Settings → Add-ons → Texecom Alarm → Configuration**.
2. Confirm `version` == `version_latest` and the Configuration labels match `translations/en.yaml` (e.g. **Panel UDL password**, **Part-Arm slot 1/2/3**).

**Restart** alone is enough only when runtime code in an already-rebuilt image changed in a way you hot-patched — for schema/translations/image layers, use Rebuild/Update.

If Rebuild/Update still does not pick up a change after a hard refresh, stop and ask — do not bump `version` as a workaround.

## Down

1. Stop `supervisor_run` with **Ctrl+C** in its terminal (or kill that process).
2. Remove the Supervisor-managed containers so nothing is left listening:

```bash
docker rm -f hassio_supervisor homeassistant hassio_cli hassio_dns hassio_audio hassio_multicast hassio_observer 2>/dev/null
```

Confirm down: `http://localhost:8123/` should not respond.
