#!/usr/bin/env bash
set -euo pipefail

# Simple installer for repo-based deployment:
# - copies script into /usr/local/bin/uptimerobot-heartbeat
# - installs systemd timer/service
# - creates empty config file (root-only)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${SCRIPT_DIR}/uptimerobot-heartbeat.sh"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Kjør som root: sudo ./install.sh" >&2
  exit 1
fi

chmod +x "$SRC"
# Use the script's built-in installer
"$SRC" install

echo ""
echo "OK. Neste:"
echo "  sudo /usr/local/bin/uptimerobot-heartbeat add <name> <ip> <heartbeat_url>"
echo "  sudo /usr/local/bin/uptimerobot-heartbeat enable"
