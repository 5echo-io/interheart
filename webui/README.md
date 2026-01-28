# Web UI (Flask)

Enkel webside for:
- list/add/remove targets
- kjøre sjekk nå
- se siste logs

## Install
```bash
sudo apt update
sudo apt install -y python3 python3-venv
cd /opt/uptimerobot-heartbeat/webui
sudo python3 -m venv .venv
sudo ./.venv/bin/pip install flask
