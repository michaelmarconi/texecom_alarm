#!/usr/bin/env bash
# Cold-start Supervisor + Home Assistant in the apps devcontainer, then ensure
# Mosquitto + the local Texecom Alarm app are installed, configured, and started.
#
# Supervisor-channel Core defaults to HTTP :80 and puts a legacy redirect on
# :8123 → http://localhost/ (port stripped). Through Cursor port-forward that
# becomes an ERR_TOO_MANY_REDIRECTS loop. We pin server_port to 8123 so the
# laptop contract matches the HA apps template (forwardPorts 8123 / appPort 7123).
#
# Idempotent: re-running does not wipe HA config/DB; it only starts missing
# pieces and fills empty Texecom options. Destructive wipe is ha-entity-reset.sh.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LOG="${HA_COLD_START_LOG:-/tmp/ha-cold-start.log}"
PID_FILE="${HA_COLD_START_PID:-/tmp/ha-cold-start.supervisor_run.pid}"
READY_TIMEOUT_SEC="${HA_COLD_START_TIMEOUT:-900}"
DISK_MIN_GIB=2
CORE_PORT=8123

# Sim defaults (override via env). Part-Arm labels match config.yaml schema tokens.
PANEL_HOST="${TEXECOM_PANEL_HOST:-192.168.1.183}"
PANEL_PORT="${TEXECOM_PANEL_PORT:-10001}"
UDL_PASSWORD="${TEXECOM_UDL_PASSWORD:-1234}"
MQTT_USER="${TEXECOM_MQTT_USERNAME:-texecom}"
MQTT_PASS="${TEXECOM_MQTT_PASSWORD:-texecom-accept}"
MQTT_HOST="${TEXECOM_MQTT_HOST:-core-mosquitto}"
PART_ARM_1="${TEXECOM_PART_ARM_1:-Night 🌙}"
PART_ARM_2="${TEXECOM_PART_ARM_2:-Home 🏠}"
PART_ARM_3="${TEXECOM_PART_ARM_3:-Unused}"

log() { printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }

disk_free_gib() {
  awk 'NR==2 { printf "%.1f", $4 / 1024 / 1024 }' < <(df -Pk /mnt/supervisor)
}

http_code() {
  local port="${1:-$CORE_PORT}" code
  code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 "http://127.0.0.1:${port}/" 2>/dev/null || true)"
  [[ -n "$code" ]] || code=000
  printf '%s\n' "$code"
}

core_ready_on() {
  case "$(http_code "$1")" in
    200|301|302|303|307|308) return 0 ;;
    *) return 1 ;;
  esac
}

core_ready() {
  core_ready_on "$CORE_PORT" || core_ready_on 80
}

# True when :8123 is the real UI (relative Location or 200), not the legacy absolute redirect to :80.
core_on_classic_port() {
  local headers loc
  headers="$(curl -sS -D- -o /dev/null --connect-timeout 2 "http://127.0.0.1:${CORE_PORT}/" 2>/dev/null || true)"
  loc="$(printf '%s\n' "$headers" | tr -d '\r' | awk 'tolower($1)=="location:"{print $2; exit}')"
  if [[ -z "$loc" || "$loc" == /* ]]; then
    return 0
  fi
  [[ "$loc" == *":${CORE_PORT}"* || "$loc" == *":${CORE_PORT}/"* ]] && return 0
  return 1
}

pin_server_port_8123() {
  if ! docker inspect homeassistant --format '{{.State.Status}}' 2>/dev/null | grep -qx running; then
    return 1
  fi
  docker exec -u root homeassistant sh -c 'python3 - <<'"'"'PY'"'"'
import json
from pathlib import Path
p = Path("/config/.storage/http")
if not p.exists():
    raise SystemExit(2)
data = json.loads(p.read_text())
stable = data.setdefault("data", {}).setdefault("stable", {})
if stable.get("server_port") == 8123:
    print("already_8123")
    raise SystemExit(0)
stable["server_port"] = 8123
p.write_text(json.dumps(data, indent=2) + "\n")
print("pinned_8123")
PY'
}

ensure_classic_port() {
  local result
  result="$(pin_server_port_8123 2>/dev/null || true)"
  case "$result" in
    *pinned_8123*)
      log "Pinned Core http.server_port=8123 (was not 8123); restarting Core"
      ha core restart >/dev/null 2>&1 || docker restart homeassistant >/dev/null 2>&1 || true
      ;;
    *already_8123*)
      log "Core http.server_port already 8123"
      ;;
    *)
      log "pin result: ${result:-failed (http storage not ready yet?)}"
      local i
      for i in 1 2 3 4 5 6 7 8 9 10; do
        sleep 2
        result="$(pin_server_port_8123 2>/dev/null || true)"
        case "$result" in
          *pinned_8123*)
            log "Pinned Core http.server_port=8123 on retry $i; restarting Core"
            ha core restart >/dev/null 2>&1 || docker restart homeassistant >/dev/null 2>&1 || true
            break
            ;;
          *already_8123*)
            log "Core http.server_port already 8123 (retry $i)"
            break
            ;;
        esac
      done
      ;;
  esac

  local deadline=$((SECONDS + 120))
  while (( SECONDS < deadline )); do
    if core_ready_on "$CORE_PORT" && core_on_classic_port; then
      return 0
    fi
    sleep 2
  done
  return 1
}

supervisor_up() {
  docker inspect hassio_supervisor --format '{{.State.Status}}' 2>/dev/null | grep -qx running
}

app_installed() {
  ha apps info "$1" --raw-json 2>/dev/null | jq -e '.data.version != null' >/dev/null 2>&1
}

app_state() {
  ha apps info "$1" --raw-json 2>/dev/null | jq -r '.data.state // "unknown"'
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

# POST JSON options to Supervisor via Core's SUPERVISOR_TOKEN (ha CLI has no options cmd).
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
with urllib.request.urlopen(req) as resp:
    body = json.loads(resp.read().decode())
if body.get("result") != "ok":
    raise SystemExit(f"options failed: {body}")
print("ok")
'
}

ensure_app_installed() {
  local slug="$1"
  if app_installed "$slug"; then
    log "$slug already installed (version $(ha apps info "$slug" --raw-json | jq -r '.data.version'))"
    return 0
  fi
  log "Installing $slug…"
  ha apps install "$slug" --no-progress
  log "Installed $slug"
}

ensure_mosquitto() {
  ensure_app_installed core_mosquitto

  local current_user opts need_restart=false
  current_user="$(ha apps info core_mosquitto --raw-json | jq -r --arg u "$MQTT_USER" \
    '[.data.options.logins[]? | select(.username==$u)] | length')"
  opts="$(jq -nc \
    --arg u "$MQTT_USER" --arg p "$MQTT_PASS" \
    '{
      logins: [{username: $u, password: $p}],
      log_dest: [],
      log_type: [],
      require_certificate: false,
      certfile: "fullchain.pem",
      keyfile: "privkey.pem",
      customize: {active: false, folder: "mosquitto"}
    }')"

  if [[ "$current_user" == "0" ]]; then
    log "Ensuring Mosquitto login ${MQTT_USER}"
    supervisor_set_options core_mosquitto "$opts" >/dev/null
    need_restart=true
  else
    log "Mosquitto login ${MQTT_USER} already present"
  fi

  local st
  st="$(app_state core_mosquitto)"
  if [[ "$st" != "started" ]]; then
    log "Starting core_mosquitto (was $st)"
    ha apps start core_mosquitto --no-progress
    wait_app_state core_mosquitto started 120 || true
  elif $need_restart; then
    # Restart only when options changed — a broker bounce fires Texecom LWT →
    # retained texecom/status=offline and HA marks every zone unavailable.
    log "Restarting core_mosquitto to apply login options"
    ha apps restart core_mosquitto --no-progress
    wait_app_state core_mosquitto started 120 || true
  else
    log "core_mosquitto already started"
  fi
}

ensure_texecom() {
  ha store reload >/dev/null 2>&1 || true
  ensure_app_installed local_texecom_alarm

  local current_host
  current_host="$(ha apps info local_texecom_alarm --raw-json | jq -r '.data.options.panel_host // empty')"
  if [[ -z "$current_host" ]]; then
    log "Applying Texecom sim options (panel=${PANEL_HOST}:${PANEL_PORT}, mqtt=${MQTT_HOST})"
    local opts
    opts="$(jq -nc \
      --arg host "$PANEL_HOST" \
      --argjson port "$PANEL_PORT" \
      --arg udl "$UDL_PASSWORD" \
      --arg mqtt_host "$MQTT_HOST" \
      --arg mqtt_user "$MQTT_USER" \
      --arg mqtt_pass "$MQTT_PASS" \
      --arg pa1 "$PART_ARM_1" \
      --arg pa2 "$PART_ARM_2" \
      --arg pa3 "$PART_ARM_3" \
      '{
        panel_host: $host,
        panel_port: $port,
        udl_password: $udl,
        mqtt_host: $mqtt_host,
        mqtt_port: 1883,
        mqtt_username: $mqtt_user,
        mqtt_password: $mqtt_pass,
        mqtt_topic_prefix: "texecom",
        part_arm_1: $pa1,
        part_arm_2: $pa2,
        part_arm_3: $pa3,
        reconnect_normal_attempts: 4,
        reconnect_normal_interval_seconds: 2.5,
        reconnect_trigger_attempts: 18,
        reconnect_trigger_interval_seconds: 5
      }')"
    supervisor_set_options local_texecom_alarm "$opts" >/dev/null
  else
    log "Texecom options already set (panel_host=$current_host) — leaving Configuration as-is"
  fi

  local st
  st="$(app_state local_texecom_alarm)"
  if [[ "$st" != "started" ]]; then
    log "Starting local_texecom_alarm (was $st)"
    ha apps start local_texecom_alarm --no-progress || log "WARNING: start returned non-zero"
  else
    log "local_texecom_alarm already started"
  fi
  wait_app_state local_texecom_alarm started 120 || true
  st="$(app_state local_texecom_alarm)"
  log "local_texecom_alarm state=$st"
  if [[ "$st" == "error" ]]; then
    log "WARNING: Texecom in error — often ComIP single-connection (stop the prior MQTT bridge / other clients). Tail:"
    ha apps logs local_texecom_alarm 2>/dev/null | tail -n 15 | sed 's/^/  | /' || true
  fi
}

ensure_apps() {
  if ! command -v ha >/dev/null 2>&1; then
    log "WARNING: ha CLI missing — skip Mosquitto/Texecom"
    return 0
  fi
  if ! docker inspect homeassistant --format '{{.State.Status}}' 2>/dev/null | grep -qx running; then
    log "WARNING: homeassistant not running — skip Mosquitto/Texecom"
    return 0
  fi
  log "=== ensure Mosquitto + Texecom Alarm ==="
  ensure_mosquitto
  ensure_texecom
}

print_open_ui() {
  log "Open UI (HA docs):     http://localhost:7123/   # Docker appPort 7123→8123"
  log "Open UI (Cursor Ports): http://localhost:8123/   # same Core via IDE forward"
  log "Do not open or forward :80 (Supervisor default — redirect loop under Cursor)."
  log "Apps: core_mosquitto=$(app_state core_mosquitto)  local_texecom_alarm=$(app_state local_texecom_alarm)"
}

finish_ready() {
  ensure_classic_port || {
    log "ERROR: Core came up but :8123 is still a legacy redirect to :80"
    return 1
  }
  ensure_apps
  print_open_ui
  return 0
}

log "=== ha-cold-start ==="

if core_ready; then
  log "Home Assistant already responding"
  finish_ready || exit 1
  exit 0
fi

free="$(disk_free_gib)"
log "Disk free on /mnt/supervisor: ${free} GiB (need ≥ ${DISK_MIN_GIB} to start/pull)"
awk -v f="$free" -v m="$DISK_MIN_GIB" 'BEGIN { exit !(f + 0 >= m) }' || {
  log "ERROR: not enough free disk for Supervisor install/pull. See docs/run.md § Disk space."
  exit 1
}
if ! supervisor_up; then
  if ! command -v supervisor_run >/dev/null 2>&1; then
    log "ERROR: supervisor_run not found (are you in the HA apps devcontainer?)"
    exit 1
  fi
  log "Starting supervisor_run (log: $LOG)"
  : >"$LOG"
  nohup supervisor_run >>"$LOG" 2>&1 &
  echo $! >"$PID_FILE"
  log "supervisor_run pid=$(cat "$PID_FILE")"
else
  log "hassio_supervisor already running; waiting for Core"
fi

deadline=$((SECONDS + READY_TIMEOUT_SEC))
tries=0
while (( SECONDS < deadline )); do
  tries=$((tries + 1))
  code="$(http_code "$CORE_PORT")"
  if core_ready; then
    log "READY after ${tries} checks (HTTP $code on probe)"
    finish_ready || exit 1
    exit 0
  fi
  if (( tries % 6 == 0 )); then
    log "still waiting… try=$tries http8123=$code http80=$(http_code 80) (tail $LOG)"
    tail -n 3 "$LOG" 2>/dev/null | sed 's/^/  | /' || true
  fi
  sleep 5
done

log "ERROR: timed out after ${READY_TIMEOUT_SEC}s waiting for Core"
log "Last log lines:"
tail -n 40 "$LOG" 2>/dev/null || true
exit 1
