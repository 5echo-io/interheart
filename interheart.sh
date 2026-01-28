#!/usr/bin/env bash
set -euo pipefail

APP_NAME="interheart"
CONFIG_FILE="/etc/5echo/interheart.conf"
LOG_FILE="/var/log/interheart.log"

PING_COUNT_DEFAULT=2
PING_TIMEOUT_DEFAULT=2
CURL_TIMEOUT_DEFAULT=6

BIN_PATH="/usr/local/bin/${APP_NAME}"
SERVICE_PATH="/etc/systemd/system/${APP_NAME}.service"
TIMER_PATH="/etc/systemd/system/${APP_NAME}.timer"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Dette må kjøres som root. Bruk: sudo $0 $*" >&2
    exit 1
  fi
}

ensure_paths() {
  mkdir -p "$(dirname "$CONFIG_FILE")"
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

Targets:
  $0 add <name> <ip> <endpoint_url>
  $0 remove <name>
  $0 list
  $0 test <name>

Runtime:
  $0 run

Schedule:
  $0 get-interval
  $0 set-interval <seconds>

Systemd:
  $0 install
  $0 uninstall
  $0 enable
  $0 disable
  $0 status

Config:
  $CONFIG_FILE
Format:
  NAME|IP|ENDPOINT_URL
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

  [[ -z "$name" || -z "$ip" || -z "$url" ]] && { usage; exit 1; }

  validate_name "$name"
  validate_ip "$ip"
  validate_url "$url"

  if config_has_name "$name"; then
    echo "Finnes allerede: $name. Fjern først med: sudo $0 remove $name" >&2
    exit 1
  fi

  echo "${name}|${ip}|${url}" >> "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE"
  log "ADD name=$name ip=$ip"
  echo "La til: $name ($ip)"
}

remove_target() {
  require_root remove
  ensure_paths

  local name="${1:-}"
  [[ -z "$name" ]] && { usage; exit 1; }
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

  log "REMOVE name=$name"
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
    [[ -z "${name:-}" ]] && continue
    masked="$(echo "$url" | sed -E 's#(https?://[^/]+/).{4,}#\1***#')"
    printf "  - %-26s %-15s %s\n" "$name" "$ip" "$masked"
  done < "$CONFIG_FILE"
  echo "------------------------------------------------------------"
}

ping_ok() {
  local ip="$1"
  ping -c "$PING_COUNT_DEFAULT" -W "$PING_TIMEOUT_DEFAULT" "$ip" > /dev/null 2>&1
}

send_endpoint() {
  local url="$1"
  curl -fsS --max-time "$CURL_TIMEOUT_DEFAULT" "$url" > /dev/null
}

run_checks() {
  require_root run
  ensure_paths

  [[ ! -s "$CONFIG_FILE" ]] && { log "RUN: no targets"; echo "No targets"; exit 0; }

  local total=0 ping_ok_count=0 ping_fail=0 sent=0 curl_fail=0

  while IFS='|' read -r name ip url; do
    [[ -z "${name:-}" ]] && continue
    total=$((total+1))

    if ping_ok "$ip"; then
      ping_ok_count=$((ping_ok_count+1))
      if send_endpoint "$url"; then
        sent=$((sent+1))
        log "OK   name=$name ip=$ip endpoint=sent"
      else
        curl_fail=$((curl_fail+1))
        log "WARN name=$name ip=$ip ping=ok endpoint=FAILED(curl)"
      fi
    else
      ping_fail=$((ping_fail+1))
      log "DOWN name=$name ip=$ip ping=failed endpoint=not_sent"
    fi
  done < "$CONFIG_FILE"

  log "RUN summary total=$total ping_ok=$ping_ok_count ping_fail=$ping_fail sent=$sent curl_fail=$curl_fail"
  echo "OK: total=$total ping_ok=$ping_ok_count ping_fail=$ping_fail sent=$sent curl_fail=$curl_fail"
}

test_target() {
  require_root test
  ensure_paths

  local name="${1:-}"
  [[ -z "$name" ]] && { usage; exit 1; }
  validate_name "$name"

  line="$(grep -E "^${name}\|" "$CONFIG_FILE" || true)"
  [[ -z "$line" ]] && { echo "Fant ikke: $name"; exit 1; }

  IFS='|' read -r _name ip url <<<"$line"

  echo "Tester: $name ($ip)"
  if ping_ok "$ip"; then
    echo "PING: OK"
    echo "Sender til endpoint…"
    if send_endpoint "$url"; then
      echo "ENDPOINT: OK"
      exit 0
    else
      echo "ENDPOINT: FEIL (curl)"
      exit 2
    fi
  else
    echo "PING: FEIL"
    exit 3
  fi
}

install_systemd() {
  require_root install
  ensure_paths
  command -v systemctl >/dev/null 2>&1 || { echo "systemd ikke tilgjengelig"; exit 1; }

  cp -f "$0" "$BIN_PATH"
  chmod 755 "$BIN_PATH"

  cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=5echo interheart - ping -> endpoint relay
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=$BIN_PATH run
User=root
EOF

  cat > "$TIMER_PATH" <<EOF
[Unit]
Description=Run interheart every 60 seconds

[Timer]
OnBootSec=30
OnUnitActiveSec=60
AccuracySec=5s
Unit=${APP_NAME}.service

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  echo "Installert systemd: $APP_NAME.service + $APP_NAME.timer"
  echo "Neste: sudo $BIN_PATH enable"
}

uninstall_systemd() {
  require_root uninstall
  if command -v systemctl >/dev/null 2>&1; then
    systemctl disable --now "${APP_NAME}.timer" >/dev/null 2>&1 || true
    rm -f "$SERVICE_PATH" "$TIMER_PATH"
    systemctl daemon-reload || true
  fi
  rm -f "$BIN_PATH"
  echo "Avinstallert. Config beholdes: $CONFIG_FILE"
}

enable_timer() {
  require_root enable
  systemctl enable --now "${APP_NAME}.timer"
  echo "Aktivert: ${APP_NAME}.timer"
}

disable_timer() {
  require_root disable
  systemctl disable --now "${APP_NAME}.timer"
  echo "Deaktivert: ${APP_NAME}.timer"
}

status_timer() {
  require_root status
  systemctl status "${APP_NAME}.timer" --no-pager || true
  echo ""
  journalctl -t "$APP_NAME" -n 25 --no-pager || true
}

get_interval() {
  require_root get-interval
  if [[ ! -f "$TIMER_PATH" ]]; then
    echo "Timer finnes ikke. Kjør: sudo $0 install"
    exit 1
  fi
  val="$(grep -E '^OnUnitActiveSec=' "$TIMER_PATH" | head -n1 | cut -d'=' -f2 || true)"
  echo "${val:-unknown}"
}

set_interval() {
  require_root set-interval
  local sec="${1:-}"
  [[ -z "$sec" ]] && { echo "Bruk: sudo $0 set-interval <seconds>"; exit 1; }
  [[ "$sec" =~ ^[0-9]+$ ]] || { echo "Må være heltall sekunder."; exit 1; }
  (( sec >= 10 && sec <= 3600 )) || { echo "Velg mellom 10 og 3600 sek."; exit 1; }

  if [[ ! -f "$TIMER_PATH" ]]; then
    echo "Timer finnes ikke. Kjør: sudo $0 install"
    exit 1
  fi

  sed -i -E "s/^Description=.*/Description=Run interheart every ${sec} seconds/" "$TIMER_PATH"
  if grep -qE '^OnUnitActiveSec=' "$TIMER_PATH"; then
    sed -i -E "s/^OnUnitActiveSec=.*/OnUnitActiveSec=${sec}/" "$TIMER_PATH"
  else
    sed -i -E "/^\[Timer\]/a OnUnitActiveSec=${sec}" "$TIMER_PATH"
  fi

  systemctl daemon-reload
  systemctl restart "${APP_NAME}.timer"
  echo "Intervall satt til ${sec}s"
}

main() {
  cmd="${1:-}"
  shift || true

  case "$cmd" in
    add) add_target "${1:-}" "${2:-}" "${3:-}" ;;
    remove) remove_target "${1:-}" ;;
    list) list_targets ;;
    run) run_checks ;;
    test) test_target "${1:-}" ;;
    install) install_systemd ;;
    uninstall) uninstall_systemd ;;
    enable) enable_timer ;;
    disable) disable_timer ;;
    status) status_timer ;;
    get-interval) get_interval ;;
    set-interval) set_interval "${1:-}" ;;
    ""|help|-h|--help) usage ;;
    *) echo "Ukjent kommando: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
