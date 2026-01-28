from flask import Flask, request, render_template_string, redirect, url_for
import os
import subprocess

APP = Flask(__name__)

# UI Versioning
UI_VERSION = "v3"
COPYRIGHT_YEAR = "2026"

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
    .grid{display:grid; grid-template-columns: 1fr; gap:16px;}
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
    input{flex:1; min-width:160px;}
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
    th, td{padding:10px 10px; border-bottom:1px solid var(--line); font-size:13px; vertical-align:top;}
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

    /* v3 footer */
    .footer{
      margin-top:16px;
      color:var(--muted);
      font-size:12px;
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:10px;
      padding-top:10px;
      border-top:1px solid var(--line);
    }
    .footer a{
      color:rgba(255,255,255,.78);
      text-decoration:none;
      border-bottom:1px solid rgba(255,255,255,.18);
    }
    .footer a:hover{
      color:rgba(255,255,255,.92);
      border-bottom-color:rgba(255,255,255,.35);
    }

    .hint{color:rgba(255,255,255,.55); font-size:12px}
    @media (max-width: 940px){ .footer{flex-direction:column; align-items:flex-start;} }
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="brand">
      <div class="title">interheart <span class="pill">ping → endpoint</span></div>
      <div class="subtitle">
        Hver target har sitt eget ping-intervall. Interheart sjekker ofte, men pinger kun når target er “due”.<br/>
        Ping OK → sender endpoint. Ping feiler → sender ikke.
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
      <div class="hint">Intervall settes per target. (10–86400 sek)</div>
      <div class="sep"></div>

      <table>
        <thead>
          <tr>
            <th style="width: 180px;">Name</th>
            <th style="width: 120px;">IP</th>
            <th style="width: 120px;">Intervall</th>
            <th>Endpoint</th>
            <th style="width: 220px;">Handling</th>
          </tr>
        </thead>
        <tbody>
        {% for t in targets %}
          <tr>
            <td><code>{{ t.name }}</code></td>
            <td><code>{{ t.ip }}</code></td>
            <td>
              <div class="row">
                <span class="chip">{{ t.interval }}s</span>
                <form method="post" action="/set-target-interval" style="display:inline">
                  <input type="hidden" name="name" value="{{ t.name }}">
                  <input class="mini" style="width:110px" name="seconds" type="number" min="10" max="86400" step="1" placeholder="sek" required>
                  <button class="mini btn-ghost" type="submit">Sett</button>
                </form>
              </div>
            </td>
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
          <input name="interval" type="number" min="10" max="86400" step="1" placeholder="intervall (sek)" required>
        </div>
        <div class="row">
          <input name="endpoint" placeholder="endpoint url (https://...)" required>
          <button type="submit">Legg til</button>
        </div>
        <div class="hint">Tips: Bruk 30–120 sek på “kritiske” targets. 300–900 sek på ting som tåler litt slack.</div>
      </form>

      <div class="footer">
        <div>
          WebUI: <code>{{ bind_host }}:{{ bind_port }}</code>
          <span class="hint">• UI {{ ui_version }}</span>
        </div>

        <div>
          <a href="https://5echo.io" target="_blank" rel="noreferrer">5echo.io</a>
          © {{ copyright_year }} All rights reserved
        </div>
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
  in_table = False
  for line in list_output.splitlines():
    line = line.rstrip()
    if line.startswith("--------------------------------------------------------------------------------"):
      in_table = True
      continue
    if not in_table:
      continue
    if line.strip().startswith("NAME") or line.strip().startswith("Targets:"):
      continue
    if not line.strip():
      continue

    # Format: name ip interval endpoint
    parts = line.split()
    if len(parts) < 4:
      continue

    name = parts[0]
    ip = parts[1]
    interval = parts[2].replace("s", "").strip()
    endpoint_masked = parts[3]

    targets.append({
      "name": name,
      "ip": ip,
      "interval": interval,
      "endpoint_masked": endpoint_masked
    })
  return targets

@APP.get("/")
def index():
  message = request.args.get("message", "")
  _, out = run_cmd(["list"])
  targets = parse_targets(out)
  return render_template_string(
    TEMPLATE,
    targets=targets,
    bind_host=BIND_HOST,
    bind_port=BIND_PORT,
    message=message,
    ui_version=UI_VERSION,
    copyright_year=COPYRIGHT_YEAR
  )

@APP.post("/add")
def add():
  name = request.form.get("name", "")
  ip = request.form.get("ip", "")
  endpoint = request.form.get("endpoint", "")
  interval = request.form.get("interval", "60")
  rc, out = run_cmd(["add", name, ip, endpoint, interval])
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

@APP.post("/set-target-interval")
def set_target_interval():
  name = request.form.get("name", "")
  sec = request.form.get("seconds", "")
  rc, out = run_cmd(["set-target-interval", name, sec])
  msg = ("OK: " + out) if rc == 0 else ("FEIL: " + out)
  return redirect(url_for("index", message=msg))

if __name__ == "__main__":
  APP.run(host=BIND_HOST, port=BIND_PORT)
