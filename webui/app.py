from flask import Flask, request, render_template_string, redirect, url_for, jsonify
import os
import subprocess
import time

APP = Flask(__name__)

# ---- SemVer from VERSION file ----
def read_version():
    try:
        base = os.environ.get("INTERHEART_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates = [
            os.path.join(base, "VERSION"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION"),
        ]
        for p in candidates:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    return f.read().strip()
    except Exception:
        pass
    return "0.0.0"

UI_VERSION = read_version()
COPYRIGHT_YEAR = "2026"

CLI = "/usr/local/bin/interheart"
BIND_HOST = os.environ.get("WEBUI_BIND", "0.0.0.0")
BIND_PORT = int(os.environ.get("WEBUI_PORT", "8088"))

LOG_LINES_DEFAULT = 200
STATE_POLL_SECONDS = 2

# ---- Helpers ----
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
            "interval": int(interval) if interval.isdigit() else 60,
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
        if line.strip().startswith("NAME") or line.strip().startswith("State:") or line.strip().startswith("(no"):
            continue
        if not line.strip():
            continue

        parts = line.split()
        if len(parts) < 6:
            continue
        name = parts[0]
        status = parts[1]
        last_ping = parts[4]
        last_sent = parts[5]
        state[name] = {
            "status": status,
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

def sudo_journalctl(lines: int) -> str:
    cmd = ["sudo", "journalctl", "-t", "interheart", "-n", str(lines), "--no-pager", "--output=short-iso"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "journalctl failed").strip())
    return (p.stdout or "").strip()

def merged_targets():
    _, list_out = run_cmd(["list"])
    targets = parse_list_targets(list_out)

    _, st_out = run_cmd(["status"])
    state = parse_status(st_out)

    merged = []
    for t in targets:
        st = state.get(t["name"], {})
        status = st.get("status", "unknown")
        last_ping_epoch = st.get("last_ping_epoch", 0)
        last_sent_epoch = st.get("last_sent_epoch", 0)

        merged.append({
            **t,
            "status": status,
            "last_ping_human": human_ts(last_ping_epoch),
            "last_sent_human": human_ts(last_sent_epoch),
            "last_ping_epoch": last_ping_epoch,
            "last_sent_epoch": last_sent_epoch,
        })
    return merged

# ---- UI Template ----
TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>interheart</title>

  <style>
    :root{
      /* "5echo-ish": deeper navy + calm panels */
      --bg:#070b12;
      --panel:#0b1220;
      --panel2:#0c1526;
      --line:rgba(255,255,255,.10);

      --text:rgba(255,255,255,.92);
      --muted:rgba(255,255,255,.60);

      --accent:rgba(255,255,255,.86);
      --accentLine:rgba(255,255,255,.14);

      --good:#35d39f;
      --danger:#ff3b5c;
      --warn:#ffd34d;

      --shadow: 0 18px 54px rgba(0,0,0,.60);
      --radius: 18px;

      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    }

    *{box-sizing:border-box}
    body{
      margin:0;
      font-family:var(--sans);
      color:var(--text);
      background: var(--bg);
    }

    .wrap{max-width:1280px;margin:34px auto;padding:0 18px}
    .top{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:16px}
    .brand{display:flex;flex-direction:column;gap:8px}
    .title{display:flex;align-items:center;gap:10px;font-size:22px;font-weight:900;letter-spacing:.2px}
    .badge{
      font-size:12px;padding:6px 10px;border-radius:999px;
      background:rgba(255,255,255,.05);
      border:1px solid var(--line);
      color:var(--muted);
    }

    .subtitle{
      color:var(--muted);
      font-size:13px;
      display:flex;
      align-items:center;
      gap:10px;
    }
    .subtitle a{
      color:rgba(255,255,255,.85);
      text-decoration:none;
      border-bottom:1px solid rgba(255,255,255,.18);
    }
    .subtitle a:hover{border-bottom-color:rgba(255,255,255,.32)}

    .card{
      background: linear-gradient(180deg, rgba(255,255,255,.035), rgba(255,255,255,.015));
      border:1px solid var(--line);
      border-radius:var(--radius);
      box-shadow: var(--shadow);
      padding:16px;
      overflow:hidden;
    }

    .hint{color:rgba(255,255,255,.52);font-size:12px}
    .sep{height:1px;background:var(--line);margin:12px 0}

    input, textarea{
      border-radius:14px;
      border:1px solid var(--line);
      background:rgba(255,255,255,.03);
      color:var(--text);
      padding:10px 12px;
      outline:none;
      transition: border-color .15s ease, filter .15s ease;
      font-family:var(--sans);
    }
    input:focus, textarea:focus{
      border-color:rgba(255,255,255,.24);
      filter:brightness(1.03);
    }
    input::placeholder{color:rgba(255,255,255,.30)}

    /* Minimal buttons */
    .btn{
      border-radius:14px;
      border:1px solid var(--line);
      padding:10px 12px;
      cursor:pointer;
      font-weight:850;
      color:rgba(255,255,255,.90);
      background:rgba(255,255,255,.03);
      transition: transform .12s ease, border-color .12s ease, background .12s ease;
      display:inline-flex;
      align-items:center;
      gap:8px;
      user-select:none;
    }
    .btn:hover{
      transform: translateY(-1px);
      border-color: rgba(255,255,255,.20);
      background:rgba(255,255,255,.04);
    }
    .btn:active{transform: translateY(0px)}
    .btn-mini{font-size:12px;padding:8px 10px;border-radius:12px}
    .btn-ghost{
      background:transparent;
      border-color:rgba(255,255,255,.12);
    }
    .btn-ghost:hover{border-color:rgba(255,255,255,.22)}

    .btn-primary{
      border-color:rgba(255,255,255,.22);
      background:rgba(255,255,255,.06);
    }

    .right-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}

    /* Table */
    table{width:100%;border-collapse:collapse;border-radius:14px;overflow:hidden}
    th,td{padding:10px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:middle}
    th{color:var(--muted);font-weight:850;text-align:left}
    td code{font-family:var(--mono);font-size:12px;color:rgba(255,255,255,.88)}

    .chip{
      display:inline-flex;align-items:center;gap:8px;
      padding:6px 10px;border-radius:999px;
      background:rgba(255,255,255,.04);
      border:1px solid var(--line);
      color:var(--muted);
      font-size:12px;
    }
    .dot{width:8px;height:8px;border-radius:99px;background:rgba(255,255,255,.35)}
    .status-up{border-color:rgba(53,211,159,.26);background:rgba(53,211,159,.09)}
    .status-up .dot{background:var(--good);animation:pulse 1.6s infinite}
    .status-down{border-color:rgba(255,59,92,.30);background:rgba(255,59,92,.08)}
    .status-down .dot{background:var(--danger)}
    .status-unknown{border-color:rgba(255,211,77,.22);background:rgba(255,211,77,.06)}
    .status-unknown .dot{background:var(--warn)}
    @keyframes pulse{
      0%{box-shadow:0 0 0 0 rgba(53,211,159,.28)}
      70%{box-shadow:0 0 0 10px rgba(53,211,159,0)}
      100%{box-shadow:0 0 0 0 rgba(53,211,159,0)}
    }

    /* Inline interval */
    .interval-wrap{display:flex;align-items:center;gap:8px}
    .interval-input{
      width:86px;
      padding:8px 10px;
      border-radius:12px;
      font-weight:850;
      font-family:var(--mono);
      background:rgba(255,255,255,.03);
    }
    .interval-suffix{color:rgba(255,255,255,.45);font-size:12px;font-weight:850}

    /* Actions menu */
    .menu{position:relative;display:inline-block}
    .menu-btn{
      width:40px;height:34px;
      display:inline-flex;align-items:center;justify-content:center;
      border-radius:12px;
    }
    .menu-dd{
      position:absolute;
      right:0;
      top:42px;
      width:220px;
      background:rgba(10,16,28,.96);
      border:1px solid rgba(255,255,255,.12);
      border-radius:14px;
      box-shadow: 0 22px 60px rgba(0,0,0,.70);
      padding:6px;
      display:none;
      z-index:50;
      transform-origin: top right;
      animation: pop .12s ease;
    }
    @keyframes pop{from{transform:scale(.98);opacity:.7}to{transform:scale(1);opacity:1}}
    .menu.show .menu-dd{display:block}
    .menu-item{
      width:100%;
      border:0;
      background:transparent;
      color:rgba(255,255,255,.86);
      padding:10px 10px;
      border-radius:12px;
      cursor:pointer;
      display:flex;align-items:center;gap:10px;
      font-weight:850;
    }
    .menu-item:hover{background:rgba(255,255,255,.06)}
    .menu-item.danger{color:rgba(255,255,255,.92)}
    .menu-item.danger:hover{background:rgba(255,59,92,.10)}

    /* Toasts */
    .toasts{
      position:fixed;
      top:18px; right:18px;
      display:flex;
      flex-direction:column;
      gap:10px;
      z-index:9999;
      width:min(420px, calc(100vw - 24px));
      pointer-events:none;
    }
    .toast{
      pointer-events:auto;
      border-radius:16px;
      border:1px solid rgba(255,255,255,.12);
      background:rgba(10,16,28,.92);
      box-shadow: 0 18px 54px rgba(0,0,0,.70);
      padding:12px 12px;
      display:flex;
      gap:10px;
      align-items:flex-start;
      animation: toastIn .14s ease;
    }
    @keyframes toastIn{from{transform:translateY(-6px);opacity:.65}to{transform:translateY(0);opacity:1}}
    .toast b{font-size:13px}
    .toast p{margin:2px 0 0 0;font-size:12px;color:rgba(255,255,255,.64);line-height:1.35}
    .toast .x{
      margin-left:auto;
      cursor:pointer;
      border:0;
      background:transparent;
      color:rgba(255,255,255,.70);
      font-weight:900;
    }

    /* Modal */
    .modal{
      position:fixed;inset:0;
      display:none;
      align-items:center;justify-content:center;
      z-index:9997;
      padding:26px; /* more air */
      background:rgba(0,0,0,.60);
      backdrop-filter: blur(12px);
    }
    .modal.show{display:flex}
    .modal-card{
      width:min(980px, calc(100vw - 40px));
      max-height:min(82vh, 880px);
      display:flex;
      flex-direction:column;
      border:1px solid rgba(255,255,255,.12);
      border-radius:22px;
      background:rgba(10,16,28,.94);
      box-shadow: 0 26px 70px rgba(0,0,0,.72);
      overflow:hidden;
    }
    .modal-head{
      padding:14px 14px;
      border-bottom:1px solid rgba(255,255,255,.10);
      display:flex;gap:12px;align-items:flex-start;justify-content:space-between;
    }
    .modal-title b{font-size:14px}
    .modal-title span{display:block;font-size:12px;color:rgba(255,255,255,.62);margin-top:2px}
    .modal-actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center;justify-content:flex-end}
    .modal-body{padding:16px;overflow:auto;flex:1;display:flex;flex-direction:column;gap:12px}

    .logbox{
      width:100%;
      min-height:380px;
      background:rgba(255,255,255,.03);
      border:1px solid rgba(255,255,255,.10);
      border-radius:16px;
      padding:12px;
      font-family:var(--mono);
      font-size:12px;
      line-height:1.45;
      color:rgba(255,255,255,.84);
      white-space:pre;
      overflow:auto;
      position:relative;
    }

    /* Small live “pulse” when values change */
    .flash{
      animation: flash .45s ease;
    }
    @keyframes flash{
      from{background:rgba(255,255,255,.10)}
      to{background:transparent}
    }

    .footer{
      margin-top:14px;
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
      color:rgba(255,255,255,.82);
      text-decoration:none;
      border-bottom:1px solid rgba(255,255,255,.18);
    }
    .footer a:hover{border-bottom-color:rgba(255,255,255,.34)}

    /* Run now spinner */
    .spin{animation: spin 0.9s linear infinite}
    @keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}

    @media (max-width: 940px){
      .footer{flex-direction:column;align-items:flex-start}
      .modal-head{flex-direction:column;align-items:stretch}
      .modal-actions{justify-content:flex-start}
    }
  </style>
</head>

<body>
<div class="toasts" id="toasts"></div>

<!-- Logs modal -->
<div class="modal" id="logModal" aria-hidden="true">
  <div class="modal-card" role="dialog" aria-modal="true" aria-label="Logs">
    <div class="modal-head">
      <div class="modal-title">
        <b>Logs</b>
        <span>Last <span id="logLinesLbl">{{ log_lines }}</span> lines</span>
      </div>
      <div class="modal-actions">
        <input id="logFilter" placeholder="filter (e.g. anl-0161)" style="min-width:220px;">
        <button class="btn btn-ghost btn-mini" id="btnReloadLogs" type="button">
          <span class="ico" aria-hidden="true">{{ icons.refresh }}</span> Reload
        </button>
        <button class="btn btn-ghost btn-mini" id="btnCopyLogs" type="button">
          <span class="ico" aria-hidden="true">{{ icons.copy }}</span> Copy
        </button>
        <button class="btn btn-ghost btn-mini" id="btnCloseLogs" type="button">
          <span class="ico" aria-hidden="true">{{ icons.close }}</span> Close
        </button>
      </div>
    </div>

    <div class="modal-body">
      <div class="logbox" id="logBox">Loading logs…</div>
      <div class="hint" id="logMeta">-</div>
    </div>

    <div class="footer" style="border-top:1px solid var(--line); padding:10px 14px; margin:0;">
      <div class="hint">interheart <code>{{ ui_version }}</code></div>
      <div>
        <a href="https://5echo.io" target="_blank" rel="noreferrer">5echo.io</a> © {{ copyright_year }} All rights reserved
      </div>
    </div>
  </div>
</div>

<!-- Add target modal -->
<div class="modal" id="addModal" aria-hidden="true">
  <div class="modal-card" role="dialog" aria-modal="true" aria-label="Add target">
    <div class="modal-head">
      <div class="modal-title">
        <b>Add target</b>
        <span>Define target and where to send a heartbeat when ping succeeds</span>
      </div>
      <div class="modal-actions">
        <button class="btn btn-ghost btn-mini" id="btnCloseAdd" type="button">
          <span class="ico" aria-hidden="true">{{ icons.close }}</span> Close
        </button>
      </div>
    </div>

    <div class="modal-body">
      <form id="addForm">
        <div class="hint" style="margin-bottom:4px;">Name</div>
        <input name="name" placeholder="e.g. anl-0161-core-gw" required>

        <div class="hint" style="margin-top:10px;margin-bottom:4px;">IP address</div>
        <input name="ip" placeholder="e.g. 10.5.0.1" required>

        <div class="hint" style="margin-top:10px;margin-bottom:4px;">Interval (seconds)</div>
        <input name="interval" type="number" min="10" max="86400" step="1" placeholder="e.g. 60" required>

        <div class="hint" style="margin-top:10px;margin-bottom:4px;">Endpoint URL</div>
        <input name="endpoint" placeholder="https://..." required>

        <div style="display:flex; gap:10px; margin-top:14px;">
          <button class="btn btn-primary" type="submit" id="btnAddSubmit">
            <span class="ico" aria-hidden="true">{{ icons.plus }}</span>
            Add target
          </button>
          <button class="btn btn-ghost" type="button" id="btnAddCancel">Cancel</button>
        </div>

        <div class="hint" style="margin-top:10px;">
          Tip: Critical targets: 30–120s. Less critical: 300–900s.
        </div>
      </form>
    </div>

    <div class="footer" style="border-top:1px solid var(--line); padding:10px 14px; margin:0;">
      <div class="hint">interheart <code>{{ ui_version }}</code></div>
      <div>
        <a href="https://5echo.io" target="_blank" rel="noreferrer">5echo.io</a> © {{ copyright_year }} All rights reserved
      </div>
    </div>
  </div>
</div>

<div class="wrap">
  <div class="top">
    <div class="brand">
      <div class="title">interheart <span class="badge">targets</span></div>
      <div class="subtitle">
        Powered by <a href="https://5echo.io" target="_blank" rel="noreferrer">5echo.io</a>
      </div>
    </div>

    <div class="right-actions">
      <button class="btn btn-ghost btn-mini" id="openLogs" type="button">
        <span class="ico" aria-hidden="true">{{ icons.logs }}</span> Logs
      </button>

      <button class="btn btn-ghost btn-mini" id="openAdd" type="button">
        <span class="ico" aria-hidden="true">{{ icons.plus }}</span> Add
      </button>

      <button class="btn btn-primary btn-mini" id="btnRunNow" type="button">
        <span class="ico" id="runNowIcon" aria-hidden="true">{{ icons.play }}</span>
        Run now
      </button>
    </div>
  </div>

  <div class="card">
    <div class="hint">Last ping / last sent update in real-time ({{ poll_seconds }}s refresh)</div>
    <div class="sep"></div>

    <table>
      <thead>
        <tr>
          <th style="width: 210px;">Name</th>
          <th style="width: 130px;">IP</th>
          <th style="width: 140px;">Status</th>
          <th style="width: 150px;">Interval</th>
          <th style="width: 190px;">Last ping</th>
          <th style="width: 190px;">Last sent</th>
          <th>Endpoint</th>
          <th style="width: 90px;">Actions</th>
        </tr>
      </thead>
      <tbody>
      {% for t in targets %}
        <tr data-name="{{ t.name }}">
          <td><code>{{ t.name }}</code></td>
          <td><code>{{ t.ip }}</code></td>
          <td>
            <span class="chip status-chip {% if t.status == 'up' %}status-up{% elif t.status == 'down' %}status-down{% else %}status-unknown{% endif %}">
              <span class="dot"></span>
              <span class="status-text" style="font-weight:900; text-transform:uppercase;">{{ t.status }}</span>
            </span>
          </td>

          <td>
            <div class="interval-wrap">
              <input class="interval-input" data-interval="{{ t.interval }}" value="{{ t.interval }}" inputmode="numeric" />
              <span class="interval-suffix">s</span>
            </div>
          </td>

          <td><code class="last-ping" data-epoch="{{ t.last_ping_epoch }}">{{ t.last_ping_human }}</code></td>
          <td><code class="last-sent" data-epoch="{{ t.last_sent_epoch }}">{{ t.last_sent_human }}</code></td>
          <td><code class="endpoint">{{ t.endpoint_masked }}</code></td>

          <td style="text-align:right;">
            <div class="menu">
              <button class="btn btn-ghost btn-mini menu-btn" type="button" aria-label="Actions">
                <span class="ico" aria-hidden="true">{{ icons.more }}</span>
              </button>
              <div class="menu-dd" role="menu">
                <button class="menu-item" data-action="test" type="button">
                  <span class="ico" aria-hidden="true">{{ icons.test }}</span> Test
                </button>
                <button class="menu-item danger" data-action="remove" type="button">
                  <span class="ico" aria-hidden="true">{{ icons.trash }}</span> Remove
                </button>
              </div>
            </div>
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>

    <div class="footer">
      <div class="hint">
        WebUI: <code>{{ bind_host }}:{{ bind_port }}</code> • interheart <code>{{ ui_version }}</code>
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
  // ---- Toasts ----
  const toasts = document.getElementById("toasts");
  function toast(title, msg){
    const el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = `
      <div>
        <b>${escapeHtml(title)}</b>
        <p>${escapeHtml(msg || "")}</p>
      </div>
      <button class="x" aria-label="Close">×</button>
    `;
    el.querySelector(".x").onclick = () => el.remove();
    toasts.appendChild(el);
    setTimeout(() => { if (el && el.parentNode) el.remove(); }, 5200);
  }
  function escapeHtml(s){
    return String(s ?? "")
      .replaceAll("&","&amp;")
      .replaceAll("<","&lt;")
      .replaceAll(">","&gt;")
      .replaceAll('"',"&quot;")
      .replaceAll("'","&#039;");
  }

  // ---- Modal helpers ----
  function show(el){ el.classList.add("show"); el.setAttribute("aria-hidden","false"); }
  function hide(el){ el.classList.remove("show"); el.setAttribute("aria-hidden","true"); }

  // ---- Logs modal ----
  const logModal = document.getElementById("logModal");
  const openLogs = document.getElementById("openLogs");
  const closeLogs = document.getElementById("btnCloseLogs");
  const reloadLogs = document.getElementById("btnReloadLogs");
  const copyLogs = document.getElementById("btnCopyLogs");
  const logBox = document.getElementById("logBox");
  const logMeta = document.getElementById("logMeta");
  const logFilter = document.getElementById("logFilter");
  let rawLog = "";

  async function loadLogs(){
    try{
      const res = await fetch("/logs?lines={{ log_lines }}", {cache:"no-store"});
      const data = await res.json();
      rawLog = data.text || "";
      logMeta.textContent = (data.source || "log") + " • " + (data.lines || 0) + " lines • " + (data.updated || "");
      applyLogFilter();
      logBox.scrollTop = logBox.scrollHeight;
    }catch(e){
      rawLog = "";
      logBox.textContent = "Failed to fetch logs: " + (e && e.message ? e.message : "unknown");
      logMeta.textContent = "error";
    }
  }
  function applyLogFilter(){
    const q = (logFilter.value || "").trim().toLowerCase();
    if (!q){ logBox.textContent = rawLog || "(empty)"; return; }
    const lines = (rawLog || "").split("\n").filter(l => l.toLowerCase().includes(q));
    logBox.textContent = lines.join("\n") || "(no matches)";
  }
  openLogs.addEventListener("click", async () => { show(logModal); logFilter.focus(); await loadLogs(); });
  closeLogs.addEventListener("click", () => hide(logModal));
  reloadLogs.addEventListener("click", async () => await loadLogs());
  copyLogs.addEventListener("click", async () => {
    try{ await navigator.clipboard.writeText(logBox.textContent || ""); toast("Copied", "Logs copied to clipboard"); }catch(e){}
  });
  logFilter.addEventListener("input", applyLogFilter);
  logModal.addEventListener("click", (e) => { if (e.target === logModal) hide(logModal); });

  // ---- Add modal ----
  const addModal = document.getElementById("addModal");
  const openAdd = document.getElementById("openAdd");
  const closeAdd = document.getElementById("btnCloseAdd");
  const addCancel = document.getElementById("btnAddCancel");
  const addForm = document.getElementById("addForm");
  const addSubmit = document.getElementById("btnAddSubmit");

  openAdd.addEventListener("click", () => show(addModal));
  closeAdd.addEventListener("click", () => hide(addModal));
  addCancel.addEventListener("click", () => hide(addModal));
  addModal.addEventListener("click", (e) => { if (e.target === addModal) hide(addModal); });

  addForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    addSubmit.disabled = true;
    addSubmit.textContent = "Adding…";
    try{
      const fd = new FormData(addForm);
      const res = await fetch("/api/add", {method:"POST", body: fd});
      const data = await res.json();
      if (data.ok){
        toast("Added", data.message || "Target added");
        hide(addModal);
        addForm.reset();
        await refreshState(true);
      }else{
        toast("Error", data.message || "Failed to add");
      }
    }catch(err){
      toast("Error", err && err.message ? err.message : "Failed to add");
    }finally{
      addSubmit.disabled = false;
      addSubmit.innerHTML = `{{ icons.plus }} Add target`;
    }
  });

  // ---- Actions dropdown menus ----
  function closeAllMenus(){
    document.querySelectorAll(".menu.show").forEach(m => m.classList.remove("show"));
  }
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".menu-btn");
    if (btn){
      const menu = btn.closest(".menu");
      const isOpen = menu.classList.contains("show");
      closeAllMenus();
      if (!isOpen) menu.classList.add("show");
      return;
    }
    if (!e.target.closest(".menu")) closeAllMenus();
  });

  // ---- Run Now (visual feedback) ----
  const btnRunNow = document.getElementById("btnRunNow");
  const runNowIcon = document.getElementById("runNowIcon");

  btnRunNow.addEventListener("click", async () => {
    btnRunNow.disabled = true;
    runNowIcon.classList.add("spin");
    toast("Run started", "Running ping cycle…");

    try{
      const res = await fetch("/api/run-now", {method:"POST"});
      const data = await res.json();
      if (data.ok){
        toast("Run completed", data.message || "Done");
      }else{
        toast("Run failed", data.message || "Error");
      }
    }catch(e){
      toast("Run failed", e && e.message ? e.message : "Error");
    }finally{
      runNowIcon.classList.remove("spin");
      btnRunNow.disabled = false;
      await refreshState(true);
    }
  });

  // ---- Inline interval editing ----
  async function setIntervalFor(name, seconds){
    const fd = new FormData();
    fd.set("name", name);
    fd.set("seconds", String(seconds));
    const res = await fetch("/api/set-target-interval", {method:"POST", body: fd});
    return await res.json();
  }

  function attachIntervalHandlers(){
    document.querySelectorAll("tr[data-name]").forEach(row => {
      const name = row.getAttribute("data-name");
      const input = row.querySelector(".interval-input");
      if (!input || input.dataset.bound === "1") return;
      input.dataset.bound = "1";

      const commit = async () => {
        const v = String(input.value || "").trim();
        const n = parseInt(v, 10);
        if (!Number.isFinite(n) || n < 10 || n > 86400){
          toast("Invalid interval", "Use 10–86400 seconds");
          input.value = input.getAttribute("data-interval") || "60";
          return;
        }
        if (String(n) === String(input.getAttribute("data-interval"))){
          return;
        }

        input.disabled = true;
        try{
          const r = await setIntervalFor(name, n);
          if (r.ok){
            toast("Updated", r.message || `Interval set to ${n}s`);
            input.setAttribute("data-interval", String(n));
          }else{
            toast("Error", r.message || "Failed to set interval");
            input.value = input.getAttribute("data-interval") || "60";
          }
        }catch(e){
          toast("Error", e && e.message ? e.message : "Failed to set interval");
          input.value = input.getAttribute("data-interval") || "60";
        }finally{
          input.disabled = false;
        }
      };

      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter"){ e.preventDefault(); commit(); input.blur(); }
        if (e.key === "Escape"){ input.value = input.getAttribute("data-interval") || "60"; input.blur(); }
      });
      input.addEventListener("blur", commit);
    });
  }

  // ---- Menu actions (Test / Remove) ----
  async function apiPost(url, fd){
    const res = await fetch(url, {method:"POST", body: fd});
    return await res.json();
  }

  function attachMenuActions(){
    document.querySelectorAll("tr[data-name]").forEach(row => {
      const name = row.getAttribute("data-name");
      row.querySelectorAll(".menu-item").forEach(btn => {
        if (btn.dataset.bound === "1") return;
        btn.dataset.bound = "1";
        btn.addEventListener("click", async () => {
          closeAllMenus();
          const action = btn.getAttribute("data-action");
          const fd = new FormData();
          fd.set("name", name);

          if (action === "remove"){
            if (!confirm(`Remove ${name}?`)) return;
          }

          try{
            let data;
            if (action === "test"){
              toast("Testing", `Running test for ${name}…`);
              data = await apiPost("/api/test", fd);
            } else if (action === "remove"){
              toast("Removing", `${name}…`);
              data = await apiPost("/api/remove", fd);
            } else {
              return;
            }

            if (data.ok){
              toast("OK", data.message || "Done");
            }else{
              toast("Error", data.message || "Failed");
            }
          }catch(e){
            toast("Error", e && e.message ? e.message : "Failed");
          }finally{
            await refreshState(true);
          }
        });
      });
    });
  }

  // ---- Real-time refresh ----
  function setStatusChip(row, status){
    const chip = row.querySelector(".status-chip");
    const text = row.querySelector(".status-text");
    if (!chip || !text) return;

    chip.classList.remove("status-up","status-down","status-unknown");
    if (status === "up") chip.classList.add("status-up");
    else if (status === "down") chip.classList.add("status-down");
    else chip.classList.add("status-unknown");

    text.textContent = (status || "unknown").toUpperCase();
  }

  function flashIfChanged(el, newText){
    if (!el) return;
    if (el.textContent !== newText){
      el.textContent = newText;
      el.classList.remove("flash");
      void el.offsetWidth;
      el.classList.add("flash");
    }
  }

  async function refreshState(force=false){
    try{
      const res = await fetch("/state", {cache:"no-store"});
      const data = await res.json();
      const map = new Map();
      (data.targets || []).forEach(t => map.set(t.name, t));

      document.querySelectorAll("tr[data-name]").forEach(row => {
        const name = row.getAttribute("data-name");
        const t = map.get(name);
        if (!t) return;

        setStatusChip(row, t.status);

        const lp = row.querySelector(".last-ping");
        const ls = row.querySelector(".last-sent");
        flashIfChanged(lp, t.last_ping_human || "-");
        flashIfChanged(ls, t.last_sent_human || "-");

        // interval input should reflect backend if changed elsewhere
        const iv = row.querySelector(".interval-input");
        if (iv && force){
          iv.value = String(t.interval || 60);
          iv.setAttribute("data-interval", String(t.interval || 60));
        }

        const ep = row.querySelector(".endpoint");
        if (ep) ep.textContent = t.endpoint_masked || "-";
      });

      attachIntervalHandlers();
      attachMenuActions();
    }catch(e){
      // keep quiet
    }
  }

  // init
  attachIntervalHandlers();
  attachMenuActions();
  setInterval(() => refreshState(false), {{ poll_seconds }} * 1000);

  // ESC closes modals
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape"){
      if (logModal.classList.contains("show")) hide(logModal);
      if (addModal.classList.contains("show")) hide(addModal);
      closeAllMenus();
    }
  });

})();
</script>
</body>
</html>
"""

def icon_svg(path_d: str):
    # monochrome line icon
    return f"""<svg width="16" height="16" viewBox="0 0 24 24" fill="none"
      xmlns="http://www.w3.org/2000/svg" style="opacity:.9">
      <path d="{path_d}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>"""

ICONS = {
    "plus": icon_svg("M12 5v14M5 12h14"),
    "logs": icon_svg("M4 6h16M4 12h16M4 18h10"),
    "close": icon_svg("M18 6L6 18M6 6l12 12"),
    "refresh": icon_svg("M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6"),
    "copy": icon_svg("M8 8h12v12H8zM4 4h12v12"),
    "play": icon_svg("M8 5v14l11-7z"),
    "more": icon_svg("M12 5h.01M12 12h.01M12 19h.01"),
    "test": icon_svg("M4 20h16M6 16l6-12 6 12"),
    "trash": icon_svg("M3 6h18M8 6V4h8v2M9 6v14m6-14v14M6 6l1 16h10l1-16"),
}

# ---- Routes ----
@APP.get("/")
def index():
    targets = merged_targets()
    return render_template_string(
        TEMPLATE,
        targets=targets,
        bind_host=BIND_HOST,
        bind_port=BIND_PORT,
        ui_version=UI_VERSION,
        copyright_year=COPYRIGHT_YEAR,
        log_lines=LOG_LINES_DEFAULT,
        poll_seconds=STATE_POLL_SECONDS,
        icons=ICONS
    )

@APP.get("/state")
def state():
    return jsonify({
        "updated": int(time.time()),
        "targets": merged_targets()
    })

@APP.get("/logs")
def logs():
    try:
        lines = int(request.args.get("lines", str(LOG_LINES_DEFAULT)))
    except Exception:
        lines = LOG_LINES_DEFAULT
    lines = max(50, min(1000, lines))

    updated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(time.time())))
    try:
        text = sudo_journalctl(lines)
        src = "journalctl -t interheart"
        actual = len(text.splitlines()) if text else 0
        return jsonify({"source": src, "lines": actual, "updated": updated, "text": text})
    except Exception as e:
        # If journalctl fails, still return something helpful
        return jsonify({"source": "journalctl (error)", "lines": 1, "updated": updated, "text": f"(journalctl error: {str(e)})"})

# ---- API endpoints (used by JS) ----
@APP.post("/api/run-now")
def api_run_now():
    rc, out = run_cmd(["run"])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/test")
def api_test():
    name = request.form.get("name", "")
    rc, out = run_cmd(["test", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/remove")
def api_remove():
    name = request.form.get("name", "")
    rc, out = run_cmd(["remove", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/add")
def api_add():
    name = request.form.get("name", "")
    ip = request.form.get("ip", "")
    endpoint = request.form.get("endpoint", "")
    interval = request.form.get("interval", "60")
    rc, out = run_cmd(["add", name, ip, endpoint, interval])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/set-target-interval")
def api_set_target_interval():
    name = request.form.get("name", "")
    sec = request.form.get("seconds", "")
    rc, out = run_cmd(["set-target-interval", name, sec])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

if __name__ == "__main__":
    APP.run(host=BIND_HOST, port=BIND_PORT)
