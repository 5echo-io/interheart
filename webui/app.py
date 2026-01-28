from flask import Flask, request, render_template_string, Response
import os
import subprocess

APP = Flask(__name__)

CLI = "/usr/local/bin/uptimerobot-heartbeat"

USER = os.environ.get("WEBUI_USER", "admin")
PASS = os.environ.get("WEBUI_PASS", "change-me")

TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>5echo – UptimeRobot Heartbeat</title>
  <style>
    body { font-family: sans-serif; margin: 24px; }
    .card { border: 1px solid #ddd; border-radius: 14px; padding: 16px; margin-bottom: 16px; }
    input { padding: 10px; margin: 6px 0; width: 520px; max-width: 100%; }
    button { padding: 10px 14px; cursor: pointer; border-radius: 10px; }
    pre { background: #f6f6f6; padding: 12px; border-radius: 14px; overflow-x: auto; }
  </style>
</head>
<body>
  <h2>5echo – UptimeRobot Heartbeat Bridge</h2>

  {% if message %}
    <div class="card"><b>{{ message }}</b></div>
  {% endif %}

  <div class="card">
    <form method="post" action="/run-now">
      <button type="submit">Kjør sjekk nå</button>
    </form>
  </div>

  <div class="card">
    <h3>Legg til target</h3>
    <form method="post" action="/add">
      <div><input name="name" placeholder="name (f.eks anl-0161-core-gw)" required></div>
      <div><input name="ip" placeholder="ip (f.eks 10.5.0.1)" required></div>
      <div><input name="url" placeholder="uptimerobot heartbeat url" required></div>
      <button type="submit">Legg til</button>
    </form>
  </div>

  <div class="card">
    <h3>Targets</h3>
    <pre>{{ targets }}</pre>
  </div>

  <div class="card">
    <h3>Fjern target</h3>
    <form method="post" action="/remove">
      <div><input name="name" placeholder="name" required></div>
      <button type="submit">Fjern</button>
    </form>
  </div>

  <div class="card">
    <h3>Siste logs</h3>
    <pre>{{ logs }}</pre>
  </div>
</body>
</html>
"""

def check_auth():
    auth = request.authorization
    return auth and auth.username == USER and auth.password == PASS

def require_auth():
    return Response("Auth required", 401, {"WWW-Authenticate": 'Basic realm="5echo"'})

def run_cmd(args):
    cmd = ["sudo", CLI] + args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, out.strip()

def get_logs():
    try:
        p = subprocess.run(
            ["journalctl", "-t", "uptimerobot-heartbeat", "-n", "60", "--no-pager"],
            capture_output=True, text=True
        )
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    except Exception:
        pass
    return "(ingen journald-logger tilgjengelig)"

@APP.before_request
def auth_gate():
    if not check_auth():
        return require_auth()

@APP.get("/")
def index():
    _, targets = run_cmd(["list"])
    logs = get_logs()
    return render_template_string(TEMPLATE, targets=targets, logs=logs, message="")

@APP.post("/add")
def add():
    name = request.form.get("name", "")
    ip = request.form.get("ip", "")
    url = request.form.get("url", "")
    rc, out = run_cmd(["add", name, ip, url])
    _, targets = run_cmd(["list"])
    logs = get_logs()
    return render_template_string(TEMPLATE, targets=targets, logs=logs,
                                  message=("OK: " + out) if rc == 0 else ("FEIL: " + out))

@APP.post("/remove")
def remove():
    name = request.form.get("name", "")
    rc, out = run_cmd(["remove", name])
    _, targets = run_cmd(["list"])
    logs = get_logs()
    return render_template_string(TEMPLATE, targets=targets, logs=logs,
                                  message=("OK: " + out) if rc == 0 else ("FEIL: " + out))

@APP.post("/run-now")
def run_now():
    rc, out = run_cmd(["run"])
    _, targets = run_cmd(["list"])
    logs = get_logs()
    return render_template_string(TEMPLATE, targets=targets, logs=logs,
                                  message=("OK: " + out) if rc == 0 else ("FEIL: " + out))

if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=8088)
