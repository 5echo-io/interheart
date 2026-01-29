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
    help|-h|--help) cmd_help ;;
    *)
      echo "Unknown command: $cmd" >&2
      cmd_help
      exit 1
      ;;
  esac
}
