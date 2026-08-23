#!/usr/bin/env bash
# Rehearse the household Supervisor Update path in simulated HA:
# stop local_* → ensure #app store repo → install FROM → update to TO (GHCR) →
# assert version + options → stop store slug → optionally restart local_*.
#
# Not live smoke (/run --target). Not a substitute for local rebuild.
# Do not run the store copy alongside a started local_texecom_alarm.
#
# Supervisor ignores /store/.../install/{version} (always installs catalogue
# latest). To install FROM we temporarily pin the local #app clone's
# config.yaml version via a local bare origin, reload, install, then restore
# the GitHub origin and Update to TO.
#
# Usage:
#   ./scripts/ha-store-upgrade-smoke.sh [--from X.Y.Z] [--no-restart-local]
#
# Preconditions: apps-devcontainer with Supervisor/Core already up (/run / cold-start).
# GHCR must publish both FROM and TO tags (image: ghcr.io/.../texecom-alarm:X.Y.Z).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STORE_REPO_URL="${TEXECOM_STORE_REPO_URL:-https://github.com/michaelmarconi/texecom_alarm#app}"
LOCAL_SLUG="local_texecom_alarm"
DISK_MIN_GIB=2
CONFIG_YAML="texecom_alarm/config.yaml"

FROM_VERSION=""
RESTART_LOCAL=true

ORIGIN_BACKUP=""
STORE_CLONE=""
BARE_REPO=""

log() { printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/ha-store-upgrade-smoke.sh [--from X.Y.Z] [--no-restart-local]

Rehearses Supervisor store Update (FROM → TO) for the #app catalogue slug.
Requires Supervisor/Core up, a published GHCR tag for FROM and TO, and a
previous SemVer ( --from or the prior git tag v*).

  --from X.Y.Z       Install this version first (default: previous v* tag)
  --no-restart-local Leave local_texecom_alarm stopped after the smoke
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      FROM_VERSION="$2"
      shift 2
      ;;
    --no-restart-local)
      RESTART_LOCAL=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log "ERROR: unknown argument: $1"
      usage
      exit 2
      ;;
  esac
done

disk_free_gib() {
  awk 'NR==2 { printf "%.1f", $4 / 1024 / 1024 }' < <(df -Pk /mnt/supervisor)
}

supervisor_up() {
  docker inspect hassio_supervisor --format '{{.State.Status}}' 2>/dev/null | grep -qx running
}

core_up() {
  docker inspect homeassistant --format '{{.State.Status}}' 2>/dev/null | grep -qx running
}

app_installed() {
  ha apps info "$1" --raw-json 2>/dev/null | jq -e '.data.version != null' >/dev/null 2>&1
}

app_state() {
  ha apps info "$1" --raw-json 2>/dev/null | jq -r '.data.state // "unknown"'
}

app_version() {
  ha apps info "$1" --raw-json 2>/dev/null | jq -r '.data.version // empty'
}

app_options_json() {
  ha apps info "$1" --raw-json 2>/dev/null | jq -c '.data.options // {}'
}

wait_app_state() {
  local slug="$1" want="$2" timeout="${3:-180}"
  local deadline=$((SECONDS + timeout)) st
  while (( SECONDS < deadline )); do
    st="$(app_state "$slug")"
    [[ "$st" == "$want" ]] && return 0
    sleep 2
  done
  log "WARNING: $slug state=$(app_state "$slug") (wanted $want)"
  return 1
}

wait_app_started_or_error() {
  local slug="$1" timeout="${2:-180}"
  local deadline=$((SECONDS + timeout)) st
  while (( SECONDS < deadline )); do
    st="$(app_state "$slug")"
    case "$st" in
      started|error) return 0 ;;
    esac
    sleep 2
  done
  log "ERROR: $slug did not reach started|error (state=$(app_state "$slug"))"
  return 1
}

wait_app_not_busy() {
  local slug="$1" timeout="${2:-300}"
  local deadline=$((SECONDS + timeout)) st
  while (( SECONDS < deadline )); do
    st="$(app_state "$slug")"
    case "$st" in
      started|stopped|error) return 0 ;;
    esac
    sleep 2
  done
  log "ERROR: $slug still busy (state=$(app_state "$slug"))"
  return 1
}

canonical_version() {
  sed -nE 's/^version:[[:space:]]*"?([0-9]+\.[0-9]+\.[0-9]+)"?.*/\1/p' "$CONFIG_YAML" | head -1
}

previous_semver_tag() {
  local to="$1" prev=""
  local -a tags=()
  mapfile -t tags < <(git tag -l 'v*' | sed 's/^v//' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | sort -V)
  for t in "${tags[@]}"; do
    if [[ "$t" == "$to" ]]; then
      printf '%s\n' "$prev"
      return 0
    fi
    prev="$t"
  done
  printf '%s\n' "$prev"
}

supervisor_set_options() {
  local slug="$1"
  local options_json="$2"
  docker exec -u root -e "OPTS_SLUG=$slug" -e "OPTS_JSON=$options_json" homeassistant \
    python3 -c '
import json, os, urllib.request
slug = os.environ["OPTS_SLUG"]
opts = json.loads(os.environ["OPTS_JSON"])
token = os.environ["SUPERVISOR_TOKEN"]
req = urllib.request.Request(
    f"http://supervisor/addons/{slug}/options",
    data=json.dumps({"options": opts}).encode(),
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=60) as resp:
    body = json.loads(resp.read().decode())
if body.get("result") != "ok":
    raise SystemExit(f"options failed: {body}")
print("ok")
'
}

options_equal() {
  local a="$1" b="$2"
  jq -n -e --argjson a "$a" --argjson b "$b" '$a == $b' >/dev/null
}

ensure_store_repo() {
  local sources
  sources="$(ha store --raw-json | jq -r '.data.repositories[]?.source // empty')"
  if printf '%s\n' "$sources" | grep -Fxq "$STORE_REPO_URL"; then
    log "Store repo already present: $STORE_REPO_URL"
    return 0
  fi
  if printf '%s\n' "$sources" | grep -Fq "github.com/michaelmarconi/texecom_alarm"; then
    log "WARNING: a texecom_alarm store URL is present but not exactly $STORE_REPO_URL:"
    printf '%s\n' "$sources" | grep -F "github.com/michaelmarconi/texecom_alarm" | sed 's/^/  | /' || true
    log "Prefer remove-and-re-add with #app before relying on this smoke."
  fi
  log "Adding store repo: $STORE_REPO_URL"
  ha store add "$STORE_REPO_URL" --no-progress
}

resolve_store_slug() {
  local slug
  slug="$(ha store --raw-json | jq -r '
    (.data.addons // .data.apps // [])
    | map(select(.slug | test("texecom_alarm$")))
    | map(select(.slug != "local_texecom_alarm"))
    | if length == 0 then empty
      elif length == 1 then .[0].slug
      else
        (map(select(.repository != "local")) | .[0].slug) // .[0].slug
      end
  ')"
  if [[ -z "$slug" || "$slug" == "null" ]]; then
    log "ERROR: no store slug for Texecom Alarm (non-local). Is $STORE_REPO_URL added and reloaded?"
    ha store --raw-json | jq -r '(.data.addons // .data.apps // [])[] | select(.slug|test("texecom")) | "\(.slug)\trepo=\(.repository)\tlatest=\(.version_latest)"' >&2 || true
    return 1
  fi
  if [[ "$slug" == "$LOCAL_SLUG" ]]; then
    log "ERROR: resolved local slug; refuse to use $LOCAL_SLUG for store Update rehearsal"
    return 1
  fi
  printf '%s\n' "$slug"
}

store_version_latest() {
  local slug="$1"
  ha store --raw-json | jq -r --arg s "$slug" '
    (.data.addons // .data.apps // [])
    | map(select(.slug == $s))
    | .[0].version_latest // empty
  '
}

store_repo_slug() {
  local slug="$1"
  printf '%s\n' "${slug%_texecom_alarm}"
}

store_clone_path() {
  local repo_slug="$1"
  printf '%s\n' "/mnt/supervisor/apps/git/${repo_slug}"
}

restore_store_origin() {
  if [[ -n "${STORE_CLONE:-}" && -n "${ORIGIN_BACKUP:-}" && -d "$STORE_CLONE/.git" ]]; then
    log "Restoring store clone origin → $ORIGIN_BACKUP"
    sudo git -C "$STORE_CLONE" remote set-url origin "$ORIGIN_BACKUP" 2>/dev/null || true
  fi
  if [[ -n "${BARE_REPO:-}" && -e "$BARE_REPO" ]]; then
    sudo rm -rf "$BARE_REPO" 2>/dev/null || true
    BARE_REPO=""
  fi
}

pin_catalogue_version() {
  local repo_slug="$1" version="$2"
  STORE_CLONE="$(store_clone_path "$repo_slug")"
  # Supervisor mounts host /mnt/supervisor as /data. Put the bare repo next to
  # the clone and set origin to the *container* path so fetch works.
  BARE_REPO="/mnt/supervisor/apps/git/_smoke_${repo_slug}.git"
  BARE_REPO_IN_SUPERVISOR="/data/apps/git/_smoke_${repo_slug}.git"
  local cfg="$STORE_CLONE/texecom_alarm/config.yaml"

  [[ -f "$cfg" ]] || { log "ERROR: missing $cfg — is the #app store clone present?"; return 1; }

  ORIGIN_BACKUP="$(sudo git -C "$STORE_CLONE" remote get-url origin)"
  log "Pinning catalogue on disk to $version (origin was $ORIGIN_BACKUP)"

  sudo sed -i -E "s/^version:[[:space:]]*\"?[0-9]+\.[0-9]+\.[0-9]+\"?/version: \"$version\"/" "$cfg"
  sudo git -C "$STORE_CLONE" config user.email "store-smoke@local"
  sudo git -C "$STORE_CLONE" config user.name "store-smoke"
  sudo git -C "$STORE_CLONE" add texecom_alarm/config.yaml
  if sudo git -C "$STORE_CLONE" diff --cached --quiet; then
    log "ERROR: config.yaml already at $version with no diff — cannot create pin commit"
    return 1
  fi
  sudo git -C "$STORE_CLONE" commit -m "smoke: pin catalogue version $version"

  sudo rm -rf "$BARE_REPO"
  sudo git clone --bare "$STORE_CLONE" "$BARE_REPO"
  local branch
  branch="$(sudo git -C "$STORE_CLONE" rev-parse --abbrev-ref HEAD)"
  sudo git -C "$BARE_REPO" branch -M "$branch" 2>/dev/null || true

  # Leave clone one commit behind so store reload's fetch+reset sees a change
  # and re-reads apps (reload skips _read_apps when pull reports unchanged).
  sudo git -C "$STORE_CLONE" reset --hard HEAD~1
  sudo git -C "$STORE_CLONE" remote set-url origin "$BARE_REPO_IN_SUPERVISOR"

  log "Reloading store to pick up pinned $version"
  ha store reload --no-progress
}

restore_catalogue_from_github() {
  restore_store_origin
  log "Reloading store from GitHub to restore catalogue"
  ha store reload --no-progress
}

install_latest_from_store() {
  local slug="$1" expect_version="$2"
  log "Installing $slug (catalogue latest should be $expect_version)"
  ha apps install "$slug" --no-progress
  wait_app_not_busy "$slug" 600 || return 1
  local ver
  ver="$(app_version "$slug")"
  if [[ "$ver" != "$expect_version" ]]; then
    log "ERROR: after install expected version=$expect_version got version=${ver:-none}"
    log "Catalogue pin may have failed; store version_latest=$(store_version_latest "$slug")"
    return 1
  fi
  log "Installed $slug@$ver"
}

# --- main ---

log "=== ha-store-upgrade-smoke ==="
trap restore_store_origin EXIT

if ! command -v ha >/dev/null 2>&1; then
  log "ERROR: ha CLI not found (are you in the HA apps devcontainer?)"
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  log "ERROR: jq not found"
  exit 1
fi
if ! supervisor_up || ! core_up; then
  log "ERROR: Supervisor/Core not running. Run ./scripts/ha-cold-start.sh (or /run) first."
  exit 1
fi

free="$(disk_free_gib)"
log "Disk free on /mnt/supervisor: ${free} GiB (need ≥ ${DISK_MIN_GIB})"
awk -v f="$free" -v m="$DISK_MIN_GIB" 'BEGIN { exit !(f + 0 >= m) }' || {
  log "ERROR: not enough free disk for Supervisor install/update. See docs/run.md § Disk space."
  exit 1
}

TO_VERSION="$(canonical_version)"
[[ -n "$TO_VERSION" ]] || { log "ERROR: no version in $CONFIG_YAML"; exit 1; }

if [[ -z "$FROM_VERSION" ]]; then
  FROM_VERSION="$(previous_semver_tag "$TO_VERSION")"
fi
if [[ -z "$FROM_VERSION" ]]; then
  log "ERROR: no FROM version. Pass --from X.Y.Z or create a prior git tag v* before $TO_VERSION."
  log "Install-only is not an Update rehearsal; Ship cannot tick Store Update rehearsal."
  exit 1
fi
if [[ "$FROM_VERSION" == "$TO_VERSION" ]]; then
  log "ERROR: FROM ($FROM_VERSION) equals TO ($TO_VERSION). Need a prior release to Update from."
  exit 1
fi
if ! [[ "$FROM_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && "$TO_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  log "ERROR: versions must be SemVer X.Y.Z (FROM=$FROM_VERSION TO=$TO_VERSION)"
  exit 1
fi
log "Rehearsal: FROM=$FROM_VERSION → TO=$TO_VERSION"
log "Note: Supervisor install always uses catalogue latest; we pin #app clone to FROM then restore TO for Update."

# 1. Stop local (do not uninstall).
if app_installed "$LOCAL_SLUG"; then
  st="$(app_state "$LOCAL_SLUG")"
  if [[ "$st" != "stopped" ]]; then
    log "Stopping $LOCAL_SLUG (was $st)"
    ha apps stop "$LOCAL_SLUG" --no-progress || true
    wait_app_state "$LOCAL_SLUG" stopped 120 || {
      log "ERROR: refuse to continue while $LOCAL_SLUG is not stopped (state=$(app_state "$LOCAL_SLUG"))"
      exit 1
    }
  else
    log "$LOCAL_SLUG already stopped"
  fi
else
  log "$LOCAL_SLUG not installed — ok"
fi

# 2. Ensure store repo + reload.
ensure_store_repo
log "Reloading store"
ha store reload --no-progress

# 3. Resolve store slug.
STORE_SLUG="$(resolve_store_slug)"
log "Store slug: $STORE_SLUG"
REPO_SLUG="$(store_repo_slug "$STORE_SLUG")"
log "Store git clone slug: $REPO_SLUG"

STORE_LATEST="$(store_version_latest "$STORE_SLUG")"
log "Store version_latest=$STORE_LATEST (config.yaml TO=$TO_VERSION)"
if [[ "$STORE_LATEST" != "$TO_VERSION" ]]; then
  log "ERROR: store version_latest ($STORE_LATEST) != config.yaml ($TO_VERSION)."
  log "Ensure #app is synced and GHCR/tag publish finished before this smoke."
  exit 1
fi

# 4–5. Force Update path: uninstall if present, pin catalogue to FROM, install.
SAVED_OPTIONS="{}"
if app_installed "$STORE_SLUG"; then
  SAVED_OPTIONS="$(app_options_json "$STORE_SLUG")"
  cur="$(app_version "$STORE_SLUG")"
  log "Store slug currently installed at $cur — uninstalling to force FROM→TO Update"
  st="$(app_state "$STORE_SLUG")"
  if [[ "$st" != "stopped" ]]; then
    ha apps stop "$STORE_SLUG" --no-progress || true
    wait_app_state "$STORE_SLUG" stopped 120 || true
  fi
  ha apps uninstall "$STORE_SLUG" --no-progress
  uninstall_deadline=$((SECONDS + 120))
  while (( SECONDS < uninstall_deadline )); do
    app_installed "$STORE_SLUG" || break
    sleep 2
  done
  if app_installed "$STORE_SLUG"; then
    log "ERROR: $STORE_SLUG still installed after uninstall"
    exit 1
  fi
fi

pin_catalogue_version "$REPO_SLUG" "$FROM_VERSION"
PINNED_LATEST="$(store_version_latest "$STORE_SLUG")"
if [[ "$PINNED_LATEST" != "$FROM_VERSION" ]]; then
  log "ERROR: after catalogue pin, version_latest=$PINNED_LATEST (want $FROM_VERSION)"
  restore_catalogue_from_github
  exit 1
fi
log "Catalogue pinned: version_latest=$PINNED_LATEST"

install_latest_from_store "$STORE_SLUG" "$FROM_VERSION"

# Merge a persistence marker into current options (Supervisor replaces the whole
# options object — partial payloads fail schema validation).
CURRENT_OPTS="$(app_options_json "$STORE_SLUG")"
MARKER_OPTS="$(jq -nc --argjson cur "$CURRENT_OPTS" --argjson saved "$SAVED_OPTIONS" '
  ($cur * $saved)
  | .mqtt_host = (if (.mqtt_host // "") == "" then "core-mosquitto" else .mqtt_host end)
  | .mqtt_username = "texecom-store-smoke"
')"
log "Seeding options on $STORE_SLUG for persistence check"
supervisor_set_options "$STORE_SLUG" "$MARKER_OPTS" >/dev/null

log "Starting $STORE_SLUG@$FROM_VERSION"
ha apps start "$STORE_SLUG" --no-progress || log "WARNING: start returned non-zero"
wait_app_started_or_error "$STORE_SLUG" 180 || exit 1
log "$STORE_SLUG state=$(app_state "$STORE_SLUG") after start (started|error ok for packaging)"

BEFORE_OPTS="$(app_options_json "$STORE_SLUG")"
log "Options snapshot before update: $(echo "$BEFORE_OPTS" | jq -c '.')"

# Restore real catalogue (TO) so Update has somewhere to go.
restore_catalogue_from_github
RESTORED_LATEST="$(store_version_latest "$STORE_SLUG")"
if [[ "$RESTORED_LATEST" != "$TO_VERSION" ]]; then
  log "ERROR: after restoring GitHub catalogue, version_latest=$RESTORED_LATEST (want $TO_VERSION)"
  exit 1
fi
log "Catalogue restored: version_latest=$RESTORED_LATEST; installed=$(app_version "$STORE_SLUG")"

# 6. Update to TO.
log "Updating $STORE_SLUG → $TO_VERSION"
ha apps update "$STORE_SLUG" --no-progress
wait_app_not_busy "$STORE_SLUG" 600 || exit 1

AFTER_VER="$(app_version "$STORE_SLUG")"
AFTER_OPTS="$(app_options_json "$STORE_SLUG")"
AFTER_STATE="$(app_state "$STORE_SLUG")"
log "After update: version=$AFTER_VER state=$AFTER_STATE"

# 7. Assert.
fail=false
if [[ "$AFTER_VER" != "$TO_VERSION" ]]; then
  log "ERROR: expected version $TO_VERSION after update, got ${AFTER_VER:-none}"
  fail=true
fi
if ! options_equal "$BEFORE_OPTS" "$AFTER_OPTS"; then
  log "ERROR: options changed across Update:"
  log "  before: $(echo "$BEFORE_OPTS" | jq -c '.')"
  log "  after:  $(echo "$AFTER_OPTS" | jq -c '.')"
  fail=true
fi
case "$AFTER_STATE" in
  started|stopped|error) ;;
  *)
    log "ERROR: unexpected post-update state=$AFTER_STATE (install/update failure?)"
    fail=true
    ;;
esac
if $fail; then
  log "FAIL: store Update rehearsal"
  exit 1
fi

log "Stopping store slug $STORE_SLUG (leave installed for next run)"
ha apps stop "$STORE_SLUG" --no-progress || true
# Packaging smoke may leave state=error (no panel); treat stopped|error as done.
stop_deadline=$((SECONDS + 60))
while (( SECONDS < stop_deadline )); do
  st="$(app_state "$STORE_SLUG")"
  case "$st" in stopped|error) break ;; esac
  sleep 2
done
log "$STORE_SLUG state=$(app_state "$STORE_SLUG") after stop"

if $RESTART_LOCAL; then
  if app_installed "$LOCAL_SLUG"; then
    log "Restarting $LOCAL_SLUG"
    ha apps start "$LOCAL_SLUG" --no-progress || log "WARNING: local start returned non-zero"
    wait_app_started_or_error "$LOCAL_SLUG" 120 || true
    log "$LOCAL_SLUG state=$(app_state "$LOCAL_SLUG")"
  else
    log "$LOCAL_SLUG not installed — skip restart"
  fi
else
  log "--no-restart-local: leaving $LOCAL_SLUG stopped"
fi

ORIGIN_BACKUP=""
restore_store_origin
trap - EXIT

log "PASS: store Update rehearsal $FROM_VERSION → $TO_VERSION on $STORE_SLUG"
echo "STORE_UPGRADE_SMOKE_PASS from=$FROM_VERSION to=$TO_VERSION slug=$STORE_SLUG"
