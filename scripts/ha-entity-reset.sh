#!/usr/bin/env bash
# Wipe HA entity/device registries + MQTT retained discovery/state so the next
# Texecom Alarm start does not create orphan / suffixed entity IDs.
# Keeps login, onboarding, MQTT config entry, and Mosquitto options.
#
# Usage: ./scripts/ha-entity-reset.sh --yes
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

HA=/mnt/supervisor/homeassistant
MOSQ=/mnt/supervisor/apps/data/core_mosquitto

log() { printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }

if [[ "${1:-}" != "--yes" ]]; then
  cat <<'EOF' >&2
ha-entity-reset.sh refuses to run without --yes.

This deletes Home Assistant history + entity/device registries and clears
MQTT retained homeassistant/# and texecom/# topics. Auth/onboarding and the
MQTT config entry are kept. Texecom Alarm is left stopped.

Usage: ./scripts/ha-entity-reset.sh --yes
EOF
  exit 2
fi

log "=== ha-entity-reset ==="

if ! docker inspect hassio_supervisor --format '{{.State.Status}}' 2>/dev/null | grep -qx running; then
  log "ERROR: hassio_supervisor is not running. Run ./scripts/ha-cold-start.sh first."
  exit 1
fi

if ! command -v ha >/dev/null 2>&1; then
  log "ERROR: ha CLI not found"
  exit 1
fi

log "1. Stop Texecom Alarm (ignore if not installed)"
ha apps stop local_texecom_alarm >/dev/null 2>&1 || true

mosq_running=false
if docker inspect app_core_mosquitto --format '{{.State.Status}}' 2>/dev/null | grep -qx running; then
  mosq_running=true
fi

if $mosq_running; then
  log "2. Clear retained MQTT topics (homeassistant/#, texecom/#)"
  docker exec app_core_mosquitto mosquitto_sub -u texecom -P texecom-accept \
    -t 'homeassistant/#' -t 'texecom/#' -v -W 2 > /tmp/mqtt_retained_raw.txt 2>/dev/null || true
  awk '{print $1}' /tmp/mqtt_retained_raw.txt 2>/dev/null | sort -u > /tmp/mqtt_retained_topics.txt || true
  while read -r t; do
    [[ -n "$t" ]] || continue
    docker exec app_core_mosquitto mosquitto_pub -u texecom -P texecom-accept -t "$t" -n -r 2>/dev/null || true
  done < /tmp/mqtt_retained_topics.txt
  log "   cleared $(wc -l < /tmp/mqtt_retained_topics.txt | tr -d ' ') topic(s)"

  log "3. Stop Mosquitto and delete persistence DB"
  ha apps stop core_mosquitto
  for i in $(seq 1 30); do
    st=$(ha apps info core_mosquitto 2>/dev/null | awk '/^state:/{print $2; exit}') || st=unknown
    [[ "$st" == "stopped" || "$st" == "unknown" ]] && break
    sleep 1
  done
  sudo rm -f "$MOSQ/mosquitto.db"
else
  log "2–3. Mosquitto not running — skip MQTT clear; remove mosquitto.db if present"
  sudo rm -f "$MOSQ/mosquitto.db" 2>/dev/null || true
fi

log "4. Stop HA Core; wipe DB + entity/device/area registries + restore_state"
ha core stop
for i in $(seq 1 40); do
  st=$(docker inspect homeassistant --format '{{.State.Status}}' 2>/dev/null || echo missing)
  case "$st" in exited|missing) break ;; esac
  sleep 1
done

sudo rm -f "$HA"/home-assistant_v2.db \
           "$HA"/home-assistant_v2.db-shm \
           "$HA"/home-assistant_v2.db-wal
sudo rm -f "$HA"/.storage/core.entity_registry \
           "$HA"/.storage/core.device_registry \
           "$HA"/.storage/core.restore_state \
           "$HA"/.storage/core.area_registry

log "5. Start Mosquitto (if installed) + HA Core; leave Texecom stopped"
if ha apps info core_mosquitto >/dev/null 2>&1; then
  ha apps start core_mosquitto || log "WARN: could not start core_mosquitto"
fi
ha core start

deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 http://127.0.0.1:8123/ 2>/dev/null || echo 000)
  case "$code" in
    200|301|302|303|307|308)
      log "Core back (HTTP $code)"
      break
      ;;
  esac
  sleep 2
done

log "DONE. Open UI: http://localhost:7123/  (hard-refresh / re-login if session is stale)"
log "Texecom Alarm is stopped — start it when you want a clean rediscovery."
log "Kept: auth, onboarding, config_entries, Mosquitto options.json"
exit 0
