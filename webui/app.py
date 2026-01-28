from flask import Flask, request, render_template_string, redirect, url_for
import os
import subprocess
import time

APP = Flask(__name__)

UI_VERSION = "v4"
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
      --bg:#060a12;
      --panel:#0b1326;
      --panel2:#091022;
      --line:rgba(255,255,255,.085);
      --text:rgba(255,255,255,.92);
      --muted:rgba(255,255,255,.62);

      /* AU-ish vibe */
      --navy:#012746;
      --accent:#2a74ff; /* primary action */
      --accent2:#58a6ff;
      --danger:#ff3b5c;

      --good:#38d39f;
      --warn:#ffd34d;

      --chip:rgba(255,255,255,.06);
      --shadow: 0 16px 40px rgba(0,0,0,.42);
      --radius: 18px;

      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    }

    *{box-sizing:border-box}
    body{
      margin:0; font-family:var(--sans); color:var(--text);
      background:
        radial-gradient(1200px 700px at 20% 8%, rgba(42,116,255,.20), transparent 55%),
        radial-gradient(900px 600px at 85% 15%, rgba(1,39,70,.38), transparent 62%),
        radial-gradient(700px 500px at 70% 80%, rgba(255,59,92,.08), transparent 55%),
        var(--bg);
    }

    .wrap{max-width:1280px; margin:34px auto; padding:0 18px;}
    .top{display:flex; align-items:flex-start; justify-content:space-between; gap:18px; margin-bottom:18px;}
    .brand{display:flex; flex-direction:column; gap:8px;}
    .title{display:flex; align-items:center; gap:10px; font-size:22px; font-weight:900; letter-spacing:.2px;}
    .badge{
      font-size:12px; padding:6px 10px; border-radius:999px;
      background:linear-gradient(180deg, rgba(42,116,255,.18), rgba(42,116,255,.06));
      border:1px solid var(--line); color:var(--muted);
    }
    .subtitle{color:var(--muted); font-size:13px; line-height:1.45}

    .card{
      background:linear-gradient(180deg, rgba(255,255,255,.045), rgba(255,255,255,.02));
      border:1px solid var(--line);
      border-radius:var(--radius);
      box-shadow: var(--shadow);
      padding:16px;
      position:relative;
      overflow:hidden;
    }
    .card:before{
      content:"";
      position:absolute; inset:-2px;
      background: radial-gradient(900px 220px at 30% 0%, rgba(42,116,255,.12), transparent 55%);
      pointer-events:none;
    }
    .card > *{position:relative;}

    .card h3{margin:0 0 10px 0; font-size:14px; color:rgba(255,255,255,.86)}
    .row{display:flex; gap:10px; flex-wrap:wrap; align-items:center}

    input{
      border-radius:14px; border:1px solid var(--line); background:rgba(0,0,0,.20);
      color:var(--text); padding:10px 12px; outline:none;
      transition: border-color .15s ease, transform .12s ease, filter .12s ease;
    }
    input{flex:1; min-width:160px;}
    input::placeholder{color:rgba(255,255,255,.35)}
    input:focus{
      border-color:rgba(42,116,255,.45);
      filter:brightness(1.03);
    }

    /* Buttons (modern) */
    .btn{
      border-radius:14px;
      border:1px solid var(--line);
      padding:10px 12px;
      cursor:pointer;
      font-weight:850;
      color:var(--text);
      background:rgba(255,255,255,.04);
      transition: transform .12s ease, border-color .12s ease, filter .12s ease, background .12s ease;
      display:inline-flex;
      align-items:center;
      gap:8px;
      user-select:none;
    }
    .btn:hover{transform: translateY(-1px); filter:brightness(1.03); border-color:rgba(42,116,255,.35);}
    .btn:active{transform: translateY(0px); filter:brightness(.98);}

    .btn-primary{
      background:linear-gradient(180deg, rgba(42,116,255,.26), rgba(42,116,255,.07));
      border-color:rgba(42,116,255,.30);
    }
    .btn-primary:hover{border-color:rgba(42,116,255,.55);}

    .btn-secondary{
      background:linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.03));
    }

    .btn-danger{
      background:linear-gradient(180deg, rgba(255,59,92,.22), rgba(255,59,92,.07));
      border-color:rgba(255,59,92,.28);
    }
    .btn-danger:hover{border-color:rgba(255,59,92,.50);}

    .btn-mini{
      font-size:12px; padding:8px 10px; border-radius:12px;
    }

    .icon{
      width:14px; height:14px; display:inline-block;
      opacity:.9;
    }

    .sep{height:1px; background:var(--line); margin:12px 0;}

    table{width:100%; border-collapse:collapse; overflow:hidden; border-radius:14px;}
    th, td{padding:10px 10px; border-bottom:1px solid var(--line); font-size:13px; vertical-align:top;}
    th{color:var(--muted); font-weight:850; text-align:left}
    td code{font-family:var(--mono); font-size:12px; color:rgba(255,255,255,.88)}

    .chip{
      display:inline-flex; align-items:center; gap:8px;
      padding:6px 10px; border-radius:999px; background:var(--chip); border:1px solid var(--line);
      color:var(--muted); font-size:12px;
      backdrop-filter: blur(6px);
    }
    .dot{width:8px; height:8px; border-radius:99px; background:rgba(255,255,255,.35)}
    .status-up{border-color:rgba(56,211,159,.26); background:rgba(56,211,159,.10)}
    .status-up .dot{background:var(--good); box-shadow:0 0 0 0 rgba(56,211,159,.35); animation:pulse 1.6s infinite;}
    .status-down{border-color:rgba(255,59,92,.30); background:rgba(255,59,92,.09)}
    .status-down .dot{background:var(--danger); box-shadow:0 0 18px rgba(255,59,92,.18);}
    .status-unknown{border-color:rgba(255,211,77,.22); background:rgba(255,211,77,.06)}
    .status-unknown .dot{background:var(--warn);}
    @keyframes pulse{
      0%{box-shadow:0 0 0 0 rgba(56,211,159,.35)}
      70%{box-shadow:0 0 0 10px rgba(56,211,159,0)}
      100%{box-shadow:0 0 0 0 rgba(56,211,159,0)}
    }

    .msg{
      border:1px solid var(--line); background:rgba(255,255,255,.03);
      border-radius:14px; padding:12px; color:var(--muted); font-size:13px;
      margin-bottom:14px;
    }

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
      color:rgba(255,255,255,.80);
      text-decoration:none;
      border-bottom:1px solid rgba(255,255,255,.18);
    }
    .footer a:hover{
      color:rgba(255,255,255,.94);
      border-bottom-color:rgba(255,255,255,.35);
    }

    .hint{color:rgba(255,255,255,.55); font-size:12px}
    .right-actions{display:flex; gap:10px; align-items:center; flex-wrap:wrap;}
    .kbd{font-family:var(--mono); font-size:11px; color:rgba(255,255,255,.68); padding:6px 8px; border:1px solid var(--line); border-radius:12px; background:rgba(0,0,0,.18);}
    .countdown{font-family:var(--mono); font-size:12px; color:rgba(255,255,255,.78)}
    .small{font-size:12px; color:rgba(255,255,255,.62)}
    .muted{color:rgba(255,255,255,.62)}
    .nowrap{white-space:nowrap}

    /* Toast */
    .toast-wrap{
      position:fixed;
      bottom:18px;
      right:18px;
      z-index:9999;
      display:flex;
      flex-direction:column;
      gap:10px;
      pointer-events:none;
    }
    .toast{
      pointer-events:none;
      min-width:260px;
      max-width:360px;
      border:1px solid var(--line);
      background:rgba(10,14,24,.78);
      backdrop-filter: blur(10px);
      border-radius:16px;
      box-shadow: 0 18px 40px rgba(0,0,0,.55);
      padding:12px 12px;
      transform: translateY(8px);
      opacity:0;
      animation: toastIn .24s ease forwards;
    }
    .toast .t-title{font-weight:900; font-size:12px; color:rgba(255,255,255,.90)}
    .toast .t-body{margin-top:4px; font-size:12px; color:rgba(255,255,255,.68); line-height:1.35}
    @keyframes toastIn{
      to{transform: translateY(0px); opacity:1;}
    }
    @keyframes toastOut{
      to{transform: translateY(8px); opacity:0;}
    }

    @media (max-width: 940px){
      .footer{flex-direction:column; align-items:flex-start;}
      .toast-wrap{right:12px; left:12px}
      .toast{min-width:unset; max-width:unset}
    }
  </style>
</head>
<body>

<div class="toast-wrap" id="toastWrap"></div>

<div class="wrap">
  <div class="top">
    <div class="brand">
      <div class="title">interheart <span class="badge">targets</span></div>
      <div class="subtitle">
        Per target: status + next ping + intervall. Ping OK → sender endpoint.
      </div>
    </div>

    <div class="right-actions">
      <div class="kbd">local: <b>{{ bind_host }}:{{ bind_port }}</b></div>
      <form method="post" action="/run-now" data-toast="Kjører sjekk…" data-toast2="Dette går fort – refresher ikke siden automatisk.">
        <button class="btn btn-primary btn-mini" type="submit">
          <span class="icon">⚡</span> Kjør nå
        </button>
      </form>
    </div>
  </div>

  {% if message %}
    <div class="msg"><b>{{ message }}</b></div>
  {% endif %}

  <div class="card">
    <h3>Targets</h3>
    <div class="hint">UI teller ned lokalt. Status/last ping/sent kommer fra state.</div>
    <div class="sep"></div>

    <table>
      <thead>
        <tr>
          <th style="width: 190px;">Name</th>
          <th style="width: 120px;">IP</th>
          <th style="width: 120px;">Status</th>
          <th style="width: 140px;">Next ping</th>
          <th style="width: 120px;">Intervall</th>
          <th style="width: 170px;">Last ping</th>
          <th style="width: 170px;">Last sent</th>
          <th>Endpoint</th>
          <th style="width: 260px;">Handling</th>
        </tr>
      </thead>
      <tbody>
      {% for t in targets %}
        <tr>
          <td><code>{{ t.name }}</code></td>
          <td><code>{{ t.ip }}</code></td>

          <td>
            <span class="chip {% if t.status == 'up' %}status-up{% elif t.status == 'down' %}status-down{% else %}status-unknown{% endif %}">
              <span class="dot"></span>
              <span style="font-weight:900; text-transform:uppercase;">{{ t.status }}</span>
            </span>
          </td>

          <td>
            <div class="countdown"
                 data-due="{{ t.next_due_epoch }}">
              …
            </div>
            <div class="small">due: <code>{{ t.next_due_epoch }}</code></div>
          </td>

          <td><span class="chip nowrap">{{ t.interval }}s</span></td>

          <td><code>{{ t.last_ping_human }}</code></td>
          <td><code>{{ t.last_sent_human }}</code></td>

          <td><code>{{ t.endpoint_masked }}</code></td>

          <td class="row">
            <form method="post" action="/set-target-interval" style="display:inline"
                  data-toast="Oppdaterer intervall…"
                  data-toast2="{{ t.name }}">
              <input type="hidden" name="name" value="{{ t.name }}">
              <input class="btn-mini" style="width:110px" name="seconds" type="number" min="10" max="86400" step="1" placeholder="sek" required>
              <button class="btn btn-secondary btn-mini" type="submit"><span class="icon">⏱</span> Intervall</button>
            </form>

            <form method="post" action="/test" style="display:inline"
                  data-toast="Tester target…"
                  data-toast2="{{ t.name }} ({{ t.ip }})">
              <input type="hidden" name="name" value="{{ t.name }}">
              <button class="btn btn-secondary btn-mini" type="submit"><span class="icon">🧪</span> Test</button>
            </form>

            <form method="post" action="/remove" style="display:inline"
                  data-toast="Fjerner target…"
                  data-toast2="{{ t.name }}"
                  onsubmit="return confirm('Fjerne {{ t.name }}?');">
              <input type="hidden" name="name" value="{{ t.name }}">
              <button class="btn btn-danger btn-mini" type="submit"><span class="icon">🗑</span> Fjern</button>
            </form>
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>

    <div class="sep"></div>

    <h3>Legg til target</h3>
    <form method="post" action="/add" data-toast="Legger til target…" data-toast2="Sjekk at endpoint er korrekt.">
      <div class="row">
        <input name="name" placeholder="name (f.eks anl-0161-core-gw)" required>
        <input name="ip" placeholder="ip (f.eks 10.5.0.1)" required>
        <input name="interval" type="number" min="10" max="86400" step="1" placeholder="intervall (sek)" required>
      </div>
      <div class="row">
        <input name="endpoint" placeholder="endpoint url (https://...)" required>
        <button class="btn btn-primary" type="submit"><span class="icon">＋</span> Legg til</button>
      </div>
      <div class="hint">Kritisk = 30–120s. Mindre kritisk = 300–900s.</div>
    </form>

    <div class="footer">
      <div class="muted">
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

<script>
(function(){
  // Countdown ticker
  function fmt(sec){
    if (sec <= 0) return "due now";
    if (sec < 60) return sec + "s";
    var m = Math.floor(sec/60);
    var s = sec % 60;
    return m + "m " + (s<10?("0"+s):s) + "s";
  }
  function tick(){
    var nodes = document.querySelectorAll(".countdown[data-due]");
    var now = Math.floor(Date.now()/1000);
    nodes.forEach(function(n){
      var due = parseInt(n.getAttribute("data-due") || "0", 10);
      if (!due || due <= 0){ n.textContent = "due now"; return; }
      n.textContent = fmt(due - now);
    });
  }
  tick();
  setInterval(tick, 1000);

  // Toasts (local UI feedback)
  var wrap = document.getElementById("toastWrap");
  function toast(title, body){
    var el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = '<div class="t-title"></div><div class="t-body"></div>';
    el.querySelector(".t-title").textContent = title || "Jobber…";
    el.querySelector(".t-body").textContent = body || "";
    wrap.appendChild(el);

    setTimeout(function(){
      el.style.animation = "toastOut .22s ease forwards";
      setTimeout(function(){ el.remove(); }, 260);
    }, 1800);
  }

  document.querySelectorAll("form[data-toast]").forEach(function(f){
    f.addEventListener("submit", function(){
      toast(f.getAttribute("data-toast"), f.getAttribute("data-toast2") || "");
    });
  });
})();
</script>

</body>
</html>
"""

def run_cmd(args):
  cmd = ["sudo", CLI] + args
  p = subprocess.run(cmd, capture_output=True, text=True)
  out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
  return p.returncode, out.strip()

def parse_list_targets(list_output: str):
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

def parse_status(status_output: str):
  state = {}
  in_table = False
  for line in status_output.splitlines():
    if line.startswith("--------------------------------------------------------------------------------------------------------------"):
      in_table = True
      continue
    if not in_table:
      continue
    if line.strip().startswith("NAME") or line.strip().startswith("State:") or line.strip().startswith("(ingen"):
      continue
    if not line.strip():
      continue

    parts = line.split()
    if len(parts) < 6:
      continue
    name = parts[0]
    status = parts[1]
    next_due = parts[3]
    last_ping = parts[4]
    last_sent = parts[5]
    state[name] = {
      "status": status,
      "next_due_epoch": int(next_due) if next_due.isdigit() else 0,
      "last_ping_epoch": int(last_ping) if last_ping.isdigit() else 0,
      "last_sent_epoch": int(last_sent) if last_sent.isdigit() else 0,
    }
  return state

def human_ts(epoch: int):
  if not epoch or epoch <= 0:
    return "-"
  try:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))
  except Exception:
    return "-"

@APP.get("/")
def index():
  message = request.args.get("message", "")

  _, list_out = run_cmd(["list"])
  targets = parse_list_targets(list_out)

  _, st_out = run_cmd(["status"])
  state = parse_status(st_out)

  merged = []
  for t in targets:
    st = state.get(t["name"], {})
    status = st.get("status", "unknown")
    next_due_epoch = st.get("next_due_epoch", 0)
    last_ping_epoch = st.get("last_ping_epoch", 0)
    last_sent_epoch = st.get("last_sent_epoch", 0)

    merged.append({
      **t,
      "status": status,
      "next_due_epoch": next_due_epoch,
      "last_ping_human": human_ts(last_ping_epoch),
      "last_sent_human": human_ts(last_sent_epoch),
    })

  return render_template_string(
    TEMPLATE,
    targets=merged,
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
