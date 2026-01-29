#!/usr/bin/env bash
set -euo pipefail

# Interheart installer (repo-based)
# Installs:
# - WebUI (venv + deps)
# - systemd units (interheart + webui)
# - sudoers rule for WebUI (optional controlled actions)
# - CLI command (interheart)
#
# Expected repo layout:
# /opt/interheart
#   install.sh
#   interheart.sh
#   config.example
#   cli/lib/interheart
#   webui/app.py
#   webui/requirements.txt
#   webui/systemd/*.service, *.timer
#   webui/systemd/sudoers/interheart-webui

REPO_DIR="/opt/interheart"
ETC_DIR="/etc/interheart"
VAR_LIB_DIR="/var/lib/interheart"
LOG_DIR="/var/log/interheart"

WEBUI_DIR="${REPO_DIR}/webui"
WEBUI_VENV="${WEBUI_DIR}/.venv"

SYSTEMD_DIR="/etc/systemd/system"
SUDOERS_DIR="/etc/sudoers.d"
BIN_DIR="/usr/local/bin"

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: Run as root (use sudo)."
    exit 1
  fi
}

say() { echo -e "==> $*"; }

install_packages() {
  say "Installing OS packages..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    ca-certificates curl git \
    python3 python3-venv python3-pip \
    sqlite3 \
    systemd
}

ensure_dirs() {
  say "Creating directories..."
  mkdir -p "${ETC_DIR}" "${VAR_LIB_DIR}" "${LOG_DIR}"
  chmod 755 "${ETC_DIR}" "${VAR_LIB_DIR}" "${LOG_DIR}"
}

install_config() {
  if [[ ! -f "${ETC_DIR}/config" ]]; then
    if [[ -f "${REPO_DIR}/config.example" ]]; then
      say "Installing default config to ${ETC_DIR}/config"
      cp "${REPO_DIR}/config.example" "${ETC_DIR}/config"
      chmod 640 "${ETC_DIR}/config"
    else
      say "WARNING: config.example not found; skipping config install"
    fi
  else
    say "Config exists: ${ETC_DIR}/config (leaving as-is)"
  fi
}

install_webui_venv() {
  say "Setting up WebUI venv..."
  if [[ ! -d "${WEBUI_DIR}" ]]; then
    echo "ERROR: Missing webui directory: ${WEBUI_DIR}"
    exit 1
  fi

  python3 -m venv "${WEBUI_VENV}"
  "${WEBUI_VENV}/bin/pip" install --upgrade pip wheel setuptools

  if [[ ! -f "${WEBUI_DIR}/requirements.txt" ]]; then
    echo "ERROR: Missing ${WEBUI_DIR}/requirements.txt"
    exit 1
  fi

  "${WEBUI_VENV}/bin/pip" install -r "${WEBUI_DIR}/requirements.txt"
}

install_systemd_units() {
  say "Installing systemd units..."
  local src_dir="${WEBUI_DIR}/systemd"

  for f in interheart.service interheart.timer interheart-webui.service; do
    if [[ ! -f "${src_dir}/${f}" ]]; then
      echo "ERROR: Missing systemd unit in repo: ${src_dir}/${f}"
      exit 1
    fi
    cp "${src_dir}/${f}" "${SYSTEMD_DIR}/${f}"
  done

  if [[ -f "${src_dir}/sudoers/interheart-webui" ]]; then
    say "Installing sudoers rule..."
    cp "${src_dir}/sudoers/interheart-webui" "${SUDOERS_DIR}/interheart-webui"
    chmod 440 "${SUDOERS_DIR}/interheart-webui"
  else
    say "No sudoers file found (ok)."
  fi
}

install_cli() {
  say "Installing CLI..."
  local cli_src="${REPO_DIR}/cli/lib/interheart"
  if [[ ! -f "${cli_src}" ]]; then
    echo "ERROR: Missing CLI entry: ${cli_src}"
    exit 1
  fi

  cp "${cli_src}" "${BIN_DIR}/interheart"
  chmod +x "${BIN_DIR}/interheart"
}

permissions_hint() {
  # Keep it simple: log + state dirs writable by root/systemd services (running as root by default in our units)
  # If later you want to run as a dedicated user, we can add users/groups and chown.
  true
}

main() {
  need_root

  if [[ ! -d "${REPO_DIR}" ]]; then
    echo "ERROR: Repo not found at ${REPO_DIR}"
    echo "Clone it first: sudo git clone <repo> ${REPO_DIR}"
    exit 1
  fi

  install_packages
  ensure_dirs
  install_config
  install_webui_venv
  install_systemd_units
  install_cli
  permissions_hint

  say "Reloading systemd daemon..."
  systemctl daemon-reload

  say "Done."
  say "Next: sudo systemctl enable --now interheart.service interheart.timer interheart-webui.service"
}

main "$@"
