#!/usr/bin/env bash
set -euo pipefail

# interheart database helpers
# All SQLite access is centralized here

db() {
  sqlite3 "$STATE_DB" "$@"
}

db_init() {
  ensure_dirs
}

db_target_exists() {
  local name="$1"
  db "SELECT 1 FROM targets WHERE name='$name' LIMIT 1;" | grep -q 1
}

db_add_target() {
  local name="$1" ip="$2" endpoint="$3" interval="$4"
  db <<EOF
INSERT INTO targets (name, ip, endpoint, interval, enabled)
VALUES ('$name', '$ip', '$endpoint', $interval, 1);
EOF
}

db_remove_target() {
  local name="$1"
  db "DELETE FROM targets WHERE name='$name';"
  db "DELETE FROM state WHERE name='$name';"
}

db_set_interval() {
  local name="$1" interval="$2"
  db "UPDATE targets SET interval=$interval WHERE name='$name';"
}

db_set_enabled() {
  local name="$1" enabled="$2"
  db "UPDATE targets SET enabled=$enabled WHERE name='$name';"
}

db_list_targets() {
  db <<EOF
SELECT
  t.name,
  t.ip,
  t.interval,
  t.enabled,
  t.endpoint,
  s.last_status,
  s.last_ping,
  s.last_response,
  s.last_latency,
  s.next_due
FROM targets t
LEFT JOIN state s ON t.name = s.name
ORDER BY t.name ASC;
EOF
}

db_get_target() {
  local name="$1"
  db <<EOF
SELECT
  t.name,
  t.ip,
  t.endpoint,
  t.interval,
  t.enabled,
  s.last_status,
  s.last_ping,
  s.last_response,
  s.last_latency,
  s.next_due
FROM targets t
LEFT JOIN state s ON t.name = s.name
WHERE t.name='$name'
LIMIT 1;
EOF
}

db_update_state() {
  local name="$1"
  local status="$2"
  local ping="$3"
  local response="$4"
  local latency="$5"
  local next_due="$6"

  db <<EOF
INSERT INTO state (name, last_status, last_ping, last_response, last_latency, next_due)
VALUES ('$name', '$status', $ping, $response, $latency, $next_due)
ON CONFLICT(name) DO UPDATE SET
  last_status=excluded.last_status,
  last_ping=excluded.last_ping,
  last_response=excluded.last_response,
  last_latency=excluded.last_latency,
  next_due=excluded.next_due;
EOF
}
