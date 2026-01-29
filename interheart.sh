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
PING_COUNT_DEFAULT=1
PING_TIMEOUT_DEFAULT=2
CURL_TIMEOUT_DEFAULT=6

BIN_PATH="/usr/local/bin/${APP_NAME}"
SERVICE_PATH="/etc/systemd/system/${APP_NAME}.service"
TIMER_PATH="/etc/systemd/system/${APP_NAME}.timer"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "This must be run as root. Use: sudo $0 $*" >&2
    exit 1
  fi
}

ensure_paths() {
  mkdir -p "$(dirname "$CONFIG_FILE")"
  touch "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE"

  mkdir -p "$STATE_DIR"
  chmod 755 "$STATE_DIR"
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
5echo ${APP_NAME}

Config format (v4.7+):
  NAME|IP|ENDPOINT_URL|INTERVAL_SEC|ENABLED

Backwards compatible:
  NAME|IP|ENDPOINT_URL|INTERVAL_SEC          (enabled defaults to 1)
  NAME|IP|ENDPOINT_URL                       (interval defaults to ${DEFAULT_INTERVAL_SEC}, enabled=1)

Commands:

Targets:
  $0 add <name> <ip> <endpoint_url> [interval_sec]
  $0 remove <name>
  $0 list
  $0 test <name>
  $0 set-target-interval <name> <seconds>
  $0 disable <name>
  $0 enable-target <name>
  $0 disable-selected <name1,name2,...>
  $0 enable-selected <name1,name2,...>

Runtime:
  $0 run                         (respects schedule + enabled state)
  $0 run-now [--targets a,b,c]    (force run now; skips disabled unless selected)
  $0 status                      (prints state for all targets)

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
    echo "Invalid name '$name'. Use only a-zA-Z0-9._-" >&2
    exit 1
  fi
}

validate_ip() {
  local ip="$1"
  if [[ ! "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    echo "Invalid IP '$ip'." >&2
    exit 1
  fi
  IFS='.' read -r o1 o2 o3 o4 <<<"$ip"
  for o in "$o1" "$o2" "$o3" "$o4"; do
    if (( o < 0 || o > 255 )); then
      echo "Invalid IP '$ip' (octet out of 0-255)." >&2
      exit 1
    fi
  done
}

validate_url() {
  local url="$1"
  if [[ ! "$url" =~ ^https?:// ]]; then
    echo "Invalid URL '$url'. Must start with http:// or https://." >&2
    exit 1
  fi
}

validate_interval() {
  local sec="$1"
  [[ "$sec" =~ ^[0-9]+$ ]] || { echo "Interval must be integer seconds."; exit 1; }
  (( sec >= 10 && sec <= 86400 )) || { echo "Interval must be between 10 and 86400 seconds."; exit 1; }
}

config_has_name() {
  local name="$1"
  grep -qE "^${name}\|" "$CONFIG_FILE"
}

# Parse config with backwards compatibility.
# Returns: name|ip|url|interval|enabled
parse_config_line() {
  local line="$1"
  local name ip url interval enabled
  IFS='|' read -r name ip url interval enabled <<<"$line"
  interval="${interval:-$DEFAULT_INTERVAL_SEC}"
  enabled="${enabled:-1}"
  if [[ "$enabled" != "0" && "$enabled" != "1" ]]; then
    enabled="1"
  fi
  echo "${name}|${ip}|${url}|${interval}|${enabled}"
}

# State db format (v4.7+):
# NAME|NEXT_DUE_EPOCH|LAST_STATUS|LAST_PING_EPOCH|LAST_SENT_EPOCH|LAST_RTT_MS
# Backwards compatible reading (missing LAST_RTT_MS -> -1)
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

# Ping and extract latency in ms (rounded int). Returns:
#  - echoes "OK|<ms>" on success
#  - echoes "FAIL|-1" on failure
ping_latency() {
  local ip="$1"
  local out
  if out="$(ping -c "${PING_COUNT_DEFAULT}" -W "${PING_TIMEOUT_DEFAULT}" "$ip" 2>/dev/null)"; then
    local ms
    ms="$(echo "$out" | grep -oE 'time=[0-9.]+' | head -n1 | cut -d= -f2 || true)"
    if [[ -n "$ms" ]]; then
      # round
      local ms_int
      ms_int="$(python3 - <<PY 2>/dev/null || echo ""
import math
try:
  v=float("${ms}")
  print(int(round(v)))
except:
  pass
PY
)"
      ms_int="${ms_int:-0}"
      echo "OK|${ms_int}"
      return 0
    fi
    echo "OK|0"
    return 0
  fi
  echo "FAIL|-1"
  return 1
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
    echo "Already exists: $name. Remove first: sudo $0 remove $name" >&2
    exit 1
  fi

  echo "${name}|${ip}|${url}|${interval}|1" >> "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE"

  local now
  now="$(date +%s)"
  state_set_line "${name}|${now}|unknown|0|0|-1"

  log "ADD name=$name ip=$ip interval=${interval}s enabled=1"
  echo "Added: $name ($ip) interval=${interval}s"
}

remove_target() {
  require_root remove
  ensure_paths

  local name="${1:-}"
  [[ -z "$name" ]] && { usage; exit 1; }
  validate_name "$name"

  if ! config_has_name "$name"; then
    echo "Not found: $name" >&2
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
  echo "Removed: $name"
}

set_target_interval() {
  require_root set-target-interval
  ensure_paths

  local name="${1:-}"
  local sec="${2:-}"
  [[ -z "$name" || -z "$sec" ]] && { echo "Use: sudo $0 set-target-interval <name> <seconds>"; exit 1; }
  validate_name "$name"
  validate_interval "$sec"

  if ! config_has_name "$name"; then
    echo "Not found: $name" >&2
    exit 1
  fi

  local tmp
  tmp="$(mktemp)"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && { echo "$line" >> "$tmp"; continue; }

    parsed="$(parse_config_line "$line")"
    IFS='|' read -r n ip url interval enabled <<<"$parsed"

    if [[ "$n" == "$name" ]]; then
      echo "${n}|${ip}|${url}|${sec}|${enabled}" >> "$tmp"
    else
      echo "${n}|${ip}|${url}|${interval}|${enabled}" >> "$tmp"
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
    IFS='|' read -r _n _due last_status last_ping last_sent last_rtt <<<"$old"
    last_rtt="${last_rtt:--1}"
    state_set_line "${name}|${now}|${last_status:-unknown}|${last_ping:-0}|${last_sent:-0}|${last_rtt}"
  else
    state_set_line "${name}|${now}|unknown|0|0|-1"
  fi

  log "SET_INTERVAL name=$name interval=${sec}s"
  echo "Updated: $name interval=${sec}s"
}

set_target_enabled() {
  require_root set-enabled
  ensure_paths
  local name="${1:-}"
  local enabled="${2:-}"
  [[ -z "$name" || -z "$enabled" ]] && { echo "Use: sudo $0 disable <name> or sudo $0 enable-target <name>"; exit 1; }
  validate_name "$name"
  [[ "$enabled" == "0" || "$enabled" == "1" ]] || { echo "enabled must be 0/1"; exit 1; }

  if ! config_has_name "$name"; then
    echo "Not found: $name" >&2
    exit 1
  fi

  local tmp
  tmp="$(mktemp)"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && { echo "$line" >> "$tmp"; continue; }

    parsed="$(parse_config_line "$line")"
    IFS='|' read -r n ip url interval en <<<"$parsed"

    if [[ "$n" == "$name" ]]; then
      echo "${n}|${ip}|${url}|${interval}|${enabled}" >> "$tmp"
    else
      echo "${n}|${ip}|${url}|${interval}|${en}" >> "$tmp"
    fi
  done < "$CONFIG_FILE"

  cat "$tmp" > "$CONFIG_FILE"
  rm -f "$tmp"
  chmod 600 "$CONFIG_FILE"

  log "SET_ENABLED name=$name enabled=$enabled"
  echo "Updated: $name enabled=$enabled"
}

disable_target() { set_target_enabled "${1:-}" "0"; }
enable_target()  { set_target_enabled "${1:-}" "1"; }

disable_selected() {
  require_root disable-selected
  ensure_paths
  local list="${1:-}"
  [[ -z "$list" ]] && { echo "Use: sudo $0 disable-selected name1,name2"; exit 1; }
  IFS=',' read -r -a names <<<"$list"
  for n in "${names[@]}"; do
    [[ -z "$n" ]] && continue
    disable_target "$n" || true
  done
  echo "Disabled selected"
}

enable_selected() {
  require_root enable-selected
  ensure_paths
  local list="${1:-}"
  [[ -z "$list" ]] && { echo "Use: sudo $0 enable-selected name1,name2"; exit 1; }
  IFS=',' read -r -a names <<<"$list"
  for n in "${names[@]}"; do
    [[ -z "$n" ]] && continue
    enable_target "$n" || true
  done
  echo "Enabled selected"
}

list_targets() {
  require_root list
  ensure_paths

  if [[ ! -s "$CONFIG_FILE" ]]; then
    echo "No targets in $CONFIG_FILE"
    exit 0
  fi

  echo "Targets:"
  echo "--------------------------------------------------------------------------------"
  printf "  %-26s %-15s %-10s %-9s %s\n" "NAME" "IP" "INTERVAL" "ENABLED" "ENDPOINT"
  echo "--------------------------------------------------------------------------------"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && continue

    parsed="$(parse_config_line "$line")"
    IFS='|' read -r name ip url interval enabled <<<"$parsed"

    printf "  %-26s %-15s %-10s %-9s %s\n" "$name" "$ip" "${interval}s" "${enabled}" "$(mask_url "$url")"
  done < "$CONFIG_FILE"
  echo "--------------------------------------------------------------------------------"
}

status_targets() {
  require_root status
  ensure_paths

  local now
  now="$(date +%s)"

  echo "State:"
  echo "----------------------------------------------------------------------------------------------------------------------------"
  printf "  %-26s %-10s %-12s %-14s %-14s %-14s %-10s\n" "NAME" "STATUS" "NEXT_IN" "NEXT_DUE" "LAST_PING" "LAST_RESP" "LAT(ms)"
  echo "----------------------------------------------------------------------------------------------------------------------------"

  [[ ! -s "$CONFIG_FILE" ]] && { echo "  (no targets)"; exit 0; }

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && continue

    parsed="$(parse_config_line "$line")"
    IFS='|' read -r name _ip _url _interval enabled <<<"$parsed"

    st="$(state_get_line "$name")"
    local next_due last_status last_ping last_sent last_rtt
    if [[ -n "$st" ]]; then
      IFS='|' read -r _n next_due last_status last_ping last_sent last_rtt <<<"$st"
    else
      next_due="0"
      last_status="unknown"
      last_ping="0"
      last_sent="0"
      last_rtt="-1"
    fi

    next_due="${next_due:-0}"
    last_status="${last_status:-unknown}"
    last_ping="${last_ping:-0}"
    last_sent="${last_sent:-0}"
    last_rtt="${last_rtt:--1}"

    if [[ "$enabled" == "0" ]]; then
      last_status="disabled"
    fi

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

    printf "  %-26s %-10s %-12s %-14s %-14s %-14s %-10s\n" \
      "$name" "$last_status" "$next_in" "$next_due" "$last_ping" "$last_sent" "$last_rtt"
  done < "$CONFIG_FILE"

  echo "----------------------------------------------------------------------------------------------------------------------------"
}

test_target() {
  require_root test
  ensure_paths

  local name="${1:-}"
  [[ -z "$name" ]] && { usage; exit 1; }
  validate_name "$name"

  line="$(grep -E "^${name}\|" "$CONFIG_FILE" || true)"
  [[ -z "$line" ]] && { echo "Not found: $name"; exit 1; }

  parsed="$(parse_config_line "$line")"
  IFS='|' read -r _name ip url interval enabled <<<"$parsed"

  echo "Testing: $name ($ip) interval=${interval}s enabled=${enabled}"
  if [[ "$enabled" == "0" ]]; then
    echo "DISABLED: skipping"
    exit 4
  fi

  local p
  if p="$(ping_latency "$ip")"; then
    local ms
    ms="${p#OK|}"
    echo "PING: OK (${ms}ms)"
    echo "Calling endpoint…"
    if send_endpoint "$url"; then
      echo "ENDPOINT: OK"
      exit 0
    else
      echo "ENDPOINT: FAILED (curl)"
      exit 2
    fi
  else
    echo "PING: FAILED"
    exit 3
  fi
}

# Helper: check if name is in comma list
name_in_list() {
  local name="$1"
  local list="$2"
  [[ -z "$list" ]] && return 1
  IFS=',' read -r -a arr <<<"$list"
  for n in "${arr[@]}"; do
    [[ "$n" == "$name" ]] && return 0
  done
  return 1
}

run_checks_internal() {
  local force="${1:-0}"           # 1 = ignore schedule (run-now)
  local only_targets="${2:-}"     # comma list; if set -> run only these

  ensure_paths
  [[ ! -s "$CONFIG_FILE" ]] && { log "RUN: no targets"; echo "No targets"; exit 0; }

  local now
  now="$(date +%s)"

  local total=0 due=0 skipped=0 ping_ok_count=0 ping_fail=0 sent=0 curl_fail=0 disabled_count=0
  local run_start_ns run_end_ns
  run_start_ns="$(date +%s%N)"

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && continue

    parsed="$(parse_config_line "$line")"
    IFS='|' read -r name ip url interval enabled <<<"$parsed"

    # Filter selection if only_targets is set
    if [[ -n "$only_targets" ]]; then
      if ! name_in_list "$name" "$only_targets"; then
        continue
      fi
    fi

    total=$((total+1))

    st="$(state_get_line "$name")"
    local next_due last_status last_ping last_sent last_rtt
    if [[ -n "$st" ]]; then
      IFS='|' read -r _n next_due last_status last_ping last_sent last_rtt <<<"$st"
      next_due="${next_due:-0}"
      last_rtt="${last_rtt:--1}"
    else
      next_due="0"
      last_status="unknown"
      last_ping="0"
      last_sent="0"
      last_rtt="-1"
    fi

    # Disabled targets:
    # - In normal run: always skip
    # - In run-now with selection: allow if explicitly selected
    if [[ "$enabled" == "0" ]]; then
      disabled_count=$((disabled_count+1))
      # If selection is set, it's explicit -> allow running disabled only when selected
      if [[ -z "$only_targets" ]]; then
        skipped=$((skipped+1))
        last_status="disabled"
        state_set_line "${name}|${next_due}|${last_status}|${last_ping}|${last_sent}|${last_rtt}"
        continue
      fi
    fi

    if [[ "$force" != "1" ]]; then
      if (( now < next_due )); then
        skipped=$((skipped+1))
        continue
      fi
    end

    due=$((due+1))

    local p ms
    if p="$(ping_latency "$ip")"; then
      ms="${p#OK|}"
      ping_ok_count=$((ping_ok_count+1))
      last_status="up"
      last_ping="$now"
      last_rtt="${ms:-0}"

      if send_endpoint "$url"; then
        sent=$((sent+1))
        last_sent="$now"
        log "OK   name=$name ip=$ip rtt=${last_rtt}ms interval=${interval}s endpoint=sent"
      else
        curl_fail=$((curl_fail+1))
        log "WARN name=$name ip=$ip rtt=${last_rtt}ms interval=${interval}s ping=ok endpoint=FAILED(curl)"
      fi
    else
      ping_fail=$((ping_fail+1))
      last_status="down"
      last_ping="$now"
      last_rtt="-1"
      log "DOWN name=$name ip=$ip interval=${interval}s ping=failed endpoint=not_sent"
    fi

    next_due=$(( now + interval ))
    state_set_line "${name}|${next_due}|${last_status}|${last_ping}|${last_sent}|${last_rtt}"
  done < "$CONFIG_FILE"

  run_end_ns="$(date +%s%N)"
  local dur_ms
  dur_ms="$(( (run_end_ns - run_start_ns) / 1000000 ))"

  log "RUN summary total=$total due=$due skipped=$skipped ping_ok=$ping_ok_count ping_fail=$ping_fail sent=$sent curl_fail=$curl_fail disabled=$disabled_count force=$force duration_ms=$dur_ms"
  echo "OK: total=$total due=$due skipped=$skipped ping_ok=$ping_ok_count ping_fail=$ping_fail sent=$sent curl_fail=$curl_fail disabled=$disabled_count force=$force duration_ms=$dur_ms"
}

run_checks() {
  require_root run
  run_checks_internal "0" ""
}

run_now() {
  require_root run-now
  ensure_paths

  local targets=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --targets)
        targets="${2:-}"
        shift 2
        ;;
      *)
        shift
        ;;
    esac
  done

  # force=1. If targets set, run only these (even if disabled, since explicit).
  run_checks_internal "1" "$targets"
}

install_systemd() {
  require_root install
  ensure_paths
  command -v systemctl >/dev/null 2>&1 || { echo "systemd not available"; exit 1; }

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
  echo "Installed systemd: $APP_NAME.service + $APP_NAME.timer"
  echo "Next: sudo $BIN_PATH enable"
}

uninstall_systemd() {
  require_root uninstall
  if command -v systemctl >/dev/null 2>&1; then
    systemctl disable --now "${APP_NAME}.timer" >/dev/null 2>&1 || true
    rm -f "$SERVICE_PATH" "$TIMER_PATH"
    systemctl daemon-reload || true
  fi
  rm -f "$BIN_PATH"
  echo "Uninstalled. Config kept: $CONFIG_FILE"
}

enable_timer() {
  require_root enable
  systemctl enable --now "${APP_NAME}.timer"
  echo "Enabled: ${APP_NAME}.timer"
}

disable_timer() {
  require_root disable
  systemctl disable --now "${APP_NAME}.timer"
  echo "Disabled: ${APP_NAME}.timer"
}

sys_status() {
  require_root sys-status
  systemctl status "${APP_NAME}.timer" --no-pager || true
  echo ""
  journalctl -t "$APP_NAME" -n 25 --no-pager --output=cat || true
}

main() {
  cmd="${1:-}"
  shift || true

  case "$cmd" in
    add) add_target "${1:-}" "${2:-}" "${3:-}" "${4:-$DEFAULT_INTERVAL_SEC}" ;;
    remove) remove_target "${1:-}" ;;
    list) list_targets ;;
    run) run_checks ;;
    run-now) run_now "$@" ;;
    test) test_target "${1:-}" ;;
    set-target-interval) set_target_interval "${1:-}" "${2:-}" ;;
    disable) disable_target "${1:-}" ;;
    enable-target) enable_target "${1:-}" ;;
    disable-selected) disable_selected "${1:-}" ;;
    enable-selected) enable_selected "${1:-}" ;;
    status) status_targets ;;
    install) install_systemd ;;
    uninstall) uninstall_systemd ;;
    enable) enable_timer ;;
    disable) disable_timer ;;
    sys-status) sys_status ;;
    ""|help|-h|--help) usage ;;
    *) echo "Unknown command: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
