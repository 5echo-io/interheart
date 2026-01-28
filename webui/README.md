# interheart WebUI

Modern darkmode WebUI for å:
- liste/legge til/fjerne targets
- teste target
- kjøre sjekk nå
- endre intervall (systemd timer)

**Ingen login** – default bindes WebUI til `127.0.0.1:8088`.

## Install dependencies
```bash
sudo apt update
sudo apt install -y python3 python3-venv
cd /opt/interheart/webui
sudo python3 -m venv .venv
sudo /opt/interheart/webui/.venv/bin/pip install flask
