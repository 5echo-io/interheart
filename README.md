# interheart (5echo)

**ping → endpoint relay**

- Pinger interne targets (IP)
- Hvis ping er OK → sender request til target sitt endpoint (HTTP GET)
- Hvis ping feiler → sender ikke request

Endpoint kan være hva som helst:
- UptimeRobot Heartbeat
- Uptime Kuma push endpoint
- Zapier webhook
- intern API

## Install (server)
```bash
sudo apt update
sudo apt install -y git curl iputils-ping
sudo git clone https://github.com/5echo-io/interheart.git /opt/interheart
cd /opt/interheart
sudo chmod +x install.sh interheart.sh
sudo ./install.sh
