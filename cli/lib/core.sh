#!/usr/bin/env bash
set -euo pipefail

# interheart core helpers
# Felles funksjoner brukt av CLI-kommandoene

APP_NAME="interheart"

STATE_DIR="/var/lib/interheart"
STATE_DB="${STATE_DIR}/state.db"
CONFIG_FILE="/etc/5echo/interheart.conf"

DEFAULT_INTERVAL=60

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "This command must be run as root. Use sudo." >&2
    exit 1
  fi
}

ensure_dirs() {
  mkdir -p "$STATE_DIR"
  chmod 755 "$STATE_DIR"

  if [[ ! -f "$STATE_DB" ]]; then
    sqlite3 "$STATE_DB" <<EOF
CREATE TABLE IF NOT EXISTS targets (
  name TEXT PRIMARY KEY,
  ip TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  interval INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS state (
  name TEXT PRIMARY KEY,
  next_due INTEGER,
  last_status TEXT,
  last_ping INTEGER,
  last_response INTEGER,
  last_latency INTEGER
);
EOF
  fi
}

validate_name() {
  [[ "$1" =~ ^[a-zA-Z0-9._-]+$ ]] || {
    echo "Invalid name: $1" >&2
    exit 1
  }
}

validate_ip() {
  [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || {
    echo "Invalid IP address: $1" >&2
    exit 1
  }
}

validate_url() {
  [[ "$1" =~ ^https?:// ]] || {
    echo "Invalid URL (must start with http:// or https://): $1" >&2
    exit 1
  }
}

validate_interval() {
  local v="$1"
  [[ "$v" =~ ^[0-9]+$ ]] || {
    echo "Interval must be a number (seconds)" >&2
    exit 1
  }
  (( v >= 10 && v <= 86400 )) || {
    echo "Interval must be between 10 and 86400 seconds" >&2
    exit 1
  }
}
