#!/usr/bin/env bash
# =============================================================================
# Copyright (c) 2026 5echo.io
# Project: interheart
# Purpose: CLI command implementations and dispatcher.
# Path: /opt/interheart/cli/lib/commands.sh
# Created: 2026-02-01
# Last modified: 2026-02-01
# =============================================================================

set -euo pipefail

# interheart CLI commands
# Depends on: core.sh + db.sh

cmd_add() {
  require_root
  db_init

  local name="${1:-}"
  local ip="${2:-}"
  local endpoint="${3:-}"
  local interval="${4:-$DEFAULT_INTERVAL}"

  [[ -z "$name" || -z "$ip" || -z "$endpoint" ]] && {
    echo "Usage: interheart add <name> <ip> <endpoint_url> [interval]"
    exit 1
  }

  validate_name "$name"
  validate_ip "$ip"
  validate_url "$endpoint"
  validate_interval "$interval"

  if db_target_exists "$name"; then
    echo "Target already exists: $name" >&2
    exit 1
  fi

  db_add_target "$name" "$ip" "$endpoint" "$interval"
  echo "Added target: $name"
}

cmd_remove() {
  require_root
  db_init

  local name="${1:-}"
  [[ -z "$name" ]] && {
    echo "Usage: interheart remove <name>"
    exit 1
  }

  validate_name "$name"

  if ! db_target_exists "$name"; then
    echo "Target not found: $name" >&2
    exit 1
  fi

  db_remove_target "$name"
  echo "Removed target: $name"
}

cmd_enable() {
  require_root
  db_init

  local name="${1:-}"
  validate_name "$name"
  db_set_enabled "$name" 1
  echo "Enabled: $name"
}

cmd_disable() {
  require_root
  db_init

  local name="${1:-}"
  validate_name "$name"
  db_set_enabled "$name" 0
  echo "Disabled: $name"
}

cmd_list() {
  require_root
  db_init

  printf "%-24s %-15s %-9s %-7s %s\n" "NAME" "IP" "INTERVAL" "ENABLED" "ENDPOINT"
  printf "%-24s %-15s %-9s %-7s %s\n" "------------------------" "---------------" "--------" "-------" "--------"

  db_list_targets | while IFS='|' read -r \
    name ip interval enabled endpoint \
    last_status last_ping last_response last_latency next_due
  do
    printf "%-24s %-15s %-9ss %-7s %s\n" \
      "$name" "$ip" "$interval" "$enabled" "$endpoint"
  done
}

cmd_status() {
  require_root
  db_init

  printf "%-24s %-10s %-10s %-10s %-10s %-10s\n" \
    "NAME" "STATUS" "PING" "RESP" "LAT(ms)" "NEXT_DUE"

  db_list_targets | while IFS='|' read -r \
    name ip interval enabled endpoint \
    last_status last_ping last_response last_latency next_due
  do
    printf "%-24s %-10s %-10s %-10s %-10s %-10s\n" \
      "$name" \
      "${last_status:-unknown}" \
      "${last_ping:-0}" \
      "${last_response:-0}" \
      "${last_latency:-0}" \
      "${next_due:-0}"
  done
}

cmd_debug() {
  require_root
  db_init

  local mode="${1:-}"

  echo "interheart debug"
  echo "- version:  $(cat /opt/interheart/VERSION 2>/dev/null || cat ./VERSION 2>/dev/null || echo '-')"
  echo "- hostname: $(hostname 2>/dev/null || true)"
  echo "- time:     $(date -Is 2>/dev/null || true)"
  echo

  echo "== Services =="
  for svc in interheart.timer interheart.service interheart-webui.service; do
    if command -v systemctl >/dev/null 2>&1; then
      local active="-"
      active="$(systemctl is-active "$svc" 2>/dev/null || true)"
      printf "%-26s %s\n" "$svc" "$active"
    else
      printf "%-26s %s\n" "$svc" "systemctl not found"
    fi
  done

  echo
  echo "== Targets (quick status) =="
  cmd_status || true

  echo
  echo "== Last runner lines (interheart.service) =="
  if [[ "$mode" == "follow" || "$mode" == "-f" || "$mode" == "--follow" ]]; then
    journalctl -u interheart.service -n 50 -f --no-pager || true
    return 0
  fi
  journalctl -u interheart.service -n 60 --no-pager || true

  echo
  echo "== Last WebUI lines (interheart-webui.service) =="
  journalctl -u interheart-webui.service -n 60 --no-pager || true

  echo
  echo "Tip: 'sudo interheart debug --follow' to tail runner logs live."
}


_selftest_latest_log() {
  ls -1t /var/lib/interheart/debug/selftest-*.log 2>/dev/null | head -n 1
}


cmd_self_test() {
  require_root
  db_init

  mkdir -p /var/lib/interheart/debug

  local ts SELFTEST_LOG
  ts="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
  SELFTEST_LOG="/var/lib/interheart/debug/selftest-${ts}.log"

  {
    echo "interheart self-test"
    echo "time_utc=${ts}"
    echo "host=$(hostname)"
    echo "version=$(cat /opt/interheart/VERSION 2>/dev/null || echo 'unknown')"
    echo "-"
  } >"${SELFTEST_LOG}"

  local ok=0 fail=0

  _st() {
    echo "$1" | tee -a "${SELFTEST_LOG}"
  }

  _st "[1] Files"
  if [ -f /opt/interheart/VERSION ]; then
    ok=$((ok + 1)); _st "  OK: VERSION exists"
  else
    fail=$((fail + 1)); _st "  FAIL: VERSION missing (/opt/interheart/VERSION)"
  fi

  if [ -f "${DB_PATH}" ]; then
    ok=$((ok + 1)); _st "  OK: DB exists (${DB_PATH})"
  else
    fail=$((fail + 1)); _st "  FAIL: DB missing (${DB_PATH})"
  fi

  _st "[2] Services"
  if systemctl is-active --quiet interheart-webui.service; then
    ok=$((ok + 1)); _st "  OK: interheart-webui.service active"
  else
    fail=$((fail + 1)); _st "  FAIL: interheart-webui.service not active"
  fi
  if systemctl is-active --quiet interheart.timer; then
    ok=$((ok + 1)); _st "  OK: interheart.timer active"
  else
    fail=$((fail + 1)); _st "  FAIL: interheart.timer not active"
  fi

  _st "[3] WebUI health"
  if curl -fsS --max-time 2 http://127.0.0.1:8088/state >/dev/null 2>&1; then
    ok=$((ok + 1)); _st "  OK: GET /state responds"
  else
    fail=$((fail + 1)); _st "  FAIL: GET /state did not respond on 127.0.0.1:8088"
  fi

  _st "[4] DB integrity (quick)"
  if sqlite3 "${DB_PATH}" "PRAGMA quick_check;" 2>/dev/null | grep -qi '^ok'; then
    ok=$((ok + 1)); _st "  OK: sqlite quick_check"
  else
    fail=$((fail + 1)); _st "  FAIL: sqlite quick_check"
  fi

  _st "-"
  _st "result_ok=${ok}"
  _st "result_fail=${fail}"
  _st "log=${SELFTEST_LOG}"

  echo
  echo "Self-test complete: ok=${ok} fail=${fail}"
  echo "Log: ${SELFTEST_LOG}"

  if [ "${fail}" -ne 0 ]; then
    return 1
  fi
}


cmd_self_test_output() {
  require_root
  local latest
  latest="$(_selftest_latest_log)"
  if [ -z "${latest}" ]; then
    echo "No self-test logs found in /var/lib/interheart/debug/"
    return 1
  fi
  cat "${latest}"
}

cmd_help() {
  cat <<EOF
interheart CLI

Commands:
  add <name> <ip> <endpoint> [interval]
  remove <name>
  enable <name>
  disable <name>
  list
  status
  debug [--follow]
  self-test
  self-test-output
EOF
}

main() {
  local cmd="${1:-help}"
  shift || true

  case "$cmd" in
    add)      cmd_add "$@" ;;
    remove)   cmd_remove "$@" ;;
    enable)   cmd_enable "$@" ;;
    disable)  cmd_disable "$@" ;;
    list)     cmd_list ;;
    status)   cmd_status ;;
    debug)    cmd_debug "$@" ;;
    self-test) cmd_self_test ;;
    self-test-output) cmd_self_test_output ;;
    help|-h|--help) cmd_help ;;
    *)
      echo "Unknown command: $cmd" >&2
      cmd_help
      exit 1
      ;;
  esac
}
