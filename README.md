# 5echo – UptimeRobot Heartbeat Bridge

Overvåk intern infrastruktur med UptimeRobot Heartbeat-monitorer.

**Hvordan det funker:**
- Scriptet leser en liste targets (name, ip, heartbeat-url)
- Ping'er hver IP
- Hvis ping OK → sender *individuell* heartbeat til UptimeRobot
- Hvis ping feiler → sender ikke heartbeat → UptimeRobot varsler når heartbeat uteblir

## Installer på server
```bash
sudo apt update
sudo apt install -y git curl iputils-ping
sudo git clone <DIN_GITHUB_REPO_URL> /opt/uptimerobot-heartbeat
cd /opt/uptimerobot-heartbeat
sudo chmod +x install.sh
sudo ./install.sh
