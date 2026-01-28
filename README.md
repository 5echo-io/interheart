# 5echo - UpTimeRobot Heartbeat Bridge

Dette scriptet lar deg overvåke intern infrastruktur med UpTimeRobot Heartbeats, ved å:
- ping'e interne IP-adresser
- sende individuell heartbeat per IP hvis ping er OK
- ikke sende heartbeat hvis ping feiler (UpTimeRobot varsler når heartbeat uteblir)

## Install
```bash
sudo ./uptimerobot-heartbeat.sh install
