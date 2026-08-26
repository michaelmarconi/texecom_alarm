#!/usr/bin/env bash
# Rehearse the household Supervisor Update path in simulated HA:
# stop local_* → ensure #app-previous store repo → confirm it's installed at
# the prior version → seed the real panel/MQTT credentials (local_texecom_alarm
# stays stopped throughout, so no contention) → confirm it actually logs into
# the real panel and publishes MQTT → force-push #app's tip onto #app-previous
# → Update → assert version + options + it still works against the real panel
# → stop store slug → optionally restart local_*.
#
# Not live smoke (/run --target). Not a substitute for local rebuild.
# Do not run the store copy alongside a started local_texecom_alarm.
#
# Home Assistant has no add-on downgrade/version-pin (no UI, no CLI flag; the
# only supported rollback is a backup restore). The only way to prove a real
# FROM→TO Update is to control what a stable git ref serves, then move it
# forward for real. #app-previous is a permanent branch kept deliberately one
# release behind #app, used only by this rehearsal — never by real households.
#
# Do NOT repoint a repository's origin to fake an old version as a shortcut:
# Supervisor actively corrects origin back to its stored canonical URL the
# moment it notices a mismatch, silently defeating that trick (confirmed in
# Supervisor logs, 26 Aug 2026). origin always stays the real GitHub URL here;
# only which permanent branch differs.
#
# Usage:
#   ./scripts/ha-store-upgrade-smoke.sh [--no-restart-local]
#   ./scripts/ha-store-upgrade-smoke.sh --bootstrap X.Y.Z
#
# --bootstrap X.Y.Z: one-time setup on a fresh clone (or after #app-previous
#   was deleted) — creates #app-previous pointed at tag vX.Y.Z's #app tree,
#   then exits without running a rehearsal. Run the plain form next time.
#
# Preconditions: apps-devcontainer with Supervisor/Core already up (/run / cold-start).
# GHCR must publish the TO tag (image: ghcr.io/.../texecom-alarm:X.Y.Z).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STORE_REPO_URL="${TEXECOM_STORE_REPO_URL:-https://github.com/michaelmarconi/texecom_alarm#app-previous}"
GITHUB_REPO="${TEXECOM_GITHUB_REPO:-https://github.com/michaelmarconi/texecom_alarm.git}"
LOCAL_SLUG="local_texecom_alarm"
DISK_MIN_GIB=2
CONFIG_YAML="texecom_alarm/config.yaml"

RESTART_LOCAL=true
BOOTSTRAP_VERSION=""

log() { printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }

usage() {
  cat <<'EOF' >&2
Usage: ./scripts/ha-store-upgrade-smoke.sh [--no-restart-local]
       ./scripts/ha-store-upgrade-smoke.sh --bootstrap X.Y.Z

Rehearses Supervisor store Update (FROM → TO) via the #app-previous branch,
which is deliberately held one release behind #app.

  --bootstrap X.Y.Z   One-time: create #app-previous at tag vX.Y.Z, then exit
  --no-restart-local  Leave local_texecom_alarm stopped after the smoke
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bootstrap)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      BOOTSTRAP_VERSION="$2"
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

# Every key present BEFORE must keep the same value AFTER — proves the
# household's own settings survive the Update. New keys a changed schema adds
# with defaults (and old keys a changed schema no longer declares but
# Supervisor still carries — see docs/run.md "Stale option keys") are both
# expected and not a failure; only a changed/missing *existing* value is.
# texecom-rehearsal/# state topics are retained but never HA-facing (discovery
# configs always point at local_texecom_alarm's real "texecom/..." topics —
# same hardcoded unique_id/device identifiers regardless of topic prefix, so
# whichever install starts last "wins" the discovery pointer, and restarting
# local_texecom_alarm at the end of this script always wins it back). Still,
# clear the orphaned retained rehearsal topics so they don't pile up forever.
clear_rehearsal_retained() {
  local prefix="texecom-rehearsal"
  local mosq_container
  mosq_container="$(docker ps --format '{{.Names}}' | grep -E '_core_mosquitto$' | head -1)"
  if [[ -z "$mosq_container" ]]; then
    log "WARNING: mosquitto container not found — skip retained cleanup for $prefix/#"
    return 0
  fi
  local opts="${REAL_OPTS:-}"
  [[ -n "$opts" ]] || return 0
  local mqtt_user mqtt_pass
  mqtt_user="$(jq -r '.mqtt_username // empty' <<<"$opts")"
  mqtt_pass="$(jq -r '.mqtt_password // empty' <<<"$opts")"
  [[ -n "$mqtt_user" ]] || return 0
  log "Clearing retained MQTT state under $prefix/# (rehearsal-only, never HA-facing)"
  docker exec "$mosq_container" sh -c "
    mosquitto_sub -h localhost -p 1883 -u '$mqtt_user' -P '$mqtt_pass' -t '$prefix/#' -v -W 2 2>/dev/null \
      | awk '{print \$1}' \
      | while read -r t; do mosquitto_pub -h localhost -p 1883 -u '$mqtt_user' -P '$mqtt_pass' -t \"\$t\" -r -n; done
  " || log "WARNING: retained cleanup for $prefix/# failed (non-fatal)"
}

options_preserved() {
  local before="$1" after="$2"
  jq -n -e --argjson before "$before" --argjson after "$after" '
    [$before | to_entries[] | select(.value != $after[.key])] as $changed
    | $changed == []
  ' >/dev/null
}

# Look for real evidence the app actually works post-Update — not just that
# its version/options fields moved. mqtt_connectivity_discovery_published
# only logs once startup (login → zone enumeration → MQTT discovery) has
# fully succeeded.
wait_for_functional_proof() {
  local slug="$1" timeout="${2:-90}"
  local deadline=$((SECONDS + timeout)) logs
  while (( SECONDS < deadline )); do
    logs="$(ha apps logs "$slug" 2>/dev/null || true)"
    if grep -q "mqtt_connectivity_discovery_published" <<<"$logs"; then
      if grep -qE "ERROR|CRITICAL" <<<"$logs"; then
        log "ERROR: $slug logged ERROR/CRITICAL during startup:"
        grep -E "ERROR|CRITICAL" <<<"$logs" | sed 's/^/  | /' >&2
        return 1
      fi
      log "$slug: real panel login + zone enumeration + MQTT discovery confirmed in logs"
      return 0
    fi
    sleep 3
  done
  log "ERROR: $slug did not confirm MQTT discovery within ${timeout}s (real panel unreachable?)"
  tail -n 20 <<<"$logs" | sed 's/^/  | /' >&2
  return 1
}

ensure_store_repo() {
  local sources
  sources="$(ha store --raw-json | jq -r '.data.repositories[]?.source // empty')"
  if printf '%s\n' "$sources" | grep -Fxq "$STORE_REPO_URL"; then
    log "Store repo already present: $STORE_REPO_URL"
    return 0
  fi
  if printf '%s\n' "$sources" | grep -Fq "github.com/michaelmarconi/texecom_alarm#app"; then
    log "WARNING: a texecom_alarm store URL is present but not exactly $STORE_REPO_URL:"
    printf '%s\n' "$sources" | grep -F "github.com/michaelmarconi/texecom_alarm#app" | sed 's/^/  | /' || true
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

# #app-previous carries the exact same config.yaml `name:` as the real
# add-on, so its Supervisor tile is indistinguishable from local_texecom_alarm
# at a glance — confusing (learned the hard way, 26 Aug 2026). Rewrite the
# name only in what we push to #app-previous so its tile reads distinctly.
patch_rehearsal_name() {
  local cfg="$1"
  sed -i -E 's/^name:[[:space:]]*(.*)$/name: \1 (Rehearsal)/' "$cfg"
}

# Commit $1 (a populated tree dir) as a fresh orphan commit on app-previous
# and force-push it — matching how CI publishes #app itself (see
# sync-app-branch.yml): no shared ancestry required, just the tree that
# matters right now.
publish_app_previous_tree() {
  local tree_dir="$1" msg="$2"
  patch_rehearsal_name "$tree_dir/texecom_alarm/config.yaml"
  (
    cd "$tree_dir"
    git init -q
    git checkout -q -b app-previous
    git config user.name "ha-store-upgrade-smoke"
    git config user.email "store-smoke@local"
    git add -A
    git commit -q -m "$msg"
    git push --force "$GITHUB_REPO" app-previous
  )
}

install_from_store() {
  local slug="$1" expect_version="$2"
  log "Installing $slug (catalogue latest should be $expect_version)"
  ha apps install "$slug" --no-progress
  wait_app_not_busy "$slug" 600 || return 1
  local ver
  ver="$(app_version "$slug")"
  if [[ "$ver" != "$expect_version" ]]; then
    log "ERROR: after install expected version=$expect_version got version=${ver:-none}"
    return 1
  fi
  log "Installed $slug@$ver"
}

# --- bootstrap mode ---
# One-time: create #app-previous pointed at tag vX.Y.Z's synced #app tree.
# #app is force-pushed as a fresh orphan commit per release (no shared
# ancestry), so #app-previous starts life the same way: an orphan snapshot of
# whatever #app looked like at that release.
run_bootstrap() {
  local version="$1"
  if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    log "ERROR: --bootstrap needs SemVer X.Y.Z, got: $version"
    exit 2
  fi
  if ! git rev-parse "v${version}" >/dev/null 2>&1; then
    log "ERROR: local tag v${version} not found — git fetch --tags first"
    exit 1
  fi
  local work
  # /tmp is mounted noexec in this devcontainer — build under the repo root
  # (exec-allowed) instead, or build-app-branch-tree.sh's shebang silently
  # fails with "Permission denied".
  work="$(mktemp -d "$REPO_ROOT/.bootstrap-tmp.XXXXXX")"
  # Intentionally expand $work now, not at trap time.
  # shellcheck disable=SC2064
  trap "rm -rf '$work'" RETURN
  log "Building #app-previous tree from v${version} (thin catalogue tree)"
  mkdir -p "$work/src"
  git -C "$REPO_ROOT" archive "v${version}" | tar -x -C "$work/src"
  chmod +x "$work/src/scripts/build-app-branch-tree.sh"
  # Use v${version}'s OWN copy of the builder script, not this repo's current
  # one — it resolves its root from its own file location, so running the
  # current script here would silently build from current main instead of
  # the archived tag (bit us once; do not "simplify" this back).
  "$work/src/scripts/build-app-branch-tree.sh" "$work/tree"
  publish_app_previous_tree "$work/tree" "Bootstrap app-previous at v${version}"
  log "Bootstrapped #app-previous at v${version}. Publish/tag the next release, then re-run without --bootstrap."
}

if [[ -n "$BOOTSTRAP_VERSION" ]]; then
  run_bootstrap "$BOOTSTRAP_VERSION"
  exit 0
fi

# --- main ---

log "=== ha-store-upgrade-smoke ==="

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
log "Rehearsal target: TO=$TO_VERSION (via #app → #app-previous)"

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

# 2. Ensure #app-previous store repo + reload.
ensure_store_repo
log "Reloading store"
ha store reload --no-progress

# 3. Resolve store slug.
STORE_SLUG="$(resolve_store_slug)"
log "Rehearsal slug: $STORE_SLUG"

FROM_VERSION="$(store_version_latest "$STORE_SLUG")"
if [[ -z "$FROM_VERSION" || "$FROM_VERSION" == "null" ]]; then
  log "ERROR: #app-previous has no readable version. Run --bootstrap X.Y.Z first."
  exit 1
fi
if [[ "$FROM_VERSION" == "$TO_VERSION" ]]; then
  log "ERROR: #app-previous is already at $TO_VERSION — nothing to rehearse."
  log "Did a previous run already advance it? #app-previous only moves during this script."
  exit 1
fi
log "Rehearsal: FROM=$FROM_VERSION (current #app-previous) → TO=$TO_VERSION (#app's tip)"

# 4. Install (or confirm already installed) at FROM.
if app_installed "$STORE_SLUG"; then
  cur="$(app_version "$STORE_SLUG")"
  if [[ "$cur" != "$FROM_VERSION" ]]; then
    log "ERROR: $STORE_SLUG installed at $cur, expected $FROM_VERSION (#app-previous's current version)"
    log "Out of lockstep — reinstall or re-bootstrap #app-previous to recover."
    exit 1
  fi
  log "$STORE_SLUG already installed at $FROM_VERSION"
else
  install_from_store "$STORE_SLUG" "$FROM_VERSION"
fi

# Seed real connection details from local_texecom_alarm so this slug can
# genuinely log into the household's panel and broker — proving the exact
# published artifact works, not just that its version/options field moved.
# local_texecom_alarm is stopped throughout (single ComIP), so no contention.
# A distinct mqtt_topic_prefix avoids colliding with local's retained
# discovery topics/entities and doubles as the options-persistence marker.
REAL_OPTS="$(app_options_json "$LOCAL_SLUG")"
if [[ "$REAL_OPTS" == "{}" || -z "$(jq -r '.panel_host // empty' <<<"$REAL_OPTS")" ]]; then
  log "ERROR: $LOCAL_SLUG has no panel_host configured to copy for the rehearsal"
  exit 1
fi
CURRENT_OPTS="$(app_options_json "$STORE_SLUG")"
SEEDED_OPTS="$(jq -nc --argjson cur "$CURRENT_OPTS" --argjson real "$REAL_OPTS" '
  ($cur * $real) | .mqtt_topic_prefix = "texecom-rehearsal"
')"
log "Seeding real connection details on $STORE_SLUG (topic prefix texecom-rehearsal)"
supervisor_set_options "$STORE_SLUG" "$SEEDED_OPTS" >/dev/null

log "Starting $STORE_SLUG@$FROM_VERSION"
ha apps start "$STORE_SLUG" --no-progress || log "WARNING: start returned non-zero"
wait_app_started_or_error "$STORE_SLUG" 180 || exit 1
if [[ "$(app_state "$STORE_SLUG")" != "started" ]]; then
  log "ERROR: $STORE_SLUG state=$(app_state "$STORE_SLUG") after start — expected started (real panel configured)"
  exit 1
fi
wait_for_functional_proof "$STORE_SLUG" 90 || exit 1

BEFORE_OPTS="$(app_options_json "$STORE_SLUG")"
log "Options snapshot before update: $(echo "$BEFORE_OPTS" | jq -c '.')"

# 5. Advance #app-previous to #app's current tip — a real, permanent git push,
# not a temporary spoof. #app is a fresh orphan commit per release, so this
# always needs --force (no shared ancestry to fast-forward from). Re-tree
# (rather than a raw ref copy) so the rehearsal name patch keeps applying.
log "Force-pushing #app's tip onto #app-previous"
git -C "$REPO_ROOT" fetch origin app --no-tags -q
ADVANCE_WORK="$(mktemp -d "$REPO_ROOT/.bootstrap-tmp.XXXXXX")"
mkdir -p "$ADVANCE_WORK/tree"
git -C "$REPO_ROOT" archive origin/app | tar -x -C "$ADVANCE_WORK/tree"
publish_app_previous_tree "$ADVANCE_WORK/tree" "Advance app-previous to ${TO_VERSION}"
rm -rf "$ADVANCE_WORK"

log "Reloading store to pick up #app-previous → $TO_VERSION"
ha store reload --no-progress
RESTORED_LATEST="$(store_version_latest "$STORE_SLUG")"
if [[ "$RESTORED_LATEST" != "$TO_VERSION" ]]; then
  log "ERROR: after advancing #app-previous, version_latest=$RESTORED_LATEST (want $TO_VERSION)"
  exit 1
fi
log "Catalogue advanced: version_latest=$RESTORED_LATEST; installed=$(app_version "$STORE_SLUG")"

# 6. Update to TO.
log "Updating $STORE_SLUG → $TO_VERSION"
ha apps update "$STORE_SLUG" --no-progress
wait_app_not_busy "$STORE_SLUG" 600 || exit 1

wait_app_started_or_error "$STORE_SLUG" 180 || true
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
if ! options_preserved "$BEFORE_OPTS" "$AFTER_OPTS"; then
  log "ERROR: an existing option's value changed across Update (new keys / lingering stale keys are fine):"
  log "  before: $(echo "$BEFORE_OPTS" | jq -c '.')"
  log "  after:  $(echo "$AFTER_OPTS" | jq -c '.')"
  fail=true
fi
if [[ "$AFTER_STATE" != "started" ]]; then
  log "ERROR: expected state=started after update (real panel configured), got $AFTER_STATE"
  fail=true
elif ! wait_for_functional_proof "$STORE_SLUG" 90; then
  fail=true
fi
if $fail; then
  log "FAIL: store Update rehearsal"
  exit 1
fi

log "Stopping store slug $STORE_SLUG (leave installed at $TO_VERSION for next run's FROM)"
ha apps stop "$STORE_SLUG" --no-progress || true
stop_deadline=$((SECONDS + 60))
while (( SECONDS < stop_deadline )); do
  st="$(app_state "$STORE_SLUG")"
  case "$st" in stopped|error) break ;; esac
  sleep 2
done
log "$STORE_SLUG state=$(app_state "$STORE_SLUG") after stop"

clear_rehearsal_retained

if $RESTART_LOCAL; then
  if app_installed "$LOCAL_SLUG"; then
    # Rebuild, not just start — this script may run after a version bump with
    # local_texecom_alarm's last build predating it (start alone would leave
    # a stale image/version behind, same reasoning as ha-cold-start.sh).
    log "Rebuilding + starting $LOCAL_SLUG from current source"
    ha apps rebuild "$LOCAL_SLUG" --no-progress \
      || log "WARNING: rebuild failed — starting whatever image is cached"
    ha apps start "$LOCAL_SLUG" --no-progress || log "WARNING: local start returned non-zero"
    wait_app_started_or_error "$LOCAL_SLUG" 120 || true
    log "$LOCAL_SLUG state=$(app_state "$LOCAL_SLUG") version=$(app_version "$LOCAL_SLUG")"
    # Wait for local's own discovery republish to win back the shared
    # unique_id/device-identifier namespace from the rehearsal slug's last
    # publish, so this script never exits while entities still point at
    # texecom-rehearsal/... topics.
    wait_for_functional_proof "$LOCAL_SLUG" 90 || log "WARNING: $LOCAL_SLUG discovery re-publish not confirmed"
  else
    log "$LOCAL_SLUG not installed — skip restart"
  fi
else
  log "--no-restart-local: leaving $LOCAL_SLUG stopped"
fi

log "PASS: store Update rehearsal $FROM_VERSION → $TO_VERSION on $STORE_SLUG"
echo "STORE_UPGRADE_SMOKE_PASS from=$FROM_VERSION to=$TO_VERSION slug=$STORE_SLUG"
