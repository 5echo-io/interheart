# interheart (5echo)

**ping → endpoint relay**

- Pinger interne targets (IP)
- Hver target har eget **intervall**
- Når en target er “due”:
  - Ping OK → sender request til target sitt endpoint (HTTP GET)
  - Ping feiler → sender ikke request
- Systemd timer kjører ofte (default 10s), men selve per-target intervallstyringen skjer i `interheart run`.

Endpoint kan være hva som helst:
- UptimeRobot Heartbeat
- Uptime Kuma push endpoint
- Zapier webhook
- intern API

---

## Install (server)
```bash
sudo apt update
sudo apt install -y git curl iputils-ping
sudo git clone https://github.com/5echo-io/interheart.git /opt/interheart
cd /opt/interheart
sudo chmod +x install.sh interheart.sh
sudo ./install.sh
