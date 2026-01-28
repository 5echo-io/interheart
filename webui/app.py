from flask import Flask, request, render_template_string, redirect, url_for
import os
import subprocess

APP = Flask(__name__)

CLI = "/usr/local/bin/interheart"
BIND_HOST = os.environ.get("WEBUI_BIND", "127.0.0.1")
BIND_PORT = int(os.environ.get("WEBUI_PORT", "8088"))

TEMPLATE = r"""
<!doctype html>
<html lang="no">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>interheart</title>
  <style>
    :root{
      --bg:#070b14;
      --panel:#0b1326;
      --line:rgba(255,255,255,.08);
      --text:rgba(255,255,255,.92);
      --muted:rgba(255,255,255,.62);
      --blue:#012746;
      --accent:#2a74ff;
      --bad:#ff5c5c;
      --chip:rgba(255,255,255,.06);
      --shadow: 0 12px 30px rgba(0,0,0,.35);
      --radius: 18px;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    }
    *{box-sizing:border-box}
    body{
      margin:0; font-family:var(--sans); color:var(--text);
      background: radial-gradient(1200px 700px at 20% 10%, rgba(42,116,255,.18), transparent 55%),
                  radial-gradient(1000px 600px at 80% 20%, rgba(1,39,70,.35), transparent 60%),
                  var(--bg);
    }
    .wrap{max-width:1100px; margin:34px auto; padding:0 18px;}
    .top{display:flex; align-items:flex-start; justify-content:space-between; gap:18px; margin-bottom:18px;}
    .brand{display:flex; flex-direction:column; gap:8px;}
    .title{display:flex; align-items:center; gap:10px; font-size:22px; font-weight:800; letter-spacing:.2px;}
    .pill{font-size:12px; padding:5px 10px; border-radius:999px;
      background:linear-gradient(180deg, rgba(42,116,255,.18), rgba(42,116,255,.05));
      border:1px solid var(--line); color:var(--muted);
    }
    .subtitle{color:var(--muted); font-size:13px; line-height:1.4}
    .grid{display:grid; grid-template-columns: 1.15fr .85fr; gap:16px;}
    .card{
      background:linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.02));
      border:1px solid var(--line);
      border-radius:var(--radius);
      box-shadow: var(--shadow);
      padding:16px;
    }
    .card h3{margin:0 0 10px 0; font-size:14px; color:rgba(255,255,255,.84)}
    .row{display:flex; gap:10px; flex-wrap:wrap; align-items:center}
    input, button{
      border-radius:14px; border:1px solid var(--line); background:rgba(0,0,0,.18);
      color:var(--text); padding:10px 12px; outline:none;
    }
    input{flex:1; min-width:180px;}
    input::placeholder{color:rgba(255,255,255,.35)}
    button{
      cursor:pointer; font-weight:750;
      background:linear-gradient(180deg, rgba(42,116,255,.22), rgba(42,116,255,.06));
    }
    button:hover{border-color:rgba(42,116,255,.35)}
    .btn-ghost{background:rgba(255,255,255,.04);}
    .btn-danger{background:linear-gradient(180deg, rgba(255,92,92,.22), rgba(255,92,92,.06));}
    .mini{font-size:12px; padding:8px 10px; border-radius:12px;}
    .sep{height:1px; background:var(--line); margin:12px 0;}
    table{width:100%; border-collapse:collapse; overflow:hidden; border-radius:14px;}
    th, td{padding:10px 10px; border-bottom:1px solid var(--line); font-size:13px;}
    th{color:var(--muted); font-weight:750; text-align:left}
    td code{font-family:var(--mono); font-size:12px; color:rgba(255,255,255,.85)}
    .chip{
      display:inline-flex; align-items:center; gap:6px;
      padding:6px 10px; border-radius:999px; background:var(--chip); border:1px solid var(--line);
      color:var(--muted); font-size:12px;
    }
    .msg{
      border:1px solid var(--line); background:rgba(255,255,255,.03);
      border-radius:14px; padding:12px; color:var(--muted); font-size:13px;
      margin-bottom:14px;
    }
    .logs{
      font-family:var(--mono); font-size:12px; color:rgba(255,255,255,.75);
      background:rgba(0,0,0,.18); border:1px solid var(--line);
      border-radius:14px; padding:12px; white-space:pre-wrap; max-height:340px; overflow:auto;
    }
    .footer{margin-top:16px; color:var(--muted); font-size:12px;}
    .hint{color:rgba(255,255,255,.55); font-size:12px}
    @media (max-width: 940px){ .grid{grid-template-columns:1fr;} }
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="brand">
      <div class="title">interheart <span class="pill">ping → endpoint</span></div>
      <div class="subtitle">
        Pinger interne targets og sender request til valgt endpoint når ping er OK.<br/>
        Endpoint kan være UptimeRobot, Kuma Push, webhook, intern API – you name it.
      </div>
    </div>

    <form method="post" action="/run-now">
      <button class="mini" type="submit">Kjør sjekk nå</button>
    </form>
  </div>

  {% if message %}
    <div class="msg"><b>{{ message }}</b></div>
  {% endif %}

  <div class="grid">
    <div class="card">
      <h3>Targets</h3>
      <div class="hint">Hver target har egen endpoint-URL. Ping OK → request sendes. Ping feiler → sendes ikke.</div>
      <div class="sep"></div>

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>IP</th>
            <th>Endpoint</th>
            <th>Handling</th>
          </tr>
        </thead>
        <tbody>
        {% for t in targets %}
          <tr>
            <td><code>{{ t.name }}</code></td>
            <td><code>{{ t.ip }}</code></td>
            <td><code>{{ t.endpoint_masked }}</code></td>
            <td class="row">
              <form method="post" action="/test" style="display:inline">
                <input type="hidden" name="name" value="{{ t.name }}">
                <button class="mini btn-ghost" type="submit">Test</button>
              </form>
              <form method="post" action="/remove" style="display:inline" onsubmit="return confirm('Fjerne {{ t.name }}?');">
                <input type="hidden" name="name" value="{{ t.name }}">
                <button class="mini btn-danger" type="submit">Fjern</button>
              </form>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>

      <div class="sep"></div>

      <h3>Legg til target</h3>
      <form method="post" action="/add">
        <div class="row">
          <input name="name" placeholder="name (f.eks anl-0161-core-gw)" required>
          <input name="ip" placeholder="ip (f.eks 10.5.0.1)" required>
        </div>
        <div class="row">
          <input name="endpoint" placeholder="endpoint url (https://...)" required>
          <button type="submit">Legg til</button>
        </div>
      </form>
    </div>

    <div class="card">
      <h3>Schedule</h3>
      <div class="row"><span class="chip">Intervall: <b>{{ interval }}</b></span></div>
      <div class="sep"></div>
      <form method="post" action="/set-interval">
        <div class="row">
          <input name="seconds" type="number" min="10" max="3600" step="1" placeholder="sekunder (10–3600)" required>
          <button type="submit">Sett intervall</button>
        </div>
        <div class="hint">Tips: 60 sek er ofte sweetspot. Juster etter hvor raskt du vil varsles.</div>
      </form>

      <div class="sep"></div>
      <h3>Siste logs</h3>
      <div class="logs">{{ logs }}</div>

      <div class="footer">
        WebUI binder til <code>{{ bind_host }}:{{ bind_port }}</code>.
        For LAN: sett <code>WEBUI_BIND=0.0.0.0</code> i systemd-servicen.
      </div>
    </div>
  </div>
</div>
</body>
</html>
"""

def run_cmd(args):
  cmd = ["sudo", CLI] + args
  p = subprocess.run(cmd, capture_output=True, text=True)
  out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
  return p.returncode, out.strip()

def parse_targets(list_output: str):
  targets = []
  for line in list_output.splitlines():
    line = line.strip()
    if line.startswith("- "):
      parts = line.replace("-", "", 1).strip().split()
      name = parts[0] if len(parts) > 0 else ""
      ip = parts[1] if len(parts) > 1 else ""
      endpoint_masked = parts[2] if len(parts) > 2 else ""
      targets.append({"name": name, "ip": ip, "endpoint_masked": endpoint_masked})
  return targets

def get_logs():
  p = subprocess.run(["journalctl", "-t", "interheart", "-n", "80", "--no-pager"], capture_output=True, text=True)
  return (p.stdout or "").strip() or "(ingen logs ennå)"

@APP.get("/")
def index():
  message = request.args.get("message", "")
  _, out = run_cmd(["list"])
  interval = run_cmd(["get-interval"])[1]
  targets = parse_targets(out)
  logs = get_logs()
  return render_template_string(
    TEMPLATE,
    targets=targets,
    logs=logs,
    interval=interval,
    bind_host=BIND_HOST,
    bind_port=BIND_PORT,
    message=message
  )

@APP.post("/add")
def add():
  name = request.form.get("name", "")
  ip = request.form.get("ip", "")
  endpoint = request.form.get("endpoint", "")
  rc, out = run_cmd(["add", name, ip, endpoint])
  msg = ("OK: " + out) if rc == 0 else ("FEIL: " + out)
  return redirect(url_for("index", message=msg))

@APP.post("/remove")
def remove():
  name = request.form.get("name", "")
  rc, out = run_cmd(["remove", name])
  msg = ("OK: " + out) if rc == 0 else ("FEIL: " + out)
  return redirect(url_for("index", message=msg))

@APP.post("/run-now")
def run_now():
  rc, out = run_cmd(["run"])
  msg = ("OK: " + out) if rc == 0 else ("FEIL: " + out)
  return redirect(url_for("index", message=msg))

@APP.post("/test")
def test():
  name = request.form.get("name", "")
  rc, out = run_cmd(["test", name])
  msg = ("TEST OK: " + out) if rc == 0 else ("TEST: " + out)
  return redirect(url_for("index", message=msg))

@APP.post("/set-interval")
def set_interval():
  sec = request.form.get("seconds", "")
  rc, out = run_cmd(["set-interval", sec])
  msg = ("OK: " + out) if rc == 0 else ("FEIL: " + out)
  return redirect(url_for("index", message=msg))

if __name__ == "__main__":
  APP.run(host=BIND_HOST, port=BIND_PORT)
