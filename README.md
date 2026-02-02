# interheart

interheart is an internal monitoring agent for on‑prem environments.

It continuously checks local targets (ping + optional HTTP/S endpoint) and can send **heartbeat signals (UP/DOWN)** to external or internal monitors like **Uptime Kuma**, **UptimeRobot**, or any endpoint that accepts heartbeat/webhook style updates.

Powered by **5echo.io**.

---

## What interheart is

- **Agent-first**: runs close to your systems (LAN/VLAN), where ICMP and internal endpoints actually make sense.
- **Simple target model**: name + IP, and optional endpoint URL for “I’m alive” heartbeats.
- **Operator-friendly WebUI**: clean status overview, bulk actions, logs, and quick debugging.

Typical use: keep “local truth” locally, and forward a simple UP/DOWN signal to whatever you use for global dashboards.

---

## How it works

1. interheart reads your configured targets
2. on schedule (systemd timer) it:
   - pings each enabled target
   - if ping is OK, it can call the configured endpoint URL (heartbeat)
3. it stores runtime state locally and exposes it in the WebUI
4. you can also run checks on demand from the WebUI (“Run now” / “Test”)

---

## Integrations

interheart is designed to fit into existing monitoring stacks:

- **Uptime Kuma**: send a heartbeat to a *Push* monitor URL.
- **UptimeRobot**: use their heartbeat-style monitor URL.
- **Custom receivers**: any HTTP endpoint that interprets simple UP/DOWN calls.

You decide what the endpoint means per target.

---

## WebUI highlights

- Clear statuses: **OK**, **STARTING..**, **HEARTBEAT FAILED**, **NOT RESPONDING**, **DISABLED**
- Target actions: **Enable/Disable/Test/Edit/Delete**
- Bulk actions for faster ops
- Network scan to discover devices on your local subnets (requires `nmap`)
- Logs viewer with filters and export (CSV/XLSX/PDF)

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

---

## Notes

- interheart is intended for **local operations** (LAN/VLAN visibility).
- Keep endpoints private when possible, and treat heartbeat URLs as secrets.

