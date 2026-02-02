#!/usr/bin/env bash

# =============================================================================
# Copyright (c) 2026 5echo.io
# Project: interheart
# Purpose: Runner script for performing checks and updating persistent state.
# Path: /interheart.sh
# Created: 2026-02-01
# Last modified: 2026-02-01
# =============================================================================

set -euo pipefail

# ------------------------------------------------------------
# interheart runner + utilities
#
# v5.43.0-beta.4 (2026-02-01)
# - Added: self-test and self-test-output commands (diagnostics)
# ------------------------------------------------------------

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# interheart CLI
# Stores state in /var/lib/interheart/state.db
# Requires: sqlite3, curl, ping

STATE_DIR="/var/lib/interheart"
DB="${STATE_DIR}/state.db"
LOG_TAG="interheart"


#############################################
# Debug system (backend)
#
# Goals:
# - Always keep a small snapshot for quick copy/paste:   /var/lib/interheart/debug_state.txt
# - Keep structured, timestamped debug logs for 7 days:  /var/lib/interheart/debug/*.log
# - Never grow without bounds (auto-rotates daily + retention)
# - Survives reboots (logs are files on disk)
# - Can be made noisier via: INTERHEART_DEBUG=1
#############################################

DEBUG_STATE_FILE="${STATE_DIR}/debug_state.txt"
DEBUG_DIR="${STATE_DIR}/debug"

DEBUG_RETENTION_DAYS=7
DEBUG_MAX_LINES_PER_FILE=20000

_debug_day() { date -u "+%Y-%m-%d" 2>/dev/null || date "+%Y-%m-%d"; }
_debug_ts() { date -u "+%Y-%m-%dT%H:%M:%S.%3NZ" 2>/dev/null || date -u "+%Y-%m-%dT%H:%M:%SZ"; }
_debug_enabled() { [[ "${INTERHEART_DEBUG:-0}" == "1" || "${INTERHEART_DEBUG:-0}" == "true" ]]; }

_debug_log_file() {
  mkdir -p "${DEBUG_DIR}" >/dev/null 2>&1 || true
  echo "${DEBUG_DIR}/runner-$(_debug_day).log"
}

_debug_rotate() {
  mkdir -p "${DEBUG_DIR}" >/dev/null 2>&1 || true
  # Keep only the newest N days (by filename date). Best-effort, no strict TZ assumptions.
  local keep_days="$DEBUG_RETENTION_DAYS"
  local files
  files=$(ls -1 "${DEBUG_DIR}"/*.log 2>/dev/null | sort || true)
  [[ -n "${files}" ]] || return 0

  # Remove anything older than keep_days using the date in the filename when possible.
  # Format: <component>-YYYY-MM-DD.log
  local cutoff
  cutoff=$(date -u -d "${keep_days} days ago" "+%Y-%m-%d" 2>/dev/null || true)
  if [[ -n "${cutoff}" ]]; then
    while IFS= read -r f; do
      local base day
      base="$(basename "${f}")"
      day="${base##*-}"
      day="${day%.log}"
      if [[ "${day}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] && [[ "${day}" < "${cutoff}" ]]; then
        rm -f "${f}" 2>/dev/null || true
      fi
    done <<<"${files}"
  fi

  # Also keep files from exploding in size (line-based cap).
  local cur
  cur="$(_debug_log_file)"
  if [[ -f "${cur}" ]]; then
    local lines
    lines=$(wc -l <"${cur}" 2>/dev/null || echo 0)
    if [[ "${lines}" =~ ^[0-9]+$ ]] && (( lines > DEBUG_MAX_LINES_PER_FILE )); then
      tail -n $((DEBUG_MAX_LINES_PER_FILE/2)) "${cur}" > "${cur}.tmp" 2>/dev/null || true
      mv -f "${cur}.tmp" "${cur}" 2>/dev/null || true
    fi
  fi
}

_debug_event() {
  # Usage: _debug_event LEVEL COMPONENT message...
  local lvl="${1:-INFO}"; shift || true
  local comp="${1:-runner}"; shift || true
  local msg="$*"
  local line="[$(_debug_ts)] ${lvl} ${comp} ${msg}"

  _debug_rotate || true

  # Always write to file (low overhead), print to stdout only when debug enabled.
  local f
  f="$(_debug_log_file)"
  echo "${line}" >>"${f}" 2>/dev/null || true
  if _debug_enabled; then
    echo "${line}"
  fi
}

### NOTE:
# Older versions had a single debug.log with size-based truncation.
# That approach made it hard to understand *what happened when*.
# We now keep daily logs with a 7-day retention window.

_write_debug_state() {
  # Always update snapshot so we can fetch it from terminal.
  local now version host
  now="$(date -Is 2>/dev/null || date)"
  version="$(cat /opt/interheart/VERSION 2>/dev/null || cat ./VERSION 2>/dev/null || echo -)"
  host="$(hostname 2>/dev/null || echo -)"

  local total enabled disabled up down unknown
  total=$(sqlite3 -noheader -batch "${DB}" 'SELECT COUNT(1) FROM targets;' 2>/dev/null || echo 0)
  enabled=$(sqlite3 -noheader -batch "${DB}" 'SELECT COUNT(1) FROM targets WHERE enabled=1;' 2>/dev/null || echo 0)
  disabled=$(sqlite3 -noheader -batch "${DB}" 'SELECT COUNT(1) FROM targets WHERE enabled!=1;' 2>/dev/null || echo 0)

  up=$(sqlite3 -noheader -batch "${DB}" "SELECT COUNT(1) FROM runtime WHERE status='up';" 2>/dev/null || echo 0)
  down=$(sqlite3 -noheader -batch "${DB}" "SELECT COUNT(1) FROM runtime WHERE status='down';" 2>/dev/null || echo 0)
  unknown=$(sqlite3 -noheader -batch "${DB}" "SELECT COUNT(1) FROM runtime WHERE status NOT IN ('up','down');" 2>/dev/null || echo 0)

  local svc_runner svc_web svc_timer
  if command -v systemctl >/dev/null 2>&1; then
    svc_runner=$(systemctl is-active interheart.service 2>/dev/null || echo -)
    svc_web=$(systemctl is-active interheart-webui.service 2>/dev/null || echo -)
    svc_timer=$(systemctl is-active interheart.timer 2>/dev/null || echo -)
  else
    svc_runner=-; svc_web=-; svc_timer=-
  fi

  {
    echo "interheart_debug_snapshot"
    echo "time=${now}"
    echo "version=${version}"
    echo "host=${host}"
    echo "targets_total=${total}"
    echo "targets_enabled=${enabled}"
    echo "targets_disabled=${disabled}"
    echo "runtime_up=${up}"
    echo "runtime_down=${down}"
    echo "runtime_unknown=${unknown}"
    echo "service_interheart.service=${svc_runner}"
    echo "service_interheart-webui.service=${svc_web}"
    echo "service_interheart.timer=${svc_timer}"
    echo "debug_dir=${DEBUG_DIR}"
    echo
    echo "down_targets_top8"
    sqlite3 -noheader -batch "${DB}" "SELECT t.name||'|'||t.ip||'|'||t.endpoint FROM targets t JOIN runtime r ON r.name=t.name WHERE r.status='down' ORDER BY t.name COLLATE NOCASE LIMIT 8;" 2>/dev/null | while IFS='|' read -r n ip ep; do
      [[ -n "${n:-}" ]] || continue
      echo "${n}|${ip}|$(mask_endpoint "${ep}")"
    done

    echo
    echo "tail_runner_30"
    tail -n 30 "$(_debug_log_file)" 2>/dev/null || true

    # WebUI + Client logs (best effort; written by the Python WebUI)
    day="$(_debug_day)"
    webui_log="${DEBUG_DIR}/webui-${day}.log"
    client_log="${DEBUG_DIR}/client-${day}.log"

    echo
    echo "tail_webui_30"
    tail -n 30 "${webui_log}" 2>/dev/null || true

    echo
    echo "tail_client_30"
    tail -n 30 "${client_log}" 2>/dev/null || true
  } >"${DEBUG_STATE_FILE}" 2>/dev/null || true
}

mkdir -p "${STATE_DIR}" >/dev/null 2>&1 || true

have_cmd() { command -v "$1" >/dev/null 2>&1; }

die() {
  echo "$*" >&2
  exit 1
}

mask_endpoint() {
  # Keep scheme + host, hide path/query
  # https://host/path?x=1  -> https://host/***
  local url="${1:-}"
  if [[ -z "$url" ]]; then
    echo "-"
    return
  fi
  # extract scheme://host[:port]
  local scheme host rest
  scheme="$(echo "$url" | awk -F:// '{print $1}')"
  rest="$(echo "$url" | sed -E 's#^[a-zA-Z]+://##')"
  host="$(echo "$rest" | awk -F/ '{print $1}')"
  if [[ -n "$scheme" && -n "$host" ]]; then
    echo "${scheme}://${host}/***"
  else
    echo "***"
  fi
}

require_deps() {
  have_cmd sqlite3 || die "ERROR: Missing sqlite3"
  have_cmd curl    || die "ERROR: Missing curl"
  have_cmd ping    || die "ERROR: Missing ping"
}

init_db() {
  require_deps
  mkdir -p "${STATE_DIR}" >/dev/null 2>&1 || true
  sqlite3 "${DB}" <<'SQL'
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS targets (
  name TEXT PRIMARY KEY,
  ip TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  interval INTEGER NOT NULL DEFAULT 60,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS runtime (
  name TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'unknown',
  next_due INTEGER NOT NULL DEFAULT 0,
  last_ping INTEGER NOT NULL DEFAULT 0,
  last_sent INTEGER NOT NULL DEFAULT 0,
  last_rtt_ms INTEGER NOT NULL DEFAULT -1
);

CREATE TABLE IF NOT EXISTS history (
  ts INTEGER NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,   -- 'up' | 'down' | 'disabled'
  rtt_ms INTEGER NOT NULL DEFAULT -1,
  curl_http INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_history_name_ts ON history(name, ts);

CREATE INDEX IF NOT EXISTS idx_targets_enabled ON targets(enabled);
CREATE INDEX IF NOT EXISTS idx_runtime_next_due ON runtime(next_due);
SQL
}

sql_one() {
  local q="$1"
  sqlite3 -noheader -batch "${DB}" "${q}"
}

sql_exec() {
  local q="$1"
  sqlite3 -batch "${DB}" "${q}"
}

ensure_exists() {
  [[ -f "${DB}" ]] || init_db
}

now_epoch() {
  date +%s
}

log_info() {
  # journal tag
  # If called by systemd/journal, stdout may be captured; keep it simple.
  echo "$*"
}

usage() {
  cat <<EOF
interheart

Usage:
  interheart init-db
  interheart add <name> <ip> <endpoint> <interval_seconds>
  interheart remove <name>
  interheart list
  interheart status
  interheart get <name>
  interheart edit <old_name> <new_name> <ip> <endpoint> <interval_seconds> <enabled 0|1>
  interheart disable <name>
  interheart enable <name>
  interheart set-target-interval <name> <interval_seconds>
  interheart test <name>
  interheart run-now [--targets name1,name2,...] [--force]
  interheart debug [--follow] [--json]
  interheart self-test
  interheart self-test-output

Notes:
  - Data stored in: ${DB}
EOF
}

validate_name() {
  local name="$1"
  [[ -n "$name" ]] || return 1
  # allow: letters, numbers, dash, underscore, dot
  [[ "$name" =~ ^[a-zA-Z0-9._-]+$ ]] || return 1
  return 0
}

validate_ip() {
  local ip="$1"
  [[ "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
  local o1 o2 o3 o4
  IFS='.' read -r o1 o2 o3 o4 <<<"$ip"
  for o in "$o1" "$o2" "$o3" "$o4"; do
    [[ "$o" -ge 0 && "$o" -le 255 ]] || return 1
  done
  return 0
}

validate_interval() {
  local s="$1"
  [[ "$s" =~ ^[0-9]+$ ]] || return 1
  [[ "$s" -ge 10 && "$s" -le 86400 ]] || return 1
  return 0
}

validate_endpoint() {
  local u="$1"
  [[ -n "$u" ]] || return 1
  [[ "$u" =~ ^https?:// ]] || return 1
  return 0
}

cmd_add() {
  ensure_exists
  local name="${1:-}"
  local ip="${2:-}"
  local endpoint="${3:-}"
  local interval="${4:-}"

  validate_name "$name" || die "ERROR: Invalid name (allowed: a-zA-Z0-9._-)"
  validate_ip "$ip" || die "ERROR: Invalid IP"
  validate_endpoint "$endpoint" || die "ERROR: Endpoint must start with http:// or https://"
  validate_interval "$interval" || die "ERROR: Interval must be 10-86400 seconds"

  local exists
  exists="$(sql_one "SELECT 1 FROM targets WHERE name='$(printf "%q" "$name" | sed "s/^'//;s/'$//")' LIMIT 1;")" || true
  # (printf %q quote is shell-ish; use sqlite safe quoting below)
  # We'll do safe quoting by replacing single quotes.
  local n_esc ip_esc ep_esc
  n_esc="${name//\'/\'\'}"
  ip_esc="${ip//\'/\'\'}"
  ep_esc="${endpoint//\'/\'\'}"

  local exists2
  exists2="$(sql_one "SELECT 1 FROM targets WHERE name='${n_esc}' LIMIT 1;")" || true
  [[ -z "$exists2" ]] || die "ERROR: Target already exists: ${name}"

  local now
  now="$(now_epoch)"

  sql_exec "INSERT INTO targets(name,ip,endpoint,interval,enabled,created_at,updated_at)
            VALUES('${n_esc}','${ip_esc}','${ep_esc}',${interval},1,${now},${now});"

  # create runtime baseline
  sql_exec "INSERT OR REPLACE INTO runtime(name,status,next_due,last_ping,last_sent,last_rtt_ms)
            VALUES('${n_esc}','unknown',0,0,0,-1);"

  log_info "OK: Added ${name}"
}

cmd_remove() {
  ensure_exists
  local name="${1:-}"
  validate_name "$name" || die "ERROR: Invalid name"
  local n_esc="${name//\'/\'\'}"

  local exists
  exists="$(sql_one "SELECT 1 FROM targets WHERE name='${n_esc}' LIMIT 1;")" || true
  [[ -n "$exists" ]] || die "ERROR: Not found: ${name}"

  sql_exec "DELETE FROM targets WHERE name='${n_esc}';"
  sql_exec "DELETE FROM runtime WHERE name='${n_esc}';"
  log_info "OK: Removed ${name}"
}

cmd_list() {
  ensure_exists

  echo "Targets:"
  echo "--------------------------------------------------------------------------------"
  echo "NAME                 IP               INTERVAL   ENABLED   ENDPOINT"
  echo "--------------------------------------------------------------------------------"

  # fixed-width-ish formatting
  sqlite3 -noheader -batch "${DB}" \
    "SELECT name, ip, interval, enabled, endpoint FROM targets ORDER BY name COLLATE NOCASE;" \
  | while IFS='|' read -r name ip interval enabled endpoint; do
      local masked
      masked="$(mask_endpoint "$endpoint")"
      printf "%-20s %-16s %-9ss %-8s %s\n" "$name" "$ip" "$interval" "$enabled" "$masked"
    done
}

cmd_status() {
  ensure_exists
  local now
  now="$(now_epoch)"

  echo "State:"
  echo "----------------------------------------------------------------------------------------------------------------------------"
  echo "NAME                 STATUS     NEXT_IN     NEXT_DUE     LAST_PING   LAST_RESP   LAT_MS"
  echo "----------------------------------------------------------------------------------------------------------------------------"

  # Join targets + runtime
  sqlite3 -noheader -batch "${DB}" \
    "SELECT t.name,
            CASE WHEN t.enabled=0 THEN 'disabled' ELSE COALESCE(r.status,'unknown') END AS status,
            COALESCE(r.next_due,0) AS next_due,
            COALESCE(r.last_ping,0) AS last_ping,
            COALESCE(r.last_sent,0) AS last_sent,
            COALESCE(r.last_rtt_ms,-1) AS last_rtt_ms
     FROM targets t
     LEFT JOIN runtime r ON r.name=t.name
     ORDER BY t.name COLLATE NOCASE;" \
  | while IFS='|' read -r name status next_due last_ping last_sent last_rtt_ms; do
      local next_in
      if [[ "$next_due" =~ ^[0-9]+$ && "$next_due" -gt 0 ]]; then
        if [[ "$next_due" -le "$now" ]]; then next_in=0; else next_in=$((next_due - now)); fi
      else
        next_in=0
        next_due=0
      fi

      printf "%-20s %-10s %-10s %-10s %-10s %-10s %-6s\n" \
        "$name" "$status" "${next_in}" "${next_due}" "${last_ping:-0}" "${last_sent:-0}" "${last_rtt_ms:-1}"
    done
}

cmd_get() {
  ensure_exists
  local name="${1:-}"
  validate_name "$name" || die "ERROR: Invalid name"
  local n_esc="${name//\'/\'\'}"

  local row
  row="$(sqlite3 -noheader -batch "${DB}" \
    "SELECT name, ip, endpoint, interval, enabled FROM targets WHERE name='${n_esc}' LIMIT 1;")" || true

  [[ -n "$row" ]] || die "ERROR: Not found: ${name}"

  # Output format required by WebUI:
  # name|ip|endpoint|interval|enabled
  echo "$row"
}

cmd_disable() {
  ensure_exists
  local name="${1:-}"
  validate_name "$name" || die "ERROR: Invalid name"
  local n_esc="${name//\'/\'\'}"

  local exists
  exists="$(sql_one "SELECT 1 FROM targets WHERE name='${n_esc}' LIMIT 1;")" || true
  [[ -n "$exists" ]] || die "ERROR: Not found: ${name}"

  local now
  now="$(now_epoch)"

  sql_exec "UPDATE targets SET enabled=0, updated_at=${now} WHERE name='${n_esc}';"
  # keep status coherent
  sql_exec "UPDATE runtime SET status='disabled' WHERE name='${n_esc}';"
  log_info "OK: Disabled ${name}"
}

cmd_enable() {
  ensure_exists
  local name="${1:-}"
  validate_name "$name" || die "ERROR: Invalid name"
  local n_esc="${name//\'/\'\'}"

  local exists
  exists="$(sql_one "SELECT 1 FROM targets WHERE name='${n_esc}' LIMIT 1;")" || true
  [[ -n "$exists" ]] || die "ERROR: Not found: ${name}"

  local now
  now="$(now_epoch)"

  sql_exec "UPDATE targets SET enabled=1, updated_at=${now} WHERE name='${n_esc}';"
  # runtime will be recalculated at next run; set unknown now
  sql_exec "UPDATE runtime SET status='unknown' WHERE name='${n_esc}';"
  log_info "OK: Enabled ${name}"
}

cmd_set_interval() {
  ensure_exists
  local name="${1:-}"
  local interval="${2:-}"
  validate_name "$name" || die "ERROR: Invalid name"
  validate_interval "$interval" || die "ERROR: Interval must be 10-86400 seconds"
  local n_esc="${name//\'/\'\'}"
  local now
  now="$(now_epoch)"

  local exists
  exists="$(sql_one "SELECT 1 FROM targets WHERE name='${n_esc}' LIMIT 1;")" || true
  [[ -n "$exists" ]] || die "ERROR: Not found: ${name}"

  sql_exec "UPDATE targets SET interval=${interval}, updated_at=${now} WHERE name='${n_esc}';"
  log_info "OK: Interval set for ${name} -> ${interval}s"
}

cmd_edit() {
  ensure_exists
  local old_name="${1:-}"
  local new_name="${2:-}"
  local ip="${3:-}"
  local endpoint="${4:-}"
  local interval="${5:-}"
  local enabled="${6:-}"

  validate_name "$old_name" || die "ERROR: Invalid old_name"
  validate_name "$new_name" || die "ERROR: Invalid new_name"
  validate_ip "$ip" || die "ERROR: Invalid IP"
  validate_endpoint "$endpoint" || die "ERROR: Endpoint must start with http:// or https://"
  validate_interval "$interval" || die "ERROR: Interval must be 10-86400 seconds"
  [[ "$enabled" == "0" || "$enabled" == "1" ]] || die "ERROR: enabled must be 0 or 1"

  local old_esc new_esc ip_esc ep_esc
  old_esc="${old_name//\'/\'\'}"
  new_esc="${new_name//\'/\'\'}"
  ip_esc="${ip//\'/\'\'}"
  ep_esc="${endpoint//\'/\'\'}"

  local exists_old
  exists_old="$(sql_one "SELECT 1 FROM targets WHERE name='${old_esc}' LIMIT 1;")" || true
  [[ -n "$exists_old" ]] || die "ERROR: Not found: ${old_name}"

  # if renaming, ensure new doesn't exist
  if [[ "$old_name" != "$new_name" ]]; then
    local exists_new
    exists_new="$(sql_one "SELECT 1 FROM targets WHERE name='${new_esc}' LIMIT 1;")" || true
    [[ -z "$exists_new" ]] || die "ERROR: Target exists: ${new_name}"
  fi

  local now
  now="$(now_epoch)"

  # Update targets (rename + values)
  sql_exec "UPDATE targets
            SET name='${new_esc}',
                ip='${ip_esc}',
                endpoint='${ep_esc}',
                interval=${interval},
                enabled=${enabled},
                updated_at=${now}
            WHERE name='${old_esc}';"

  # runtime key rename if needed
  if [[ "$old_name" != "$new_name" ]]; then
    sql_exec "UPDATE runtime SET name='${new_esc}' WHERE name='${old_esc}';"
  fi

  # reflect enabled state into runtime status (best effort)
  if [[ "$enabled" == "0" ]]; then
    sql_exec "UPDATE runtime SET status='disabled' WHERE name='${new_esc}';"
  else
    # don't force "up"; just set unknown
    sql_exec "UPDATE runtime SET status='unknown' WHERE name='${new_esc}';"
  fi

  log_info "OK: Updated ${old_name} -> ${new_name}"
}

cmd_test() {
  ensure_exists
  local name="${1:-}"
  validate_name "$name" || die "ERROR: Invalid name"
  local n_esc="${name//\'/\'\'}"

  local row
  row="$(sqlite3 -noheader -batch "${DB}" \
    "SELECT ip, endpoint, interval, enabled FROM targets WHERE name='${n_esc}' LIMIT 1;")" || true
  [[ -n "$row" ]] || die "ERROR: Not found: ${name}"

  local ip endpoint interval enabled
  IFS='|' read -r ip endpoint interval enabled <<<"$row"

  local now
  now="$(now_epoch)"
  # Keep history reasonably small (90 days)
  sql_exec "DELETE FROM history WHERE ts < $((now - 90*24*3600));" >/dev/null 2>&1 || true

  local ping_ok=0 rtt_ms=-1
  local t0 t1
  t0="$(date +%s%3N 2>/dev/null || true)"
  if ping -c 1 -W 1 "$ip" >/dev/null 2>&1; then
    ping_ok=1
    t1="$(date +%s%3N 2>/dev/null || true)"
    if [[ -n "$t0" && -n "$t1" ]]; then rtt_ms=$((t1 - t0)); else rtt_ms=0; fi
  fi

  if [[ "$enabled" != "1" ]]; then
    # Don't mutate schedule for disabled targets, but still allow a ping test.
    :
  fi

  if [[ "$ping_ok" -eq 1 ]]; then
    # curl endpoint
    local code
    code="$(curl -sS -o /dev/null -m 5 -w "%{http_code}" "$endpoint" || true)"
    if [[ "$code" =~ ^[23] ]]; then
      # Mark up
      sql_exec "INSERT OR REPLACE INTO runtime(name,status,next_due,last_ping,last_sent,last_rtt_ms)
                VALUES('${n_esc}','up', $((now + interval)), ${now}, ${now}, ${rtt_ms});" >/dev/null 2>&1 || true
      sql_exec "INSERT INTO history(ts,name,status,rtt_ms,curl_http)
                VALUES(${now},'${n_esc}','up',${rtt_ms},${code:-0});" >/dev/null 2>&1 || true
      echo "OK: ping_ok=1 curl_http=${code}"
    else
      # Mark down (endpoint)
      sql_exec "INSERT OR REPLACE INTO runtime(name,status,next_due,last_ping,last_sent,last_rtt_ms)
                VALUES('${n_esc}','down', $((now + 5)), ${now}, ${now}, ${rtt_ms});" >/dev/null 2>&1 || true
      sql_exec "INSERT INTO history(ts,name,status,rtt_ms,curl_http)
                VALUES(${now},'${n_esc}','down',${rtt_ms},${code:-0});" >/dev/null 2>&1 || true
      echo "WARN: ping_ok=1 curl_http=${code}"
    fi
  else
    # Mark down (ping)
    sql_exec "INSERT OR REPLACE INTO runtime(name,status,next_due,last_ping,last_sent,last_rtt_ms)
              VALUES('${n_esc}','down', $((now + interval)), ${now}, 0, -1);" >/dev/null 2>&1 || true
    sql_exec "INSERT INTO history(ts,name,status,rtt_ms,curl_http)
              VALUES(${now},'${n_esc}','down',-1,0);" >/dev/null 2>&1 || true
    echo "FAIL: ping_ok=0"
  fi
}

cmd_run_now() {
  ensure_exists

  local targets_csv=""
  local force=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --targets)
        targets_csv="${2:-}"
        shift 2
        ;;
      --force)
        force=1
        shift
        ;;
      *)
        die "ERROR: Unknown arg: $1"
        ;;
    esac
  done

  local start_ms end_ms dur_ms
  start_ms="$(date +%s%3N 2>/dev/null || true)"
  local start_epoch
  start_epoch="$(now_epoch)"

  _debug_event INFO runner "run-now start force=${force} targets='${targets_csv:-all}'"

  local total=0 due=0 skipped=0 ping_ok=0 ping_fail=0 sent=0 curl_fail=0 disabled=0

  local now
  now="$start_epoch"

  # Keep history reasonably small (90 days)
  sql_exec "DELETE FROM history WHERE ts < $((now - 90*24*3600));" >/dev/null 2>&1 || true

  # Build target list
  local list_sql
  if [[ -n "$targets_csv" ]]; then
    # selected targets => treat as force on those
    IFS=',' read -ra arr <<<"$targets_csv"
    local in_list=""
    for t in "${arr[@]}"; do
      t="$(echo "$t" | xargs)"
      [[ -n "$t" ]] || continue
      validate_name "$t" || die "ERROR: Invalid target name in --targets: $t"
      local t_esc="${t//\'/\'\'}"
      if [[ -z "$in_list" ]]; then in_list="'${t_esc}'"; else in_list="${in_list},'${t_esc}'"; fi
    done
    [[ -n "$in_list" ]] || die "ERROR: Empty --targets list"
    list_sql="SELECT name, ip, endpoint, interval, enabled FROM targets WHERE name IN (${in_list}) ORDER BY name COLLATE NOCASE;"
    force=1
  else
    list_sql="SELECT name, ip, endpoint, interval, enabled FROM targets ORDER BY name COLLATE NOCASE;"
  fi

  # Iterate
  while IFS='|' read -r name ip endpoint interval enabled; do
      total=$((total+1))

      if [[ "$enabled" != "1" ]]; then
        disabled=$((disabled+1))
        skipped=$((skipped+1))
        continue
      fi

      # due check
      local next_due
      next_due="$(sql_one "SELECT next_due FROM runtime WHERE name='${name//\'/\'\'}' LIMIT 1;" 2>/dev/null || true)"
      next_due="${next_due:-0}"
      local is_due=0

      if [[ "$force" -eq 1 ]]; then
        is_due=1
      else
        if [[ "$next_due" =~ ^[0-9]+$ && "$next_due" -gt 0 ]]; then
          if [[ "$now" -ge "$next_due" ]]; then is_due=1; else is_due=0; fi
        else
          # first time: treat as due
          is_due=1
        fi
      fi

      if [[ "$is_due" -ne 1 ]]; then
        skipped=$((skipped+1))
        continue
      fi

      due=$((due+1))

      # ping
      local t0 t1 rtt_ms
      t0="$(date +%s%3N 2>/dev/null || true)"
      if ping -c 1 -W 1 "$ip" >/dev/null 2>&1; then
        t1="$(date +%s%3N 2>/dev/null || true)"
        if [[ -n "$t0" && -n "$t1" ]]; then
          rtt_ms=$((t1 - t0))
        else
          rtt_ms=0
        fi
        ping_ok=$((ping_ok+1))

        # curl endpoint on success
        local http_code
        http_code="$(curl -sS -o /dev/null -m 5 -w "%{http_code}" "$endpoint" || true)"
        if [[ "$http_code" =~ ^[23] ]]; then
          sent=$((sent+1))
          # status up
          sql_exec "INSERT OR REPLACE INTO runtime(name,status,next_due,last_ping,last_sent,last_rtt_ms)
                    VALUES('${name//\'/\'\'}','up', $((now + interval)), ${now}, ${now}, ${rtt_ms});"
          sql_exec "INSERT INTO history(ts,name,status,rtt_ms,curl_http)
                    VALUES(${now},'${name//\'/\'\'}','up',${rtt_ms},${http_code:-0});" >/dev/null 2>&1 || true
          echo "run: ${name} ping_ok=1 curl_http=${http_code} rtt_ms=${rtt_ms}"
          _debug_event INFO check "${name} up ping_ok=1 curl_http=${http_code} rtt_ms=${rtt_ms}"
          _debug_event INFO runner "target '${name}' up ip=${ip} rtt_ms=${rtt_ms} http=${http_code}"
        else
          curl_fail=$((curl_fail+1))
          # status down (endpoint)
          sql_exec "INSERT OR REPLACE INTO runtime(name,status,next_due,last_ping,last_sent,last_rtt_ms)
                    VALUES('${name//\'/\'\'}','down', $((now + interval)), ${now}, ${now}, ${rtt_ms});"
          sql_exec "INSERT INTO history(ts,name,status,rtt_ms,curl_http)
                    VALUES(${now},'${name//\'/\'\'}','down',${rtt_ms},${http_code:-0});" >/dev/null 2>&1 || true
          echo "run: ${name} ping_ok=1 curl_fail=1 curl_http=${http_code} rtt_ms=${rtt_ms}"
          _debug_event WARN check "${name} down ping_ok=1 curl_fail=1 curl_http=${http_code} rtt_ms=${rtt_ms}"
          _debug_event WARN runner "target '${name}' down(endpoint) ip=${ip} rtt_ms=${rtt_ms} http=${http_code}"
        fi
      else
        ping_fail=$((ping_fail+1))
        # ping fail: down
        sql_exec "INSERT OR REPLACE INTO runtime(name,status,next_due,last_ping,last_sent,last_rtt_ms)
                  VALUES('${name//\'/\'\'}','down', $((now + interval)), ${now}, 0, -1);"
        sql_exec "INSERT INTO history(ts,name,status,rtt_ms,curl_http)
                  VALUES(${now},'${name//\'/\'\'}','down',-1,0);" >/dev/null 2>&1 || true
        echo "run: ${name} ping_ok=0"
        _debug_event WARN check "${name} down ping_ok=0"
        _debug_event WARN runner "target '${name}' down(ping) ip=${ip}"
      fi
    done < <(sqlite3 -noheader -batch "${DB}" "${list_sql}")

  end_ms="$(date +%s%3N 2>/dev/null || true)"
  if [[ -n "$start_ms" && -n "$end_ms" ]]; then
    dur_ms=$((end_ms - start_ms))
  else
    dur_ms=$(( ($(now_epoch) - start_epoch) * 1000 ))
  fi

  # Print summary line (WebUI parses this)
  echo "total=${total} due=${due} skipped=${skipped} ping_ok=${ping_ok} ping_fail=${ping_fail} sent=${sent} curl_fail=${curl_fail} disabled=${disabled} force=${force} duration_ms=${dur_ms}"
  _debug_event INFO runner "run-now done total=${total} due=${due} skipped=${skipped} up=${ping_ok} down=${ping_fail} sent=${sent} curl_fail=${curl_fail} duration_ms=${dur_ms}"
  _write_debug_state
}


cmd_self_test() {
  [[ "${EUID}" -eq 0 ]] || die "ERROR: This command must be run as root. Use sudo."
  ensure_exists
  mkdir -p "$DEBUG_DIR" 2>/dev/null || true

  local ts out latest
  ts="$(date +%Y%m%d-%H%M%S)"
  out="$DEBUG_DIR/selftest-${ts}.txt"
  latest="$DEBUG_DIR/selftest-latest.txt"

  local version
  version="$(cat "${ROOT_DIR}/VERSION" 2>/dev/null || echo "unknown")"

  local gw
  gw="$(ip route show default 2>/dev/null | awk '{print $3}' | head -n1)"

  {
    echo "interheart_self_test"
    echo "time=$(date -Is)"
    echo "host=$(hostname)"
    echo "version=$version"
    echo "root_dir=${ROOT_DIR}"
    echo "state_dir=$STATE_DIR"
    echo "debug_dir=$DEBUG_DIR"
    echo "default_gateway=${gw:-}";
    echo "-"

    echo "binaries"
    echo "curl=$(command -v curl 2>/dev/null || echo missing)"
    echo "ping=$(command -v ping 2>/dev/null || echo missing)"
    echo "nmap=$(command -v nmap 2>/dev/null || echo missing)"
    if command -v nmap >/dev/null 2>&1; then
      echo "nmap_version=$(nmap --version 2>/dev/null | head -n1)"
    fi
    echo "-"

    echo "systemd"
    if command -v systemctl >/dev/null 2>&1; then
      echo "interheart.service=$(systemctl is-active interheart.service 2>/dev/null || true)"
      echo "interheart.timer=$(systemctl is-active interheart.timer 2>/dev/null || true)"
      echo "interheart-webui.service=$(systemctl is-active interheart-webui.service 2>/dev/null || true)"
    else
      echo "systemctl=missing"
    fi
    echo "-"

    echo "quick_checks"
    if [ -n "${gw:-}" ] && command -v ping >/dev/null 2>&1; then
      ping -c 1 -W 1 "$gw" >/dev/null 2>&1 && echo "ping_gateway=ok" || echo "ping_gateway=fail"
    else
      echo "ping_gateway=skipped"
    fi
    if command -v curl >/dev/null 2>&1; then
      curl -fsS -m 2 http://127.0.0.1:8088/state >/dev/null 2>&1 && echo "webui_state=ok" || echo "webui_state=fail"
    else
      echo "webui_state=skipped"
    fi
    echo "-"

    echo "discovery_meta"
    if [ -f "$DISCOVERY_META_FILE" ]; then
      sed -n '1,120p' "$DISCOVERY_META_FILE" || true
    else
      echo "(none)"
    fi
  } >"$out" 2>&1

  cp -f "$out" "$latest" 2>/dev/null || true
  echo "OK: wrote $out"
  echo "OK: latest $latest"
}

cmd_self_test_output() {
  [[ "${EUID}" -eq 0 ]] || die "ERROR: This command must be run as root. Use sudo."
  ensure_exists
  local latest="$DEBUG_DIR/selftest-latest.txt"
  if [ ! -f "$latest" ]; then
    echo "ERROR: No self-test output found (run: interheart self-test)" >&2
    exit 1
  fi
  cat "$latest"
}

cmd_debug() {
  ensure_exists
  local follow=0
  local as_json=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --follow)
        follow=1
        shift
        ;;
      --json)
        as_json=1
        shift
        ;;
      *)
        die "ERROR: Unknown arg: $1"
        ;;
    esac
  done

  _write_debug_state

  if [[ "$as_json" -eq 1 ]]; then
    # very small JSON conversion for the snapshot (best-effort)
    python3 - <<'PYS'
import json
out={}
with open('/var/lib/interheart/debug_state.txt','r',encoding='utf-8',errors='ignore') as f:
    for line in f:
        line=line.strip()
        if not line or line in ('interheart_debug_snapshot','down_targets_top8'):
            continue
        if '=' in line:
            k,v=line.split('=',1)
            out[k]=v
        else:
            # down targets lines
            out.setdefault('down_targets',[]).append(line)
print(json.dumps(out, indent=2, ensure_ascii=False))
PYS
  else
    cat "${DEBUG_STATE_FILE}" 2>/dev/null || true
  fi

  if [[ "$follow" -eq 1 ]]; then
    echo
    echo "--- tail -n 120 ${DEBUG_DIR}/runner-$(_debug_day).log ---"
    tail -n 120 "${DEBUG_DIR}/runner-$(_debug_day).log" 2>/dev/null || true
    echo
    echo "--- tail -n 120 ${DEBUG_DIR}/webui-$(_debug_day).log ---"
    tail -n 120 "${DEBUG_DIR}/webui-$(_debug_day).log" 2>/dev/null || true
    echo
    echo "--- tail -n 120 ${DEBUG_DIR}/client-$(_debug_day).log ---"
    tail -n 120 "${DEBUG_DIR}/client-$(_debug_day).log" 2>/dev/null || true
    echo
    echo "--- journalctl -u interheart.service -n 80 ---"
    journalctl -u interheart.service -n 80 --no-pager -l 2>/dev/null || true
    echo
    echo "--- journalctl -u interheart-webui.service -n 80 ---"
    journalctl -u interheart-webui.service -n 80 --no-pager -l 2>/dev/null || true
  fi
}

main() {
  local cmd="${1:-}"
  shift || true

  case "$cmd" in
    ""|-h|--help|help)
      usage
      exit 0
      ;;
    init-db)
      init_db
      echo "OK: DB ready at ${DB}"
      ;;
    add)
      [[ $# -ge 4 ]] || die "ERROR: Usage: interheart add <name> <ip> <endpoint> <interval_seconds>"
      cmd_add "$1" "$2" "$3" "$4"
      ;;
    remove)
      [[ $# -ge 1 ]] || die "ERROR: Usage: interheart remove <name>"
      cmd_remove "$1"
      ;;
    list)
      cmd_list
      ;;
    status)
      cmd_status
      ;;
    get)
      [[ $# -ge 1 ]] || die "ERROR: Usage: interheart get <name>"
      cmd_get "$1"
      ;;
    edit)
      [[ $# -ge 6 ]] || die "ERROR: Usage: interheart edit <old_name> <new_name> <ip> <endpoint> <interval_seconds> <enabled 0|1>"
      cmd_edit "$1" "$2" "$3" "$4" "$5" "$6"
      ;;
    disable)
      [[ $# -ge 1 ]] || die "ERROR: Usage: interheart disable <name>"
      cmd_disable "$1"
      ;;
    enable)
      [[ $# -ge 1 ]] || die "ERROR: Usage: interheart enable <name>"
      cmd_enable "$1"
      ;;
    set-target-interval)
      [[ $# -ge 2 ]] || die "ERROR: Usage: interheart set-target-interval <name> <interval_seconds>"
      cmd_set_interval "$1" "$2"
      ;;
    test)
      [[ $# -ge 1 ]] || die "ERROR: Usage: interheart test <name>"
      cmd_test "$1"
      ;;
    run-now)
      cmd_run_now "$@"
      ;;
    debug)
      cmd_debug "$@"
      ;;
    self-test)
      cmd_self_test "$@"
      ;;
    self-test-output)
      cmd_self_test_output "$@"
      ;;
    *)
      die "ERROR: Unknown command: ${cmd} (try: interheart --help)"
      ;;
  esac
}

main "$@"
