from flask import Flask, request, render_template_string, redirect, url_for, jsonify
import os
import subprocess
import time

APP = Flask(__name__)

# SemVer from VERSION file
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
BIND_HOST = os.environ.get("WEBUI_BIND", "127.0.0.1")
BIND_PORT = int(os.environ.get("WEBUI_PORT", "8088"))

LOG_LINES_DEFAULT = 200
LOG_FILE_FALLBACK = "/var/log/interheart.log"

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
      --line:rgba(255,255,255,.085);
      --text:rgba(255,255,255,.92);
      --muted:rgba(255,255,255,.62);

      --navy:#012746;
      --accent:#2a74ff;
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
    input:focus{ border-color:rgba(42,116,255,.45); filter:brightness(1.03); }

    .btn{
      border-radius:14px; border:1px solid var(--line);
      padding:10px 12px; cursor:pointer; font-weight:850; color:var(--text);
      background:rgba(255,255,255,.04);
      transition: transform .12s ease, border-color .12s ease, filter .12s ease, background .12s ease;
      display:inline-flex; align-items:center; gap:8px; user-select:none;
    }
    .btn:hover{transform: translateY(-1px); filter:brightness(1.03); border-color:rgba(42,116,255,.35);}
    .btn:active{transform: translateY(0px); filter:brightness(.98);}

    .btn-primary{
      background:linear-gradient(180deg, rgba(42,116,255,.26), rgba(42,116,255,.07));
      border-color:rgba(42,116,255,.30);
    }
    .btn-primary:hover{border-color:rgba(42,116,255,.55);}

    .btn-secondary{ background:linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.03)); }
    .btn-danger{
      background:linear-gradient(180deg, rgba(255,59,92,.22), rgba(255,59,92,.07));
      border-color:rgba(255,59,92,.28);
    }
    .btn-danger:hover{border-color:rgba(255,59,92,.50);}

    .btn-mini{font-size:12px; padding:8px 10px; border-radius:12px;}
    .icon{width:14px; height:14px; display:inline-block; opacity:.9;}
    .sep{height:1px; background:var(--line); margin:12px 0;}

    table{width:100%; border-collapse:collapse; overflow:hidden; border-radius:14px;}
    th, td{padding:10px 10px; border-bottom:1px solid var(--line); font-size:13px; vertical-align:top;}
    th{color:var(--muted); font-weight:850; text-align:left}
    td code{font-family:var(--mono); font-size:12px; color:rgba(255,255,255,.88)}

    .chip{
      display:inline-flex; align-items:center; gap:8px;
      padding:6px 10px; border-radius:999px; background:var(--chip); border:1px solid var(--line);
      color:var(--muted); font-size:12px; backdrop-filter: blur(6px);
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
      border-radius:14px; padding:12px; color:var(--muted); font-size:13px; margin-bottom:14px;
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
    .footer a:hover{ color:rgba(255,255,255,.94); border-bottom-color:rgba(255,255,255,.35); }

    .hint{color:rgba(255,255,255,.55); font-size:12px}
    .right-actions{display:flex; gap:10px; align-items:center; flex-wrap:wrap;}
    .countdown{font-family:var(--mono); font-size:12px; color:rgba(255,255,255,.80)}
    .small{font-size:12px; color:rgba(255,255,255,.62)}
    .muted{color:rgba(255,255,255,.62)}
    .nowrap{white-space:nowrap}

    /* Modal + chips + live tail styles kept from v7 */
    .modal{
      position:fixed; inset:0; display:none; align-items:center; justify-content:center;
      z-index:9997; padding:18px; background:rgba(0,0,0,.52); backdrop-filter: blur(10px);
    }
    .modal.show{display:flex;}
    .modal-card{
      width:min(1100px, calc(100vw - 24px));
      max-height: min(80vh, 820px);
      display:flex; flex-direction:column;
      border:1px solid var(--line); border-radius:22px;
      background:rgba(10,14,24,.86);
      box-shadow: 0 26px 70px rgba(0,0,0,.70);
      overflow:hidden;
    }
    .modal-head{
      padding:12px 12px; border-bottom:1px solid var(--line);
      display:flex; gap:10px; align-items:flex-start; justify-content:space-between;
    }
    .modal-title{display:flex; flex-direction:column; gap:2px;}
    .modal-title b{font-size:14px}
    .modal-title span{font-size:12px; color:rgba(255,255,255,.62)}
    .modal-actions{display:flex; gap:10px; flex-wrap:wrap; align-items:center; justify-content:flex-end;}
    .modal-body{padding:12px; overflow:auto; flex:1; display:flex; flex-direction:column; gap:10px;}
    .chips{
      display:flex; flex-wrap:wrap; gap:8px; padding:10px;
      border:1px solid var(--line); background:rgba(0,0,0,.18); border-radius:18px;
    }
    .chip-btn{
      cursor:pointer; user-select:none; padding:7px 10px; border-radius:999px;
      border:1px solid var(--line); background:rgba(255,255,255,.04);
      color:rgba(255,255,255,.74); font-size:12px; font-weight:850;
      transition: transform .12s ease, border-color .12s ease, filter .12s ease, background .12s ease;
      display:inline-flex; align-items:center; gap:8px;
    }
    .chip-btn:hover{transform: translateY(-1px); filter:brightness(1.03); border-color:rgba(42,116,255,.35);}
    .chip-btn:active{transform: translateY(0px); filter:brightness(.98);}
    .chip-btn.active{
      border-color:rgba(42,116,255,.55);
      background:linear-gradient(180deg, rgba(42,116,255,.20), rgba(42,116,255,.06));
      color:rgba(255,255,255,.90);
    }
    .logbox{
      width:100%; min-height: 360px;
      background:rgba(0,0,0,.25); border:1px solid var(--line); border-radius:16px;
      padding:12px; font-family:var(--mono); font-size:12px; line-height:1.45;
      color:rgba(255,255,255,.84); white-space:pre; overflow:auto; position:relative;
    }
    .logbox.loading:after{
      content:"Oppdaterer…"; position:absolute; top:12px; right:12px;
      font-family:var(--sans); font-size:12px; font-weight:900;
      color:rgba(255,255,255,.70);
      background:rgba(10,14,24,.60); border:1px solid var(--line);
      padding:6px 10px; border-radius:999px; backdrop-filter: blur(10px);
    }
    .pill{
      display:inline-flex; align-items:center; gap:8px;
      border:1px solid var(--line); background:rgba(0,0,0,.18);
      padding:7px 10px; border-radius:999px; font-family:var(--mono);
      font-size:11px; color:rgba(255,255,255,.70);
    }
    .live-dot{width:8px; height:8px; border-radius:99px; background:rgba(255,255,255,.25);}
    .pill.on{border-color:rgba(56,211,159,.25); background:rgba(56,211,159,.09);}
    .pill.on .live-dot{background:var(--good); box-shadow:0 0 0 0 rgba(56,211,159,.35); animation:pulse 1.4s infinite;}

    .toggle{
      display:inline-flex; align-items:center; gap:8px;
      border:1px solid var(--line); background:rgba(0,0,0,.18);
      padding:7px 10px; border-radius:14px; cursor:pointer; user-select:none;
      transition: border-color .12s ease, filter .12s ease;
    }
    .toggle:hover{border-color:rgba(42,116,255,.35); filter:brightness(1.03);}
    .switch{width:34px; height:18px; border-radius:999px; background:rgba(255,255,255,.12); border:1px solid var(--line); position:relative;}
    .knob{position:absolute; top:1px; left:1px; width:14px; height:14px; border-radius:99px; background:rgba(255,255,255,.70); transition: transform .14s ease, background .14s ease;}
    .toggle.on .switch{background:rgba(42,116,255,.22); border-color:rgba(42,116,255,.30);}
    .toggle.on .knob{transform: translateX(16px); background:rgba(255,255,255,.92);}

    @media (max-width: 940px){
      .footer{flex-direction:column; align-items:flex-start;}
      .modal-head{flex-direction:column; align-items:stretch;}
      .modal-actions{justify-content:flex-start;}
    }
  </style>
</head>
<body>

<div class="modal" id="logModal" aria-hidden="true">
  <div class="modal-card" role="dialog" aria-modal="true" aria-label="Logg">
    <div class="modal-head">
      <div class="modal-title">
        <b>Logg</b>
        <span>Siste <span id="logLinesLbl">{{ log_lines }}</span> linjer • target-chips • live tail</span>
      </div>
      <div class="modal-actions">
        <input id="logFilter" placeholder="filter (f.eks. anl-0161)" style="min-width:220px;">
        <button class="btn btn-secondary btn-mini" id="btnReloadLogs" type="button"><span class="icon">⟳</span> Last på nytt</button>
        <button class="btn btn-secondary btn-mini" id="btnCopyLogs" type="button"><span class="icon">⧉</span> Copy</button>

        <div class="toggle" id="liveToggle" title="Live tail (poll hver 3s)">
          <div class="switch"><div class="knob"></div></div>
          <div>
            <div style="font-weight:900; font-size:12px;">Live tail</div>
            <small>3s</small>
          </div>
        </div>

        <div class="toggle" id="followToggle" title="Hold scroller i bunn ved nye linjer">
          <div class="switch"><div class="knob"></div></div>
          <div>
            <div style="font-weight:900; font-size:12px;">Follow</div>
            <small>bottom</small>
          </div>
        </div>

        <button class="btn btn-danger btn-mini" id="btnCloseLogs" type="button"><span class="icon">✕</span> Lukk</button>
      </div>
    </div>

    <div class="modal-body">
      <div class="chips" id="targetChips"><span class="hint">Laster targets…</span></div>
      <div class="logbox" id="logBox">Laster logg…</div>

      <div class="row" style="justify-content:space-between;">
        <div class="pill" id="livePill"><span class="live-dot"></span> LIVE: OFF</div>
        <div class="muted" id="logMeta">-</div>
      </div>
    </div>

    <div class="footer" style="border-top:1px solid var(--line); padding:10px 12px; margin-top:0;">
      <div class="muted">Tips: ESC lukker. Klikk chip → filter. Live tail kan stå på mens du feilsøker.</div>
      <div class="muted">interheart <code>{{ ui_version }}</code></div>
    </div>
  </div>
</div>

<div class="wrap">
  <div class="top">
    <div class="brand">
      <div class="title">interheart <span class="badge">targets</span></div>
      <div class="subtitle">SemVer: <code>{{ ui_version }}</code></div>
    </div>

    <div class="right-actions">
      <button class="btn btn-secondary btn-mini" id="openLogs" type="button"><span class="icon">🧾</span> Logg</button>

      <form method="post" action="/run-now">
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
    <div class="hint">Status/last ping/sent kommer fra state. (countdown kan vi legge inn igjen om du vil – dette er den “stabile” SemVer-migrasjonen).</div>
    <div class="sep"></div>

    <table>
      <thead>
        <tr>
          <th style="width: 200px;">Name</th>
          <th style="width: 120px;">IP</th>
          <th style="width: 120px;">Status</th>
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
          <td><span class="chip nowrap">{{ t.interval }}s</span></td>
          <td><code>{{ t.last_ping_human }}</code></td>
          <td><code>{{ t.last_sent_human }}</code></td>
          <td><code>{{ t.endpoint_masked }}</code></td>

          <td class="row">
            <form method="post" action="/set-target-interval" style="display:inline">
              <input type="hidden" name="name" value="{{ t.name }}">
              <input class="btn-mini" style="width:110px" name="seconds" type="number" min="10" max="86400" step="1" placeholder="sek" required>
              <button class="btn btn-secondary btn-mini" type="submit"><span class="icon">⏱</span> Intervall</button>
            </form>

            <form method="post" action="/test" style="display:inline">
              <input type="hidden" name="name" value="{{ t.name }}">
              <button class="btn btn-secondary btn-mini" type="submit"><span class="icon">🧪</span> Test</button>
            </form>

            <form method="post" action="/remove" style="display:inline" onsubmit="return confirm('Fjerne {{ t.name }}?');">
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
    <form method="post" action="/add">
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
        <span class="hint">• interheart <code>{{ ui_version }}</code></span>
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
  // Logs modal (Step 7 behavior retained)
  var modal = document.getElementById("logModal");
  var openBtn = document.getElementById("openLogs");
  var closeBtn = document.getElementById("btnCloseLogs");
  var reloadBtn = document.getElementById("btnReloadLogs");
  var copyBtn = document.getElementById("btnCopyLogs");
  var logBox = document.getElementById("logBox");
  var logMeta = document.getElementById("logMeta");
  var filter = document.getElementById("logFilter");
  var chipsWrap = document.getElementById("targetChips");

  var liveToggle = document.getElementById("liveToggle");
  var followToggle = document.getElementById("followToggle");
  var livePill = document.getElementById("livePill");

  var rawLog = "";
  var liveOn = false;
  var followBottom = true;
  var liveTimer = null;
  var LIVE_INTERVAL_MS = 3000;

  var activeChip = "";

  function openModal(){
    modal.classList.add("show");
    modal.setAttribute("aria-hidden","false");
    filter.focus();
  }
  function closeModal(){
    stopLive();
    modal.classList.remove("show");
    modal.setAttribute("aria-hidden","true");
  }

  function setLivePill(){
    if (liveOn){
      livePill.classList.add("on");
      livePill.innerHTML = '<span class="live-dot"></span> LIVE: ON';
    } else {
      livePill.classList.remove("on");
      livePill.innerHTML = '<span class="live-dot"></span> LIVE: OFF';
    }
  }

  async function loadLogs(silent){
    if (!silent) logBox.classList.add("loading");
    try{
      const res = await fetch("/logs?lines={{ log_lines }}", {cache:"no-store"});
      const data = await res.json();
      rawLog = data.text || "";
      logMeta.textContent = (data.source || "log") + " • " + (data.lines || 0) + " linjer • " + (data.updated || "");
      applyFilter();
      if (followBottom){
        logBox.scrollTop = logBox.scrollHeight;
      }
    }catch(e){
      rawLog = "";
      logBox.textContent = "Kunne ikke hente logg: " + (e && e.message ? e.message : "ukjent feil");
      logMeta.textContent = "error";
    }finally{
      logBox.classList.remove("loading");
    }
  }

  function applyFilter(){
    var q = (filter.value || "").trim().toLowerCase();
    if (!q){
      logBox.textContent = rawLog || "(tom logg)";
      return;
    }
    var lines = (rawLog || "").split("\n").filter(function(l){
      return l.toLowerCase().indexOf(q) !== -1;
    });
    logBox.textContent = lines.join("\n") || "(ingen treff)";
  }

  function renderChips(){
    chipsWrap.innerHTML = "";
    var allBtn = document.createElement("button");
    allBtn.type = "button";
    allBtn.className = "chip-btn" + (activeChip === "" ? " active" : "");
    allBtn.textContent = "ALL";
    allBtn.addEventListener("click", function(){
      activeChip = "";
      filter.value = "";
      renderChips();
      applyFilter();
    });
    chipsWrap.appendChild(allBtn);

    (window.__targets || []).forEach(function(t){
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip-btn" + (activeChip === t.name ? " active" : "");
      btn.textContent = t.name;
      btn.addEventListener("click", function(){
        activeChip = t.name;
        filter.value = t.name;
        renderChips();
        applyFilter();
      });
      chipsWrap.appendChild(btn);
    });

    if ((window.__targets || []).length === 0){
      var s = document.createElement("span");
      s.className = "hint";
      s.textContent = "Ingen targets funnet.";
      chipsWrap.appendChild(s);
    }
  }

  function startLive(){
    if (liveTimer) return;
    liveOn = true;
    setLivePill();
    liveTimer = setInterval(function(){ loadLogs(true); }, LIVE_INTERVAL_MS);
  }

  function stopLive(){
    liveOn = false;
    setLivePill();
    if (liveTimer){
      clearInterval(liveTimer);
      liveTimer = null;
    }
  }

  function setToggle(el, on){
    if (on) el.classList.add("on"); else el.classList.remove("on");
  }

  openBtn.addEventListener("click", async function(){
    openModal();
    renderChips();
    await loadLogs(false);
    if (followBottom) logBox.scrollTop = logBox.scrollHeight;
  });

  closeBtn.addEventListener("click", function(){ closeModal(); });

  reloadBtn.addEventListener("click", async function(){ await loadLogs(false); });

  copyBtn.addEventListener("click", async function(){
    try{ await navigator.clipboard.writeText(logBox.textContent || ""); }catch(e){}
  });

  filter.addEventListener("input", function(){
    activeChip = "";
    renderChips();
    applyFilter();
  });

  liveToggle.addEventListener("click", function(){
    var newState = !liveOn;
    if (newState){
      setToggle(liveToggle, true);
      startLive();
      loadLogs(true);
    } else {
      setToggle(liveToggle, false);
      stopLive();
    }
  });

  followToggle.addEventListener("click", function(){
    followBottom = !followBottom;
    setToggle(followToggle, followBottom);
    if (followBottom) logBox.scrollTop = logBox.scrollHeight;
  });

  setToggle(liveToggle, false);
  setToggle(followToggle, true);
  setLivePill();

  document.addEventListener("keydown", function(e){
    if (e.key === "Escape" && modal.classList.contains("show")) closeModal();
  });
  modal.addEventListener("click", function(e){
    if (e.target === modal) closeModal();
  });
})();
</script>

<script>
window.__targets = {{ targets_json | safe }};
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
    raise RuntimeError((p.stderr or "journalctl feilet").strip())
  return (p.stdout or "").strip()

def read_log_file(lines: int) -> str:
  if not os.path.exists(LOG_FILE_FALLBACK):
    return ""
  try:
    with open(LOG_FILE_FALLBACK, "r", encoding="utf-8", errors="replace") as f:
      data = f.read().splitlines()
    return "\n".join(data[-lines:])
  except Exception:
    return ""

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
    last_ping_epoch = st.get("last_ping_epoch", 0)
    last_sent_epoch = st.get("last_sent_epoch", 0)

    merged.append({
      **t,
      "status": status,
      "last_ping_human": human_ts(last_ping_epoch),
      "last_sent_human": human_ts(last_sent_epoch),
    })

  targets_json = [{"name": t["name"], "ip": t["ip"]} for t in targets]
  import json

  return render_template_string(
    TEMPLATE,
    targets=merged,
    bind_host=BIND_HOST,
    bind_port=BIND_PORT,
    message=message,
    ui_version=UI_VERSION,
    copyright_year=COPYRIGHT_YEAR,
    log_lines=LOG_LINES_DEFAULT,
    targets_json=json.dumps(targets_json)
  )

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
    text = read_log_file(lines)
    src = "file: /var/log/interheart.log (fallback)"
    actual = len(text.splitlines()) if text else 0
    if not text:
      text = f"(ingen logg funnet)\n(journalctl-feil: {str(e)})"
      actual = len(text.splitlines())
    return jsonify({"source": src, "lines": actual, "updated": updated, "text": text})

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
