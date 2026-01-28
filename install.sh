#!/usr/bin/env bash
set -euo pipefail

# interheart installer/upgrader (one command)
# - stops existing services (including legacy)
# - clones/pulls repo
# - installs deps + venv
# - installs sudoers (restricted)
# - installs systemd units (dynamic paths)
# - enables + starts interheart + webui

REPO_URL_DEFAULT="https://github.com/5echo-io/interheart.git"
INSTALL_DIR_DEFAULT="/opt/interheart"
SERVICE_USER_DEFAULT="www-data"
WEBUI_PORT_DEFAULT="8088"
WEBUI_BIND_DEFAULT="0.0.0.0"

FORCE_RESET="0"
REPO_URL="${REPO_URL_DEFAULT}"
INSTALL_DIR="${INSTALL_DIR_DEFAULT}"
SERVICE_USER="${SERVICE_USER_DEFAULT}"
WEBUI_PORT="${WEBUI_PORT_DEFAULT}"
WEBUI_BIND="${WEBUI_BIND_DEFAULT}"

usage() {
  cat <<EOF
Usage:
  sudo ./install.sh [options]

Options:
  --dir <path>        Install dir (default: ${INSTALL_DIR_DEFAULT})
  --repo <url>        Repo URL (default: ${REPO_URL_DEFAULT})
  --user <user>       Service user for WebUI (default: ${SERVICE_USER_DEFAULT})
  --bind <ip>         WebUI bind address (default: ${WEBUI_BIND_DEFAULT})
  --port <port>       WebUI port (default: ${WEBUI_PORT_DEFAULT})
  --force             Hard reset local changes on update (default: off)

Examples:
  sudo ./install.sh
  sudo ./install.sh --dir /opt/interheart --port 8088 --bind 0.0.0.0
  sudo ./install.sh --force
EOF
}

log() { echo -e "\033[1;34m[interheart]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
err() { echo -e "\033[1;31m[error]\033[0m $*" >&2; }

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    err "Kjør som root: sudo ./install.sh"
    exit 1
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir) INSTALL_DIR="$2"; shift 2 ;;
      --repo) REPO_URL="$2"; shift 2 ;;
      --user) SERVICE_USER="$2"; shift 2 ;;
      --bind) WEBUI_BIND="$2"; shift 2 ;;
      --port) WEBUI_PORT="$2"; shift 2 ;;
      --force) FORCE_RESET="1"; shift 1 ;;
      -h|--help) usage; exit 0 ;;
      *) err "Ukjent argument: $1"; usage; exit 1 ;;
    esac
  done
}

stop_services() {
  log "Stopper evt. gamle services (hvis de finnes)…"
  # New names
  systemctl disable --now interheart-webui.service 2>/dev/null || true
  systemctl disable --now interheart.timer 2>/dev/null || true
  systemctl disable --now interheart.service 2>/dev/null || true

  # Legacy/backwards
  systemctl disable --now uptimekuma-webui.service 2>/dev/null || true
  systemctl disable --now uptimerobot-heartbeat-webui.service 2>/dev/null || true
  systemctl disable --now uptime-kuma.service 2>/dev/null || true
  systemctl disable --now uptimekuma.service 2>/dev/null || true
  systemctl disable --now uptimerobot-heartbeat.service 2>/dev/null || true

  # Kill lingering old python bound to 8088 (best effort)
  fuser -k "${WEBUI_PORT}/tcp" 2>/dev/null || true
}

install_packages() {
  log "Installerer pakker (git, curl, ping, python venv)…"
  apt-get update -y
  apt-get install -y \
    git curl iputils-ping \
    python3 python3-venv python3-pip \
    ca-certificates
}

clone_or_update_repo() {
  if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
    log "Cloner repo → ${INSTALL_DIR}"
    rm -rf "${INSTALL_DIR}" || true
    git clone "${REPO_URL}" "${INSTALL_DIR}"
    return
  fi

  log "Oppdaterer repo i ${INSTALL_DIR}"
  pushd "${INSTALL_DIR}" >/dev/null

  if [[ "${FORCE_RESET}" == "1" ]]; then
    warn "--force: Hard reset mot origin/main (lokale endringer blir kastet)"
    git fetch origin
    git reset --hard origin/main
    git clean -fd
  else
    if ! git diff --quiet || ! git diff --cached --quiet; then
      warn "Repo har lokale endringer → stasher før pull"
      git stash push -m "auto-stash before pull $(date -Is)" || true
    fi
    git pull --ff-only
  fi

  popd >/dev/null
}

install_cli_symlink() {
  log "Setter opp CLI symlink: /usr/local/bin/interheart"
  ln -sf "${INSTALL_DIR}/interheart.sh" /usr/local/bin/interheart
  chmod +x "${INSTALL_DIR}/interheart.sh" || true
}

read_version() {
  if [[ -f "${INSTALL_DIR}/VERSION" ]]; then
    cat "${INSTALL_DIR}/VERSION" | tr -d '\r\n' || true
  else
    echo "0.0.0"
  fi
}

setup_logfile_fallback() {
  log "Sikrer fallback-loggfil: /var/log/interheart.log"
  touch /var/log/interheart.log
  chmod 0644 /var/log/interheart.log || true
}

setup_webui_venv() {
  log "Setter opp WebUI venv + requirements"
  local webui_dir="${INSTALL_DIR}/webui"
  local venv_dir="${webui_dir}/.venv"
  local pip="${venv_dir}/bin/pip"

  if [[ ! -d "${webui_dir}" ]]; then
    err "Fant ikke webui-mappe: ${webui_dir}"
    exit 1
  fi

  python3 -m venv "${venv_dir}"
  "${pip}" install --upgrade pip
  if [[ -f "${webui_dir}/requirements.txt" ]]; then
    "${pip}" install -r "${webui_dir}/requirements.txt"
  else
    warn "Fant ikke webui/requirements.txt – installerer Flask manuelt"
    "${pip}" install Flask
  fi

  chown -R "${SERVICE_USER}:${SERVICE_USER}" "${webui_dir}" || true
}

install_systemd_units_dynamic() {
  log "Installerer systemd units (dynamic paths)"
  mkdir -p /etc/systemd/system

  # interheart runner
  cat > /etc/systemd/system/interheart.service <<EOF
[Unit]
Description=5echo interheart runner (manual runs)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/interheart run
EOF

  # interheart timer
  cat > /etc/systemd/system/interheart.timer <<EOF
[Unit]
Description=5echo interheart scheduler

[Timer]
OnBootSec=10s
OnUnitActiveSec=10s
AccuracySec=1s
Unit=interheart.service

[Install]
WantedBy=timers.target
EOF

  # webui service (dynamic WorkingDirectory + ExecStart)
  cat > /etc/systemd/system/interheart-webui.service <<EOF
[Unit]
Description=5echo interheart Web UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}/webui

Environment=PYTHONUNBUFFERED=1
Environment=INTERHEART_DIR=${INSTALL_DIR}

# Env settes i override.conf av install.sh (WEBUI_BIND + WEBUI_PORT)
ExecStart=${INSTALL_DIR}/webui/.venv/bin/python ${INSTALL_DIR}/webui/app.py

Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
}

install_sudoers() {
  log "Installerer sudoers (begrenset) for WebUI"
  local sudoers_path="/etc/sudoers.d/interheart-webui"

  cat > "${sudoers_path}" <<EOF
# interheart webui sudoers
# Allow only interheart + journalctl for tag "interheart"

Cmnd_Alias INTERHEART = /usr/local/bin/interheart *
Cmnd_Alias INTERHEART_JOURNAL = /usr/bin/journalctl -t interheart -n * --no-pager --output=short-iso

${SERVICE_USER} ALL=(root) NOPASSWD: INTERHEART, INTERHEART_JOURNAL
EOF

  chmod 0440 "${sudoers_path}"
  visudo -c -f "${sudoers_path}"
}

enable_start() {
  log "Starter interheart + WebUI"
  mkdir -p /etc/systemd/system/interheart-webui.service.d
  cat > /etc/systemd/system/interheart-webui.service.d/override.conf <<EOF
[Service]
Environment=WEBUI_BIND=${WEBUI_BIND}
Environment=WEBUI_PORT=${WEBUI_PORT}
EOF

  systemctl daemon-reload

  systemctl enable --now interheart.service
  systemctl enable --now interheart.timer
  systemctl enable --now interheart-webui.service

  log "Status:"
  systemctl --no-pager --full status interheart.service || true
  systemctl --no-pager --full status interheart.timer || true
  systemctl --no-pager --full status interheart-webui.service || true
}

main() {
  need_root
  parse_args "$@"

  log "Config:"
  echo "  Repo: ${REPO_URL}"
  echo "  Dir : ${INSTALL_DIR}"
  echo "  User: ${SERVICE_USER}"
  echo "  Web : ${WEBUI_BIND}:${WEBUI_PORT}"
  echo "  Force reset: ${FORCE_RESET}"

  stop_services
  install_packages
  clone_or_update_repo
  install_cli_symlink
  setup_logfile_fallback
  setup_webui_venv
  install_systemd_units_dynamic
  install_sudoers
  enable_start

  local ver
  ver="$(read_version)"
  log "Ferdig ✅ interheart ${ver}"
  log "WebUI: http://${WEBUI_BIND}:${WEBUI_PORT}"
}

main "$@"
