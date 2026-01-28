#!/usr/bin/env bash
set -euo pipefail

APP="interheart"
BASE_DIR="/opt/${APP}"
WEBUI_DIR="${BASE_DIR}/webui"
VENV_DIR="${WEBUI_DIR}/.venv"
SERVICE_SRC="${WEBUI_DIR}/systemd/${APP}-webui.service"
SERVICE_DST="/etc/systemd/system/${APP}-webui.service"

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
  fi
}

main() {
  require_root

  if [[ ! -d "${BASE_DIR}" ]]; then
    echo "ERROR: ${BASE_DIR} not found. Clone repo to ${BASE_DIR} first."
    exit 1
  fi

  sudo apt update
  sudo apt install -y python3 python3-venv python3-pip

  # venv
  mkdir -p "${WEBUI_DIR}"
  if [[ ! -d "${VENV_DIR}" ]]; then
    python3 -m venv "${VENV_DIR}"
  fi
  "${VENV_DIR}/bin/pip" install --upgrade pip
  "${VENV_DIR}/bin/pip" install flask

  # install CLI
  if [[ -f "${BASE_DIR}/interheart.sh" ]]; then
    cp -f "${BASE_DIR}/interheart.sh" /usr/local/bin/interheart
    chmod 755 /usr/local/bin/interheart
  fi

  # systemd service
  if [[ ! -f "${SERVICE_SRC}" ]]; then
    echo "ERROR: Missing ${SERVICE_SRC}"
    exit 1
  fi
  cp -f "${SERVICE_SRC}" "${SERVICE_DST}"

  systemctl daemon-reload
  systemctl enable --now "${APP}-webui.service"
  systemctl restart "${APP}-webui.service"

  echo ""
  echo "OK: ${APP} WebUI installed and running"
  echo "Check: sudo systemctl status ${APP}-webui --no-pager"
}

main "$@"
