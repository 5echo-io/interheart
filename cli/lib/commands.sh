#!/usr/bin/env bash
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
    help|-h|--help) cmd_help ;;
    *)
      echo "Unknown command: $cmd" >&2
      cmd_help
      exit 1
      ;;
  esac
}
