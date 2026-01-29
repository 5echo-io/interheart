#!/usr/bin/env bash
set -euo pipefail

# interheart CLI
# Stores state in /var/lib/interheart/state.db
# Requires: sqlite3, curl, ping

STATE_DIR="/var/lib/interheart"
DB="${STATE_DIR}/state.db"
LOG_TAG="interheart"

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
    "SELECT ip, endpoint FROM targets WHERE name='${n_esc}' LIMIT 1;")" || true
  [[ -n "$row" ]] || die "ERROR: Not found: ${name}"

  local ip endpoint
  IFS='|' read -r ip endpoint <<<"$row"

  local ping_ok=0 ping_ms=-1
  if ping -c 1 -W 1 "$ip" >/dev/null 2>&1; then
    ping_ok=1
    # crude RTT: use ping output if possible (not required)
    ping_ms=0
  fi

  if [[ "$ping_ok" -eq 1 ]]; then
    # curl endpoint
    local code
    code="$(curl -sS -o /dev/null -m 3 -w "%{http_code}" "$endpoint" || true)"
    if [[ "$code" =~ ^2|3 ]]; then
      echo "OK: ping_ok=1 curl_http=${code}"
    else
      echo "WARN: ping_ok=1 curl_http=${code}"
    fi
  else
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

  local total=0 due=0 skipped=0 ping_ok=0 ping_fail=0 sent=0 curl_fail=0 disabled=0

  local now
  now="$start_epoch"

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
  sqlite3 -noheader -batch "${DB}" "${list_sql}" \
  | while IFS='|' read -r name ip endpoint interval enabled; do
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
        if [[ "$http_code" =~ ^2|3 ]]; then
          sent=$((sent+1))
          # status up
          sql_exec "INSERT OR REPLACE INTO runtime(name,status,next_due,last_ping,last_sent,last_rtt_ms)
                    VALUES('${name//\'/\'\'}','up', $((now + interval)), ${now}, ${now}, ${rtt_ms});"
          echo "run: ${name} ping_ok=1 curl_http=${http_code} rtt_ms=${rtt_ms}"
        else
          curl_fail=$((curl_fail+1))
          # status down (endpoint)
          sql_exec "INSERT OR REPLACE INTO runtime(name,status,next_due,last_ping,last_sent,last_rtt_ms)
                    VALUES('${name//\'/\'\'}','down', $((now + interval)), ${now}, ${now}, ${rtt_ms});"
          echo "run: ${name} ping_ok=1 curl_fail=1 curl_http=${http_code} rtt_ms=${rtt_ms}"
        fi
      else
        ping_fail=$((ping_fail+1))
        # ping fail: down
        sql_exec "INSERT OR REPLACE INTO runtime(name,status,next_due,last_ping,last_sent,last_rtt_ms)
                  VALUES('${name//\'/\'\'}','down', $((now + interval)), ${now}, 0, -1);"
        echo "run: ${name} ping_ok=0"
      fi
    done

  end_ms="$(date +%s%3N 2>/dev/null || true)"
  if [[ -n "$start_ms" && -n "$end_ms" ]]; then
    dur_ms=$((end_ms - start_ms))
  else
    dur_ms=$(( ($(now_epoch) - start_epoch) * 1000 ))
  fi

  # Print summary line (WebUI parses this)
  echo "total=${total} due=${due} skipped=${skipped} ping_ok=${ping_ok} ping_fail=${ping_fail} sent=${sent} curl_fail=${curl_fail} disabled=${disabled} force=${force} duration_ms=${dur_ms}"
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
    *)
      die "ERROR: Unknown command: ${cmd} (try: interheart --help)"
      ;;
  esac
}

main "$@"
