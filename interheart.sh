#!/usr/bin/env bash
set -euo pipefail

APP_NAME="interheart"
VERSION="3"

CONFIG_FILE="/etc/5echo/interheart.conf"
STATE_DIR="/var/lib/interheart"
STATE_FILE="${STATE_DIR}/state.json"
LOG_FILE="/var/log/interheart.log"

PING_COUNT_DEFAULT=2
PING_TIMEOUT_DEFAULT=2
CURL_TIMEOUT_DEFAULT=6
DEFAULT_INTERVAL=60

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
  chmod 755 "$STATE_DIR"

  # state file root-owned but readable for webui if you want later (we keep 644)
  if [[ ! -f "$STATE_FILE" ]]; then
    echo '{}' > "$STATE_FILE"
  fi
  chmod 644 "$STATE_FILE"

  # log file readable
  touch "$LOG_FILE" 2>/dev/null || true
  chmod 644 "$LOG_FILE" 2>/dev/null || true
}

now_epoch() {
  date +%s
}

log_line() {
  local msg="$1"
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "${ts} - ${msg}" >> "$LOG_FILE" 2>/dev/null || true
  if command -v systemd-cat >/dev/null 2>&1; then
    echo "${ts} - ${msg}" | systemd-cat -t "$APP_NAME" || true
  fi
}

usage() {
  cat <<EOF
5echo ${APP_NAME} v${VERSION}

Targets:
  $0 add <name> <ip> <endpoint_url> [interval_seconds]
  $0 remove <name>
  $0 list
  $0 set-interval <name> <seconds>
  $0 test <name>

Runtime:
  $0 run
  $0 version

Systemd:
  $0 install
  $0 uninstall
  $0 enable
  $0 disable
  $0 status

Files:
  Config: $CONFIG_FILE
  State:  $STATE_FILE
  Log:    $LOG_FILE

Config format (per line):
  NAME|IP|ENDPOINT_URL|INTERVAL_SECONDS
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
  (( sec >= 5 && sec <= 86400 )) || { echo "Intervall må være mellom 5 og 86400 sek."; exit 1; }
}

config_has_name() {
  local name="$1"
  grep -qE "^${name}\|" "$CONFIG_FILE"
}

mask_url() {
  local url="$1"
  echo "$url" | sed -E 's#(https?://[^/]+/).{4,}#\1***#'
}

# ---- JSON state helpers (no jq dependency; minimal, safe enough) ----
# We store state as:
# {
#   "targets": {
#     "name": {"last_ping": 123, "last_ok": 123, "last_status":"UP/DOWN/ERR", "next_due":123, "last_rtt_ms":12}
#   }
# }
state_read() {
  cat "$STATE_FILE" 2>/dev/null || echo '{}'
}

state_write() {
  local content="$1"
  # atomic write
  local tmp
  tmp="$(mktemp)"
  echo "$content" > "$tmp"
  mv "$tmp" "$STATE_FILE"
  chmod 644 "$STATE_FILE"
}

state_get_field() {
  local name="$1"
  local field="$2"
  # Extract number/string fields with sed; if missing -> empty
  # Note: This is lightweight parsing; we keep JSON simple.
  state_read | sed -nE "s/.*\"${name}\"[^{]*\{[^}]*\"${field}\"[[:space:]]*:[[:space:]]*\"?([^\",}]*)\"?.*/\1/p" | head -n1
}

state_set_target() {
  local name="$1"
  local last_ping="$2"
  local last_ok="$3"
  local last_status="$4"
  local next_due="$5"
  local last_rtt="$6"

  local current
  current="$(state_read)"

  # Ensure "targets" object exists
  if ! echo "$current" | grep -q '"targets"'; then
    current='{"targets":{}}'
  fi

  # Remove existing target entry (if exists)
  local without
  without="$(echo "$current" | sed -E "s/\"${name}\"[[:space:]]*:[[:space:]]*\{[^}]*\},?//g")"

  # Clean up possible trailing commas issues lightly
  without="$(echo "$without" | sed -E 's/,\s*}/}/g; s/\{\s*,/\{ /g')"

  # Insert/replace inside targets
  # Strategy: replace "targets":{ ... } with appended entry (safe-ish)
  local entry
  entry="\"${name}\":{\"last_ping\":${last_ping},\"last_ok\":${last_ok},\"last_status\":\"${last_status}\",\"next_due\":${next_due},\"last_rtt_ms\":${last_rtt}}"

  local updated
  updated="$(echo "$without" | sed -E "s/\"targets\"\s*:\s*\{/\0${entry},/")"
  updated="$(echo "$updated" | sed -E 's/\{("targets":\{)([^}]*)\}\}/\{\1\2\}\}/')"
  updated="$(echo "$updated" | sed -E 's/,\s*}/}/g')"

  state_write "$updated"
}

# ---- core actions ----
ping_rtt_ms() {
  # returns rtt in ms if possible, else empty
  # works on typical ping output with 'time='
  local ip="$1"
  ping -c 1 -W "$PING_TIMEOUT_DEFAULT" "$ip" 2>/dev/null | sed -nE 's/.*time=([0-9.]+).*/\1/p' | head -n1
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
  local interval="${4:-$DEFAULT_INTERVAL}"

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
  log_line "ADD name=$name ip=$ip interval=${interval}s"
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
  grep -vE "^${name}\|" "$CONFIG_FILE" > "$tmp"
  cat "$tmp" > "$CONFIG_FILE"
  rm -f "$tmp"
  chmod 600 "$CONFIG_FILE"

  log_line "REMOVE name=$name"
  echo "Fjernet: $name"
}

set_target_interval() {
  require_root set-interval
  ensure_paths

  local name="${1:-}"
  local sec="${2:-}"
  [[ -z "$name" || -z "$sec" ]] && { echo "Bruk: sudo $0 set-interval <name> <seconds>"; exit 1; }
  validate_name "$name"
  validate_interval "$sec"

  if ! config_has_name "$name"; then
    echo "Fant ikke: $name" >&2
    exit 1
  fi

  local tmp
  tmp="$(mktemp)"
  while IFS='|' read -r n ip url interval; do
    [[ -z "${n:-}" ]] && continue
    if [[ "$n" == "$name" ]]; then
      echo "${n}|${ip}|${url}|${sec}" >> "$tmp"
    else
      # keep original interval or default if missing
      if [[ -z "${interval:-}" ]]; then interval="$DEFAULT_INTERVAL"; fi
      echo "${n}|${ip}|${url}|${interval}" >> "$tmp"
    fi
  done < "$CONFIG_FILE"

  cat "$tmp" > "$CONFIG_FILE"
  rm -f "$tmp"
  chmod 600 "$CONFIG_FILE"

  log_line "SET_INTERVAL name=$name interval=${sec}s"
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
  while IFS='|' read -r name ip url interval; do
    [[ -z "${name:-}" ]] && continue
    if [[ -z "${interval:-}" ]]; then interval="$DEFAULT_INTERVAL"; fi
    printf "  %-26s %-15s %-10s %s\n" "$name" "$ip" "${interval}s" "$(mask_url "$url")"
  done < "$CONFIG_FILE"
  echo "--------------------------------------------------------------------------------"
}

test_target() {
  require_root test
  ensure_paths

  local name="${1:-}"
  [[ -z "$name" ]] && { usage; exit 1; }
  validate_name "$name"

  local line
  line="$(grep -E "^${name}\|" "$CONFIG_FILE" || true)"
  [[ -z "$line" ]] && { echo "Fant ikke: $name"; exit 1; }

  IFS='|' read -r _name ip url interval <<<"$line"
  interval="${interval:-$DEFAULT_INTERVAL}"

  echo "Tester: $name ($ip) interval=${interval}s"
  local rtt
  rtt="$(ping_rtt_ms "$ip" || true)"

  if ping_ok "$ip"; then
    echo "PING: OK (rtt=${rtt}ms)"
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

  [[ ! -s "$CONFIG_FILE" ]] && { log_line "RUN: no targets"; echo "No targets"; exit 0; }

  local now
  now="$(now_epoch)"

  local total=0 due=0 ping_ok_count=0 ping_fail=0 sent=0 curl_fail=0 skipped=0

  while IFS='|' read -r name ip url interval; do
    [[ -z "${name:-}" ]] && continue
    total=$((total+1))

    interval="${interval:-$DEFAULT_INTERVAL}"

    local next_due
    next_due="$(state_get_field "$name" "next_due" || true)"
    if [[ -z "${next_due:-}" ]]; then
      next_due=0
    fi

    if (( now < next_due )); then
      skipped=$((skipped+1))
      continue
    fi

    due=$((due+1))

    # Mark ping start in state (status=Pinging)
    state_set_target "$name" "$now" "$(state_get_field "$name" "last_ok" || echo 0)" "PINGING" "$((now + interval))" 0

    local rtt
    rtt="$(ping_rtt_ms "$ip" || true)"
    rtt="${rtt:-0}"

    if ping_ok "$ip"; then
      ping_ok_count=$((ping_ok_count+1))
      if send_endpoint "$url"; then
        sent=$((sent+1))
        state_set_target "$name" "$now" "$now" "UP" "$((now + interval))" "$rtt"
        log_line "PING OK   name=$name ip=$ip rtt=${rtt}ms endpoint=SENT next_in=${interval}s"
      else
        curl_fail=$((curl_fail+1))
        state_set_target "$name" "$now" "$(state_get_field "$name" "last_ok" || echo 0)" "ERR" "$((now + interval))" "$rtt"
        log_line "PING OK   name=$name ip=$ip rtt=${rtt}ms endpoint=FAILED next_in=${interval}s"
      fi
    else
      ping_fail=$((ping_fail+1))
      state_set_target "$name" "$now" "$(state_get_field "$name" "last_ok" || echo 0)" "DOWN" "$((now + interval))" "$rtt"
      log_line "PING FAIL name=$name ip=$ip rtt=${rtt}ms endpoint=NOT_SENT next_in=${interval}s"
    fi

  done < "$CONFIG_FILE"

  log_line "RUN summary total=$total due=$due skipped=$skipped ping_ok=$ping_ok_count ping_fail=$ping_fail sent=$sent curl_fail=$curl_fail"
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

  # Fixed small cadence; per-target intervals are handled inside run
  cat > "$TIMER_PATH" <<EOF
[Unit]
Description=Run interheart scheduler (checks due targets)

[Timer]
OnBootSec=15
OnUnitActiveSec=5
AccuracySec=1s
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

main() {
  cmd="${1:-}"
  shift || true

  case "$cmd" in
    add) add_target "${1:-}" "${2:-}" "${3:-}" "${4:-$DEFAULT_INTERVAL}" ;;
    remove) remove_target "${1:-}" ;;
    list) list_targets ;;
    set-interval) set_target_interval "${1:-}" "${2:-}" ;;
    run) run_checks ;;
    test) test_target "${1:-}" ;;
    install) install_systemd ;;
    uninstall) uninstall_systemd ;;
    enable) enable_timer ;;
    disable) disable_timer ;;
    status) status_timer ;;
    version) echo "$VERSION" ;;
    ""|help|-h|--help) usage ;;
    *) echo "Ukjent kommando: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
