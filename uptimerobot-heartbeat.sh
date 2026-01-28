#!/usr/bin/env bash
set -euo pipefail

# 5echo - UpTimeRobot Heartbeat Bridge
# - Maintains a list of internal IP targets
# - If a target responds to ping -> send its own UpTimeRobot heartbeat
# - If ping fails -> do NOT send heartbeat (UpTimeRobot will alert when missing)
#
# Config format (pipe-delimited):
# NAME|IP|HEARTBEAT_URL

APP_NAME="uptimerobot-heartbeat"
CONFIG_FILE="/etc/5echo/uptimerobot-heartbeat.conf"
STATE_DIR="/var/lib/5echo/uptimerobot-heartbeat"
LOG_FILE="/var/log/uptimerobot-heartbeat.log"  # optional; journald always used

PING_COUNT_DEFAULT=2
PING_TIMEOUT_DEFAULT=2
CURL_TIMEOUT_DEFAULT=6

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Dette må kjøres som root. Bruk: sudo $0 $*" >&2
    exit 1
  fi
}

ensure_paths() {
  mkdir -p "$(dirname "$CONFIG_FILE")"
  mkdir -p "$STATE_DIR"
  touch "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE"
}

log() {
  local msg="$1"
  local line
  line="$(date '+%Y-%m-%d %H:%M:%S') - ${msg}"
  if command -v systemd-cat >/dev/null 2>&1; then
    echo "$line" | systemd-cat -t "$APP_NAME" || true
  fi
  echo "$line" >> "$LOG_FILE" 2>/dev/null || true
}

usage() {
  cat <<EOF
5echo $APP_NAME

Bruk:
  $0 install
  $0 uninstall
  $0 add <name> <ip> <heartbeat_url>
  $0 remove <name>
  $0 list
  $0 run
  $0 enable
  $0 disable
  $0 status

Eksempel:
  sudo $0 install
  sudo $0 add anl-0161-core-gw 10.5.0.1 https://heartbeat.uptimerobot.com/XXXX
  sudo $0 add anl-0161-core-switch 10.5.10.2 https://heartbeat.uptimerobot.com/YYYY
  sudo $0 list
  sudo $0 enable

Config:
  $CONFIG_FILE
EOF
}

validate_name() {
  local name="$1"
  if [[ ! "$name" =~ ^[a-zA-Z0-9._-]+$ ]]; then
    echo "Ugyldig name '$name'. Bruk kun a-zA-Z0-9._-" >&2
    exit 1
  fi
}

validate_ip() {
  local ip="$1"
  if [[ ! "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    echo "Ugyldig IP '$ip'." >&2
    exit 1
  fi
  IFS='.' read -r o1 o2 o3 o4 <<<"$ip"
  for o in "$o1" "$o2" "$o3" "$o4"; do
    if (( o < 0 || o > 255 )); then
      echo "Ugyldig IP '$ip' (octet utenfor 0-255)." >&2
      exit 1
    fi
  done
}

validate_url() {
  local url="$1"
  if [[ ! "$url" =~ ^https?:// ]]; then
    echo "Ugyldig URL '$url'. Må starte med http:// eller https://." >&2
    exit 1
  fi
}

config_has_name() {
  local name="$1"
  grep -qE "^${name}\|" "$CONFIG_FILE"
}

add_target() {
  require_root add
  ensure_paths

  local name="${1:-}"
  local ip="${2:-}"
  local url="${3:-}"

  if [[ -z "$name" || -z "$ip" || -z "$url" ]]; then
    echo "Mangler parametere." >&2
    usage
    exit 1
  fi

  validate_name "$name"
  validate_ip "$ip"
  validate_url "$url"

  if config_has_name "$name"; then
    echo "Finnes allerede: $name. Fjern først med: sudo $0 remove $name" >&2
    exit 1
  fi

  echo "${name}|${ip}|${url}" >> "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE"
  log "ADD target name=$name ip=$ip"
  echo "La til: $name ($ip)"
}

remove_target() {
  require_root remove
  ensure_paths

  local name="${1:-}"
  if [[ -z "$name" ]]; then
    echo "Mangler <name>." >&2
    usage
    exit 1
  fi
  validate_name "$name"

  if ! config_has_name "$name"; then
    echo "Fant ikke: $name" >&2
    exit 1
  fi

  tmp="$(mktemp)"
  grep -vE "^${name}\|" "$CONFIG_FILE" > "$tmp"
  cat "$tmp" > "$CONFIG_FILE"
  rm -f "$tmp"
  chmod 600 "$CONFIG_FILE"

  log "REMOVE target name=$name"
  echo "Fjernet: $name"
}

list_targets() {
  require_root list
  ensure_paths

  if [[ ! -s "$CONFIG_FILE" ]]; then
    echo "Ingen targets i $CONFIG_FILE"
    exit 0
  fi

  echo "Targets:"
  echo "------------------------------------------------------------"
  while IFS='|' read -r name ip url; do
    [[ -z "$name" ]] && continue
    masked="$url"
    masked="$(echo "$masked" | sed -E 's#(https?://[^/]+/).{4,}#\1***#')"
    printf "  - %-24s %-15s %s\n" "$name" "$ip" "$masked"
  done < "$CONFIG_FILE"
  echo "------------------------------------------------------------"
}

ping_ok() {
  local ip="$1"
  local count="${2:-$PING_COUNT_DEFAULT}"
  local timeout="${3:-$PING_TIMEOUT_DEFAULT}"
  ping -c "$count" -W "$timeout" "$ip" > /dev/null 2>&1
}

send_heartbeat() {
  local url="$1"
  local timeout="${2:-$CURL_TIMEOUT_DEFAULT}"
  curl -fsS --max-time "$timeout" "$url" > /dev/null
}

run_checks() {
  require_root run
  ensure_paths

  if [[ ! -s "$CONFIG_FILE" ]]; then
    log "RUN: No targets configured"
    exit 0
  fi

  local total=0 ok=0 fail=0 sent=0 curl_fail=0

  while IFS='|' read -r name ip url; do
    [[ -z "$name" ]] && continue
    total=$((total+1))

    if ping_ok "$ip"; then
      ok=$((ok+1))
      if send_heartbeat "$url"; then
        sent=$((sent+1))
        log "OK   name=$name ip=$ip heartbeat=sent"
      else
        curl_fail=$((curl_fail+1))
        log "WARN name=$name ip=$ip ping=ok heartbeat=FAILED(curl)"
      fi
    else
      fail=$((fail+1))
      log "DOWN name=$name ip=$ip ping=failed heartbeat=not_sent"
    fi
  done < "$CONFIG_FILE"

  log "RUN summary total=$total ping_ok=$ok ping_fail=$fail heartbeat_sent=$sent curl_fail=$curl_fail"
}

install_systemd() {
  require_root install
  ensure_paths

  if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemd ikke tilgjengelig. Bruk cron eller kjør manuelt." >&2
    exit 1
  fi

  local bin_path="/usr/local/bin/${APP_NAME}"
  local service_path="/etc/systemd/system/${APP_NAME}.service"
  local timer_path="/etc/systemd/system/${APP_NAME}.timer"

  cp -f "$0" "$bin_path"
  chmod 755 "$bin_path"

  cat > "$service_path" <<EOF
[Unit]
Description=5echo UpTimeRobot Heartbeat Bridge
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=$bin_path run
User=root
EOF

  cat > "$timer_path" <<EOF
[Unit]
Description=Run 5echo UpTimeRobot Heartbeat Bridge every minute

[Timer]
OnBootSec=30
OnUnitActiveSec=60
AccuracySec=5s
Unit=${APP_NAME}.service

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  echo "Installert:"
  echo "  - $bin_path"
  echo "  - $service_path"
  echo "  - $timer_path"
  echo ""
  echo "Neste steg:"
  echo "  sudo $bin_path enable"
}

uninstall_systemd() {
  require_root uninstall

  local bin_path="/usr/local/bin/${APP_NAME}"
  local service_path="/etc/systemd/system/${APP_NAME}.service"
  local timer_path="/etc/systemd/system/${APP_NAME}.timer"

  if command -v systemctl >/dev/null 2>&1; then
    systemctl disable --now "${APP_NAME}.timer" >/dev/null 2>&1 || true
    rm -f "$service_path" "$timer_path"
    systemctl daemon-reload || true
  fi

  rm -f "$bin_path"
  echo "Avinstallert systemd units + bin: $bin_path"
  echo "Config beholdes: $CONFIG_FILE"
}

enable_timer() {
  require_root enable
  command -v systemctl >/dev/null 2>&1 || { echo "systemd ikke tilgjengelig." >&2; exit 1; }
  systemctl enable --now "${APP_NAME}.timer"
  echo "Aktivert: ${APP_NAME}.timer"
}

disable_timer() {
  require_root disable
  command -v systemctl >/dev/null 2>&1 || { echo "systemd ikke tilgjengelig." >&2; exit 1; }
  systemctl disable --now "${APP_NAME}.timer"
  echo "Deaktivert: ${APP_NAME}.timer"
}

status_timer() {
  require_root status
  if command -v systemctl >/dev/null 2>&1; then
    systemctl status "${APP_NAME}.timer" --no-pager || true
    echo ""
    echo "Siste logs:"
    journalctl -t "$APP_NAME" -n 25 --no-pager || true
  else
    echo "systemd ikke tilgjengelig." >&2
  fi
}

main() {
  local cmd="${1:-}"
  shift || true

  case "$cmd" in
    install) install_systemd ;;
    uninstall) uninstall_systemd ;;
    add) add_target "${1:-}" "${2:-}" "${3:-}" ;;
    remove) remove_target "${1:-}" ;;
    list) list_targets ;;
    run) run_checks ;;
    enable) enable_timer ;;
    disable) disable_timer ;;
    status) status_timer ;;
    ""|help|-h|--help) usage ;;
    *)
      echo "Ukjent kommando: $cmd" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
