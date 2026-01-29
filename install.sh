#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/interheart"
STATE_DIR="/var/lib/interheart"

echo "[interheart] Installing from: ${REPO_DIR}"

# 1) Ensure base dirs
sudo mkdir -p "${INSTALL_DIR}" "${STATE_DIR}"
sudo chmod 755 "${STATE_DIR}"

# 2) Install CLI -> /usr/local/bin/interheart (from repo interheart.sh)
sudo install -m 0755 "${REPO_DIR}/interheart.sh" /usr/local/bin/interheart

# 3) Init DB (creates /var/lib/interheart/state.db)
sudo /usr/local/bin/interheart init-db || true

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
