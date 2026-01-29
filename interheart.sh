#!/usr/bin/env bash
set -euo pipefail

# interheart v4.8.0
# 5echo.io © 2026 All rights reserved

APP_NAME="interheart"

CONFIG_FILE="/etc/5echo/interheart.conf"
LOG_FILE="/var/log/interheart.log"
STATE_DIR="/var/lib/interheart"
STATE_FILE="${STATE_DIR}/state.db"

RUNTIME_FILE="${STATE_DIR}/runtime.json"
RUN_META_FILE="${STATE_DIR}/run_meta.json"
RUN_OUT_FILE="${STATE_DIR}/run_last_output.txt"

LAT_DIR="${STATE_DIR}/latency"
LAT_KEEP=20

# Defaults
DEFAULT_INTERVAL_SEC=60
RUNNER_DEFAULT_SEC=10   # how often systemd timer triggers
PING_COUNT_DEFAULT=1
PING_TIMEOUT_DEFAULT=1
CURL_TIMEOUT_DEFAULT=6

BIN_PATH="/usr/local/bin/${APP_NAME}"
SERVICE_PATH="/etc/systemd/system/${APP_NAME}.service"
TIMER_PATH="/etc/systemd/system/${APP_NAME}.timer"

VERSION_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/VERSION"
VERSION="4.8.0"
if [[ -f "$VERSION_FILE" ]]; then
  VERSION="$(cat "$VERSION_FILE" 2>/dev/null | tr -d '[:space:]' || echo "4.8.0")"
fi

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "This must run as root. Use: sudo $0 $*" >&2
    exit 1
  fi
}

ensure_paths() {
  mkdir -p "$(dirname "$CONFIG_FILE")"
  touch "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE"

  mkdir -p "$STATE_DIR" "$LAT_DIR"
  chmod 700 "$STATE_DIR"
  touch "$STATE_FILE"
  chmod 600 "$STATE_FILE"

  # runtime files (used by WebUI)
  : > "$RUNTIME_FILE" 2>/dev/null || true
  : > "$RUN_META_FILE" 2>/dev/null || true
  : > "$RUN_OUT_FILE" 2>/dev/null || true
  chmod 666 "$RUNTIME_FILE" "$RUN_META_FILE" "$RUN_OUT_FILE" 2>/dev/null || true
}

log() {
  local msg="$1"
  local line
  line="$(date '+%Y-%m-%d %H:%M:%S') - ${msg}"

  # avoid syslog prefix pollution in content; keep message clean
  if command -v systemd-cat >/dev/null 2>&1; then
    echo "$line" | systemd-cat -t "$APP_NAME" >/dev/null 2>&1 || true
  fi
  echo "$line" >> "$LOG_FILE" 2>/dev/null || true
}

usage() {
  cat <<EOF
5echo ${APP_NAME} v${VERSION}

Config formats supported:
  NAME|IP|ENDPOINT_URL
  NAME|IP|ENDPOINT_URL|INTERVAL_SEC
  NAME|IP|ENDPOINT_URL|INTERVAL_SEC|ENABLED   (ENABLED: 1 or 0)

Targets:
  $0 add <name> <ip> <endpoint_url> [interval_sec]
  $0 remove <name>
  $0 list
  $0 status
  $0 test <name>
  $0 set-target-interval <name> <seconds>
  $0 disable <name>
  $0 enable <name>

Run:
  $0 run
  $0 run-now [--targets name1,name2,...] [--force 1]

Systemd:
  $0 install
  $0 uninstall
  $0 enable-timer
  $0 disable-timer
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
      echo "Invalid IP '$ip' (octet out of range)." >&2
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
  [[ "$sec" =~ ^[0-9]+$ ]] || { echo "Interval must be an integer (seconds)."; exit 1; }
  (( sec >= 10 && sec <= 86400 )) || { echo "Interval must be 10..86400 seconds."; exit 1; }
}

config_has_name() {
  local name="$1"
  grep -qE "^${name}\|" "$CONFIG_FILE"
}

# returns: name|ip|url|interval|enabled
parse_config_line() {
  local line="$1"
  local name ip url interval enabled
  IFS='|' read -r name ip url interval enabled <<<"$line"
  interval="${interval:-$DEFAULT_INTERVAL_SEC}"
  enabled="${enabled:-1}"
  [[ "$enabled" != "0" ]] && enabled="1"
  echo "${name}|${ip}|${url}|${interval}|${enabled}"
}

# State db format:
# NAME|NEXT_DUE_EPOCH|LAST_STATUS|LAST_PING_EPOCH|LAST_SENT_EPOCH|LAST_LAT_MS
state_get_line() {
  local name="$1"
  grep -E "^${name}\|" "$STATE_FILE" 2>/dev/null || true
}

state_set_line() {
  local newline="$1"
  local name
  IFS='|' read -r name _ <<<"$newline"

  local tmp
  tmp="$(mktemp)"
  grep -vE "^${name}\|" "$STATE_FILE" 2>/dev/null > "$tmp" || true
  echo "$newline" >> "$tmp"
  cat "$tmp" > "$STATE_FILE"
  rm -f "$tmp"
  chmod 600 "$STATE_FILE"
}

mask_url() {
  local url="$1"
  echo "$url" | sed -E 's#(https?://[^/]+/).{4,}#\1***#'
}

ping_latency_ms() {
  local ip="$1"
  # Use ping -c 1 -W 1 and parse "time=XX ms"
  local out
  if ! out="$(ping -c "$PING_COUNT_DEFAULT" -W "$PING_TIMEOUT_DEFAULT" "$ip" 2>/dev/null)"; then
    echo ""
    return 1
  fi
  local t
  t="$(echo "$out" | sed -nE 's/.*time=([0-9.]+) ms.*/\1/p' | head -n1 || true)"
  if [[ -z "$t" ]]; then
    echo ""
    return 1
  fi
  # convert to int ms (round)
  python3 - <<PY 2>/dev/null || true
import math
t=float("$t")
print(int(round(t)))
PY
  return 0
}

lat_push() {
  local name="$1"
  local ms="$2"
  local f="${LAT_DIR}/${name}.json"
  python3 - <<PY 2>/dev/null || true
import json, os
f="$f"
ms=int("$ms")
keep=int("$LAT_KEEP")
arr=[]
try:
  if os.path.exists(f):
    with open(f,"r",encoding="utf-8") as fh:
      arr=json.load(fh) or []
except Exception:
  arr=[]
arr.append(ms)
arr=arr[-keep:]
os.makedirs(os.path.dirname(f), exist_ok=True)
with open(f,"w",encoding="utf-8") as fh:
  json.dump(arr, fh)
PY
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
    echo "Target already exists: $name. Remove first: sudo $0 remove $name" >&2
    exit 1
  fi

  echo "${name}|${ip}|${url}|${interval}|1" >> "$CONFIG_FILE"
  chmod 600 "$CONFIG_FILE"

  local now
  now="$(date +%s)"
  state_set_line "${name}|${now}|unknown|0|0|0"

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

  rm -f "${LAT_DIR}/${name}.json" 2>/dev/null || true

  log "REMOVE name=$name"
  echo "Removed: $name"
}

set_target_interval() {
  require_root set-target-interval
  ensure_paths

  local name="${1:-}"
  local sec="${2:-}"
  [[ -z "$name" || -z "$sec" ]] && { echo "Usage: sudo $0 set-target-interval <name> <seconds>"; exit 1; }
  validate_name "$name"
  validate_interval "$sec"

  if ! config_has_name "$name"; then
    echo "Not found: $name" >&2
    exit 1
  fi

  local tmp
  tmp="$(mktemp)"
  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
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
    IFS='|' read -r _n _due last_status last_ping last_sent last_lat <<<"$old"
    state_set_line "${name}|${now}|${last_status:-unknown}|${last_ping:-0}|${last_sent:-0}|${last_lat:-0}"
  else
    state_set_line "${name}|${now}|unknown|0|0|0"
  fi

  log "SET_INTERVAL name=$name interval=${sec}s"
  echo "Updated: $name interval=${sec}s"
}

set_target_enabled() {
  require_root enable-disable
  ensure_paths
  local name="${1:-}"
  local en="${2:-}"
  [[ -z "$name" || -z "$en" ]] && { echo "Usage: sudo $0 enable|disable <name>"; exit 1; }
  validate_name "$name"
  [[ "$en" != "0" ]] && en="1"

  if ! config_has_name "$name"; then
    echo "Not found: $name" >&2
    exit 1
  fi

  local tmp
  tmp="$(mktemp)"
  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    parsed="$(parse_config_line "$line")"
    IFS='|' read -r n ip url interval enabled <<<"$parsed"
    if [[ "$n" == "$name" ]]; then
      echo "${n}|${ip}|${url}|${interval}|${en}" >> "$tmp"
    else
      echo "${n}|${ip}|${url}|${interval}|${enabled}" >> "$tmp"
    fi
  done < "$CONFIG_FILE"

  cat "$tmp" > "$CONFIG_FILE"
  rm -f "$tmp"
  chmod 600 "$CONFIG_FILE"

  log "SET_ENABLED name=$name enabled=$en"
  echo "Updated: $name enabled=$en"
}

enable_target(){ set_target_enabled "${1:-}" "1"; }
disable_target(){ set_target_enabled "${1:-}" "0"; }

list_targets() {
  require_root list
  ensure_paths

  if [[ ! -s "$CONFIG_FILE" ]]; then
    echo "No targets in $CONFIG_FILE"
    exit 0
  fi

  echo "Targets:"
  echo "---------------------------------------------------------------------------------------------------------------"
  printf "  %-26s %-15s %-10s %-9s %s\n" "NAME" "IP" "INTERVAL" "ENABLED" "ENDPOINT"
  echo "---------------------------------------------------------------------------------------------------------------"
  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    parsed="$(parse_config_line "$line")"
    IFS='|' read -r name ip url interval enabled <<<"$parsed"
    printf "  %-26s %-15s %-10s %-9s %s\n" "$name" "$ip" "${interval}s" "$enabled" "$(mask_url "$url")"
  done < "$CONFIG_FILE"
  echo "---------------------------------------------------------------------------------------------------------------"
}

status_targets() {
  require_root status
  ensure_paths

  local now
  now="$(date +%s)"

  echo "State:"
  echo "-------------------------------------------------------------------------------------------------------------------------------"
  printf "  %-26s %-10s %-12s %-14s %-14s %-14s %-10s\n" "NAME" "STATUS" "NEXT_IN" "NEXT_DUE" "LAST_PING" "LAST_RESP" "LAT_MS"
  echo "-------------------------------------------------------------------------------------------------------------------------------"

  [[ ! -s "$CONFIG_FILE" ]] && { echo "  (no targets)"; exit 0; }

  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    parsed="$(parse_config_line "$line")"
    IFS='|' read -r name _ip _url _interval enabled <<<"$parsed"

    st="$(state_get_line "$name")"
    local next_due last_status last_ping last_sent last_lat
    if [[ -n "$st" ]]; then
      IFS='|' read -r _n next_due last_status last_ping last_sent last_lat <<<"$st"
    else
      next_due="0"; last_status="unknown"; last_ping="0"; last_sent="0"; last_lat="0"
    fi

    local next_in
    if (( now < ${next_due:-0} )); then
      next_in="$(( next_due - now ))s"
    else
      next_in="due"
    fi

    printf "  %-26s %-10s %-12s %-14s %-14s %-14s %-10s\n" \
      "$name" "${last_status:-unknown}" "$next_in" "${next_due:-0}" "${last_ping:-0}" "${last_sent:-0}" "${last_lat:-0}"
  done < "$CONFIG_FILE"

  echo "-------------------------------------------------------------------------------------------------------------------------------"
}

test_target() {
  require_root test
  ensure_paths

  local name="${1:-}"
  [[ -z "$name" ]] && { usage; exit 1; }
  validate_name "$name"

  local line
  line="$(grep -E "^${name}\|" "$CONFIG_FILE" || true)"
  [[ -z "$line" ]] && { echo "Not found: $name"; exit 1; }

  local parsed ip url interval enabled
  parsed="$(parse_config_line "$line")"
  IFS='|' read -r _name ip url interval enabled <<<"$parsed"

  echo "Testing: $name ($ip) interval=${interval}s enabled=${enabled}"
  if [[ "$enabled" == "0" ]]; then
    echo "DISABLED"
    exit 4
  fi

  local ms
  ms="$(ping_latency_ms "$ip" || true)"
  if [[ -n "$ms" ]]; then
    echo "PING: OK (${ms}ms)"
    echo "Calling endpoint…"
    if send_endpoint "$url"; then
      echo "ENDPOINT: OK"
      exit 0
    else
      echo "ENDPOINT: FAIL (curl)"
      exit 2
    fi
  else
    echo "PING: FAIL"
    exit 3
  fi
}

write_runtime() {
  # args: status current done due queue_json updated
  local status="$1" current="$2" done="$3" due="$4" queue="$5"
  python3 - <<PY 2>/dev/null || true
import json, time
data={
  "status":"$status",
  "current":"$current",
  "done":int("$done"),
  "due":int("$due"),
  "queue":$queue,
  "updated":int(time.time())
}
open("$RUNTIME_FILE","w",encoding="utf-8").write(json.dumps(data))
PY
  chmod 666 "$RUNTIME_FILE" 2>/dev/null || true
}

run_checks_internal() {
  # args: force(0/1) selected_csv(optional)
  local force="${1:-0}"
  local selected="${2:-}"

  [[ ! -s "$CONFIG_FILE" ]] && { log "RUN: no targets"; echo "No targets"; exit 0; }

  local now
  now="$(date +%s)"

  # build selection map
  declare -A sel
  if [[ -n "$selected" ]]; then
    IFS=',' read -r -a arr <<<"$selected"
    for n in "${arr[@]}"; do
      n="$(echo "$n" | xargs || true)"
      [[ -n "$n" ]] && sel["$n"]=1
    done
  fi

  local total=0 due=0 skipped=0 ping_ok_count=0 ping_fail=0 sent=0 curl_fail=0 disabled=0
  local queue_json="[]"
  if [[ -n "$selected" ]]; then
    # queue only selected
    queue_json="$(python3 - <<PY 2>/dev/null
import json
s="$selected".split(",")
s=[x.strip() for x in s if x.strip()]
print(json.dumps(s))
PY
)"
  else
    # queue all enabled targets
    queue_json="$(python3 - <<PY 2>/dev/null
import json
cfg=open("$CONFIG_FILE","r",encoding="utf-8").read().splitlines()
out=[]
for line in cfg:
  line=line.strip()
  if not line or line.startswith("#"): continue
  parts=line.split("|")
  name=parts[0].strip()
  enabled="1"
  if len(parts)>=5:
    enabled=parts[4].strip() or "1"
  if enabled!="0":
    out.append(name)
print(json.dumps(out))
PY
)"
  fi

  write_runtime "running" "" 0 0 "$queue_json"

  local done_count=0
  local due_count=0

  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue

    local parsed name ip url interval enabled
    parsed="$(parse_config_line "$line")"
    IFS='|' read -r name ip url interval enabled <<<"$parsed"

    # selection filter
    if [[ -n "$selected" && -z "${sel[$name]+x}" ]]; then
      continue
    fi

    total=$((total+1))

    if [[ "$enabled" == "0" ]]; then
      disabled=$((disabled+1))
      continue
    fi

    local st next_due last_status last_ping last_sent last_lat
    st="$(state_get_line "$name")"
    if [[ -n "$st" ]]; then
      IFS='|' read -r _n next_due last_status last_ping last_sent last_lat <<<"$st"
      next_due="${next_due:-0}"
    else
      next_due="0"; last_status="unknown"; last_ping="0"; last_sent="0"; last_lat="0"
    fi

    if (( force == 0 )) && (( now < next_due )); then
      skipped=$((skipped+1))
      continue
    fi

    due=$((due+1))
    due_count=$due

    write_runtime "running" "$name" "$done_count" "$due_count" "$queue_json"

    local ms
    ms="$(ping_latency_ms "$ip" || true)"

    if [[ -n "$ms" ]]; then
      ping_ok_count=$((ping_ok_count+1))
      last_status="up"
      last_ping="$now"
      last_lat="$ms"
      lat_push "$name" "$ms"

      if send_endpoint "$url"; then
        sent=$((sent+1))
        last_sent="$now"
        log "OK name=$name ip=$ip latency=${ms}ms endpoint=sent"
      else
        curl_fail=$((curl_fail+1))
        log "WARN name=$name ip=$ip latency=${ms}ms ping=ok endpoint=FAILED(curl)"
      fi
    else
      ping_fail=$((ping_fail+1))
      last_status="down"
      last_ping="$now"
      last_lat="0"
      log "DOWN name=$name ip=$ip ping=failed endpoint=not_sent"
    fi

    next_due=$(( now + interval ))
    state_set_line "${name}|${next_due}|${last_status}|${last_ping}|${last_sent}|${last_lat}"

    done_count=$((done_count+1))
    write_runtime "running" "$name" "$done_count" "$due_count" "$queue_json"
  done < "$CONFIG_FILE"

  write_runtime "idle" "" "$done_count" "$due_count" "$queue_json"

  log "RUN summary total=$total due=$due skipped=$skipped ping_ok=$ping_ok_count ping_fail=$ping_fail sent=$sent curl_fail=$curl_fail force=$force disabled=$disabled"
  echo "OK: total=$total due=$due skipped=$skipped ping_ok=$ping_ok_count ping_fail=$ping_fail sent=$sent curl_fail=$curl_fail force=$force disabled=$disabled"
}

run_checks() {
  require_root run
  ensure_paths
  run_checks_internal 0 ""
}

run_now() {
  require_root run-now
  ensure_paths

  local force="0"
  local targets_csv=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --force) force="${2:-0}"; shift 2 ;;
      --targets) targets_csv="${2:-}"; shift 2 ;;
      *) shift 1 ;;
    esac
  done

  run_checks_internal "$force" "$targets_csv"
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
  echo "Next: sudo $BIN_PATH enable-timer"
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
  require_root enable-timer
  systemctl enable --now "${APP_NAME}.timer"
  echo "Enabled: ${APP_NAME}.timer"
}

disable_timer() {
  require_root disable-timer
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
    enable) enable_target "${1:-}" ;;
    status) status_targets ;;
    install) install_systemd ;;
    uninstall) uninstall_systemd ;;
    enable-timer) enable_timer ;;
    disable-timer) disable_timer ;;
    sys-status) sys_status ;;
    ""|help|-h|--help) usage ;;
    *) echo "Unknown command: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
