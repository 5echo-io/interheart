#!/usr/bin/env bash
set -euo pipefail

APP_NAME="interheart"

CONFIG_FILE="/etc/5echo/interheart.conf"
LOG_FILE="/var/log/interheart.log"
STATE_DIR="/var/lib/interheart"
STATE_FILE="${STATE_DIR}/state.db"

# Defaults
DEFAULT_INTERVAL_SEC=60
RUNNER_DEFAULT_SEC=10   # how often systemd timer triggers
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

  mkdir -p "$STATE_DIR"
  chmod 700 "$STATE_DIR"
  touch "$STATE_FILE"
  chmod 600 "$STATE_FILE"
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

Config format:
  NAME|IP|ENDPOINT_URL|INTERVAL_SEC

Backwards compatible:
  NAME|IP|ENDPOINT_URL              (interval defaults to ${DEFAULT_INTERVAL_SEC})

Targets:
  $0 add <name> <ip> <endpoint_url> [interval_sec]
  $0 remove <name>
  $0 list
  $0 test <name>
  $0 set-target-interval <name> <seconds>

Runtime:
  $0 run
  $0 status         (prints state for all targets)

Systemd:
  $0 install
  $0 uninstall
  $0 enable
  $0 disable
  $0 sys-status

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

validate_interval() {
  local sec="$1"
  [[ "$sec" =~ ^[0-9]+$ ]] || { echo "Intervall må være heltall sekunder."; exit 1; }
  (( sec >= 10 && sec <= 86400 )) || { echo "Intervall må være mellom 10 og 86400 sek."; exit 1; }
}

config_has_name() {
  local name="$1"
  grep -qE "^${name}\|" "$CONFIG_FILE"
}

parse_config_line() {
  local line="$1"
  local name ip url interval
  IFS='|' read -r name ip url interval <<<"$line"
  interval="${interval:-$DEFAULT_INTERVAL_SEC}"
  echo "${name}|${ip}|${url}|${interval}"
}

# State db format:
# NAME|NEXT_DUE_EPOCH|LAST_STATUS|LAST_PING_EPOCH|LAST_SENT_EPOCH
state_get_line() {
  local name="$1"
  grep -E "^${name}\|" "$STATE_FILE" || true
}

state_set_line() {
  local newline="$1"
  local name
  IFS='|' read -r name _ <<<"$newline"

  local tmp
  tmp="$(mktemp)"
  grep -vE "^${name}\|" "$STATE_FILE" > "$tmp" || true
  echo "$newline" >> "$tmp"
  cat "$tmp" > "$STATE_FILE"
  rm -f "$tmp"
  chmod 600 "$STATE_FILE"
}

mask_url() {
  local url="$1"
  echo "$url" | sed -E 's#(https?://[^/]+/).{4,}#\1***#'
}

ping_ok() {
  local ip="$1"
  ping -c "$PING_COUNT_DEFAULT" -W "$PING_TIMEOUT_DEFAULT" "$ip" > /dev/null 2>&1
}

send_endpoint() {
  local url="$1"
  curl -fsS --max-time "$CURL_TIMEOUT_DEFAULT" "$url" > /dev/null
}

add_target() {
  require_root add
  ensure_paths

  local name="${1:-}"
  local ip="${2:-}"
  local url="${3:-}"
  local interval="${4:-$DEFAULT_INTERVAL_SEC}"

  [[ -z "$name" || -z "$ip" || -z "$url" ]] && { usage; exit 1; }

  validate_name "$name"
  validate_ip "$ip"
  validate_url "$url"
  validate_interval "$interval"

  if config_has_name "$name"; then
    echo "Finnes allerede: $name. Fjern først med: sudo $0 remove $name" >&2
    exit 1
  fi

  echo "${name}|${ip}|${url}|${interval}" >> "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE"

  local now
  now="$(date +%s)"
  state_set_line "${name}|${now}|unknown|0|0"

  log "ADD name=$name ip=$ip interval=${interval}s"
  echo "La til: $name ($ip) interval=${interval}s"
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

  local tmp
  tmp="$(mktemp)"
  grep -vE "^${name}\|" "$CONFIG_FILE" > "$tmp" || true
  cat "$tmp" > "$CONFIG_FILE"
  rm -f "$tmp"
  chmod 600 "$CONFIG_FILE"

  tmp="$(mktemp)"
  grep -vE "^${name}\|" "$STATE_FILE" > "$tmp" || true
  cat "$tmp" > "$STATE_FILE"
  rm -f "$tmp"
  chmod 600 "$STATE_FILE"

  log "REMOVE name=$name"
  echo "Fjernet: $name"
}

set_target_interval() {
  require_root set-target-interval
  ensure_paths

  local name="${1:-}"
  local sec="${2:-}"
  [[ -z "$name" || -z "$sec" ]] && { echo "Bruk: sudo $0 set-target-interval <name> <seconds>"; exit 1; }
  validate_name "$name"
  validate_interval "$sec"

  if ! config_has_name "$name"; then
    echo "Fant ikke: $name" >&2
    exit 1
  fi

  local tmp
  tmp="$(mktemp)"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && { echo "$line" >> "$tmp"; continue; }

    parsed="$(parse_config_line "$line")"
    IFS='|' read -r n ip url interval <<<"$parsed"

    if [[ "$n" == "$name" ]]; then
      echo "${n}|${ip}|${url}|${sec}" >> "$tmp"
    else
      echo "${n}|${ip}|${url}|${interval}" >> "$tmp"
    fi
  done < "$CONFIG_FILE"

  cat "$tmp" > "$CONFIG_FILE"
  rm -f "$tmp"
  chmod 600 "$CONFIG_FILE"

  local now
  now="$(date +%s)"
  local old
  old="$(state_get_line "$name")"
  if [[ -n "$old" ]]; then
    IFS='|' read -r _n _due last_status last_ping last_sent <<<"$old"
    state_set_line "${name}|${now}|${last_status:-unknown}|${last_ping:-0}|${last_sent:-0}"
  else
    state_set_line "${name}|${now}|unknown|0|0"
  fi

  log "SET_INTERVAL name=$name interval=${sec}s"
  echo "Oppdatert: $name interval=${sec}s"
}

list_targets() {
  require_root list
  ensure_paths

  if [[ ! -s "$CONFIG_FILE" ]]; then
    echo "Ingen targets i $CONFIG_FILE"
    exit 0
  fi

  echo "Targets:"
  echo "--------------------------------------------------------------------------------"
  printf "  %-26s %-15s %-10s %s\n" "NAME" "IP" "INTERVAL" "ENDPOINT"
  echo "--------------------------------------------------------------------------------"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && continue

    parsed="$(parse_config_line "$line")"
    IFS='|' read -r name ip url interval <<<"$parsed"

    printf "  %-26s %-15s %-10s %s\n" "$name" "$ip" "${interval}s" "$(mask_url "$url")"
  done < "$CONFIG_FILE"
  echo "--------------------------------------------------------------------------------"
}

status_targets() {
  require_root status
  ensure_paths

  local now
  now="$(date +%s)"

  echo "State:"
  echo "--------------------------------------------------------------------------------------------------------------"
  printf "  %-26s %-10s %-12s %-14s %-14s %-14s\n" "NAME" "STATUS" "NEXT_IN" "NEXT_DUE" "LAST_PING" "LAST_SENT"
  echo "--------------------------------------------------------------------------------------------------------------"

  # Build a map of config names to keep output aligned with configured targets
  if [[ ! -s "$CONFIG_FILE" ]]; then
    echo "  (ingen targets)"
    exit 0
  fi

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && continue

    parsed="$(parse_config_line "$line")"
    IFS='|' read -r name _ip _url _interval <<<"$parsed"

    st="$(state_get_line "$name")"
    local next_due last_status last_ping last_sent
    if [[ -n "$st" ]]; then
      IFS='|' read -r _n next_due last_status last_ping last_sent <<<"$st"
    else
      next_due="0"
      last_status="unknown"
      last_ping="0"
      last_sent="0"
    fi

    next_due="${next_due:-0}"
    last_status="${last_status:-unknown}"
    last_ping="${last_ping:-0}"
    last_sent="${last_sent:-0}"

    local next_in
    if (( next_due <= 0 )); then
      next_in="due"
    else
      local diff=$(( next_due - now ))
      if (( diff <= 0 )); then
        next_in="due"
      else
        next_in="${diff}s"
      fi
    fi

    printf "  %-26s %-10s %-12s %-14s %-14s %-14s\n" \
      "$name" "$last_status" "$next_in" "$next_due" "$last_ping" "$last_sent"
  done < "$CONFIG_FILE"

  echo "--------------------------------------------------------------------------------------------------------------"
}

test_target() {
  require_root test
  ensure_paths

  local name="${1:-}"
  [[ -z "$name" ]] && { usage; exit 1; }
  validate_name "$name"

  line="$(grep -E "^${name}\|" "$CONFIG_FILE" || true)"
  [[ -z "$line" ]] && { echo "Fant ikke: $name"; exit 1; }

  parsed="$(parse_config_line "$line")"
  IFS='|' read -r _name ip url interval <<<"$parsed"

  echo "Tester: $name ($ip) interval=${interval}s"
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

run_checks() {
  require_root run
  ensure_paths

  [[ ! -s "$CONFIG_FILE" ]] && { log "RUN: no targets"; echo "No targets"; exit 0; }

  local now
  now="$(date +%s)"

  local total=0 due=0 skipped=0 ping_ok_count=0 ping_fail=0 sent=0 curl_fail=0

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && continue

    total=$((total+1))

    parsed="$(parse_config_line "$line")"
    IFS='|' read -r name ip url interval <<<"$parsed"

    st="$(state_get_line "$name")"
    local next_due last_status last_ping last_sent
    if [[ -n "$st" ]]; then
      IFS='|' read -r _n next_due last_status last_ping last_sent <<<"$st"
      next_due="${next_due:-0}"
    else
      next_due="0"
      last_status="unknown"
      last_ping="0"
      last_sent="0"
    fi

    if (( now < next_due )); then
      skipped=$((skipped+1))
      continue
    fi

    due=$((due+1))

    if ping_ok "$ip"; then
      ping_ok_count=$((ping_ok_count+1))
      last_status="up"
      last_ping="$now"

      if send_endpoint "$url"; then
        sent=$((sent+1))
        last_sent="$now"
        log "OK   name=$name ip=$ip interval=${interval}s endpoint=sent"
      else
        curl_fail=$((curl_fail+1))
        log "WARN name=$name ip=$ip interval=${interval}s ping=ok endpoint=FAILED(curl)"
      fi
    else
      ping_fail=$((ping_fail+1))
      last_status="down"
      last_ping="$now"
      log "DOWN name=$name ip=$ip interval=${interval}s ping=failed endpoint=not_sent"
    fi

    next_due=$(( now + interval ))
    state_set_line "${name}|${next_due}|${last_status}|${last_ping}|${last_sent}"
  done < "$CONFIG_FILE"

  log "RUN summary total=$total due=$due skipped=$skipped ping_ok=$ping_ok_count ping_fail=$ping_fail sent=$sent curl_fail=$curl_fail"
  echo "OK: total=$total due=$due skipped=$skipped ping_ok=$ping_ok_count ping_fail=$ping_fail sent=$sent curl_fail=$curl_fail"
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
Description=Run interheart every ${RUNNER_DEFAULT_SEC} seconds

[Timer]
OnBootSec=20
OnUnitActiveSec=${RUNNER_DEFAULT_SEC}
AccuracySec=2s
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

sys_status() {
  require_root sys-status
  systemctl status "${APP_NAME}.timer" --no-pager || true
  echo ""
  journalctl -t "$APP_NAME" -n 25 --no-pager || true
}

main() {
  cmd="${1:-}"
  shift || true

  case "$cmd" in
    add) add_target "${1:-}" "${2:-}" "${3:-}" "${4:-$DEFAULT_INTERVAL_SEC}" ;;
    remove) remove_target "${1:-}" ;;
    list) list_targets ;;
    run) run_checks ;;
    test) test_target "${1:-}" ;;
    set-target-interval) set_target_interval "${1:-}" "${2:-}" ;;
    status) status_targets ;;
    install) install_systemd ;;
    uninstall) uninstall_systemd ;;
    enable) enable_timer ;;
    disable) disable_timer ;;
    sys-status) sys_status ;;
    ""|help|-h|--help) usage ;;
    *) echo "Ukjent kommando: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
