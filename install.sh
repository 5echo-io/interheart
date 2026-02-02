#!/usr/bin/env bash
# =============================================================================
# Copyright (c) 2026 5echo.io
# Project: interheart
# Purpose: Installer script (install/update/uninstall).
# Path: /opt/interheart/install.sh
# Created: 2026-02-01
# Last modified: 2026-02-01
# =============================================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/interheart"
STATE_DIR="/var/lib/interheart"

echo "[interheart] Installing from: ${REPO_DIR}"

# Base deps (best effort)
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y >/dev/null 2>&1 || true
  sudo apt-get install -y python3 python3-venv python3-pip nmap build-essential python3-dev libfreetype6-dev libjpeg-dev zlib1g-dev >/dev/null 2>&1 || true
fi

# 1) Ensure base dirs
sudo mkdir -p "${INSTALL_DIR}" "${STATE_DIR}"
sudo chmod 755 "${STATE_DIR}"

# 2) Install CLI -> /usr/local/bin/interheart (from repo interheart.sh)
sudo install -m 0755 "${REPO_DIR}/interheart.sh" /usr/local/bin/interheart

# 3) Init DB (creates /var/lib/interheart/state.db)
sudo /usr/local/bin/interheart init-db || true

# 3b) Debug log directory (7-day retention handled by the app; this is just setup + cleanup)
sudo mkdir -p "${STATE_DIR}/debug"
sudo chmod 755 "${STATE_DIR}/debug"

# Keep disk usage bounded across upgrades: delete debug logs older than 7 days.
# Also truncate today's logs on install/update so new versions start with a clean slate.
if command -v find >/dev/null 2>&1; then
  sudo find "${STATE_DIR}/debug" -maxdepth 1 -type f -name '*.log' -mtime +7 -delete 2>/dev/null || true
fi
today_utc="$(date -u '+%Y-%m-%d' 2>/dev/null || date '+%Y-%m-%d')"
sudo truncate -s 0 "${STATE_DIR}/debug/runner-${today_utc}.log" 2>/dev/null || true
sudo truncate -s 0 "${STATE_DIR}/debug/webui-${today_utc}.log" 2>/dev/null || true
sudo truncate -s 0 "${STATE_DIR}/debug/client-${today_utc}.log" 2>/dev/null || true
sudo bash -lc "echo '[install] version=$(cat ${REPO_DIR}/VERSION 2>/dev/null || echo -) time=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date)' >> '${STATE_DIR}/debug/runner-${today_utc}.log'" 2>/dev/null || true

# 4) WebUI venv + deps
if [ -d "${INSTALL_DIR}/webui" ]; then
  echo "[interheart] Setting up webui venv"
  sudo mkdir -p "${INSTALL_DIR}/webui"
  sudo python3 -m venv "${INSTALL_DIR}/webui/.venv"
  sudo "${INSTALL_DIR}/webui/.venv/bin/pip" install --upgrade pip
  sudo "${INSTALL_DIR}/webui/.venv/bin/pip" install -r "${INSTALL_DIR}/webui/requirements.txt"
fi

# 5) Install systemd units (FROM REPO)
echo "[interheart] Installing systemd units"
sudo cp -f "${INSTALL_DIR}/webui/systemd/interheart.service" /etc/systemd/system/interheart.service
sudo cp -f "${INSTALL_DIR}/webui/systemd/interheart.timer" /etc/systemd/system/interheart.timer
sudo cp -f "${INSTALL_DIR}/webui/systemd/interheart-webui.service" /etc/systemd/system/interheart-webui.service

# Optional sudoers (only if you use it)
if [ -f "${INSTALL_DIR}/webui/systemd/sudoers/interheart-webui" ]; then
  sudo cp -f "${INSTALL_DIR}/webui/systemd/sudoers/interheart-webui" /etc/sudoers.d/interheart-webui
  sudo chmod 0440 /etc/sudoers.d/interheart-webui
fi

# 6) Reload systemd
sudo systemctl daemon-reload

echo "[interheart] Done."
echo "Next:"
echo "  sudo systemctl enable --now interheart.timer interheart-webui.service"
