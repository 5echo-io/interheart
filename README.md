# interheart

**interheart** is a lightweight heartbeat + ping monitor built for real operations.

It’s made for small to mid-sized environments where you want a clean overview of what is up, what is starting, what has heartbeat issues, and what is not responding — without the noise.

Powered by **5echo.io**.

---

## Strengths

- **Fast overview**: OK / STARTING / HEARTBEAT FAILED / NOT RESPONDING / DISABLED
- **Simple targets**: name + IP (+ optional endpoint URL) with interval control
- **Operator-friendly UI**: bulk actions, quick test, clear timestamps
- **Readable logs**: timestamps included and cleaned for humans
- **Lightweight**: runs great on small servers and Raspberry Pi

---

## Install

```bash
sudo git clone https://github.com/5echo-io/interheart.git /opt/interheart
cd /opt/interheart
sudo bash install.sh

sudo systemctl daemon-reload
sudo systemctl enable --now interheart.timer interheart-webui.service
```

---

## Update

```bash
sudo systemctl stop interheart.timer interheart.service interheart-webui.service 2>/dev/null || true

cd /tmp
sudo rm -rf /opt/interheart
sudo git clone https://github.com/5echo-io/interheart.git /opt/interheart

cd /opt/interheart
sudo bash install.sh

sudo systemctl daemon-reload
sudo systemctl enable --now interheart.timer interheart-webui.service
```

---

## Uninstall

```bash
sudo systemctl stop interheart.timer interheart.service interheart-webui.service 2>/dev/null || true
sudo systemctl disable interheart.timer interheart.service interheart-webui.service 2>/dev/null || true

sudo rm -rf /opt/interheart

sudo rm -f /etc/systemd/system/interheart.service /etc/systemd/system/interheart.timer /etc/systemd/system/interheart-webui.service
sudo systemctl daemon-reload
```
