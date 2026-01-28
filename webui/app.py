from flask import Flask, request, render_template_string, redirect, url_for, jsonify
import os
import subprocess
import time

APP = Flask(__name__)

CLI = "/usr/local/bin/interheart"
VERSION = "3"

BIND_HOST = os.environ.get("WEBUI_BIND", "0.0.0.0")
BIND_PORT = int(os.environ.get("WEBUI_PORT", "8088"))

STATE_FILE = "/var/lib/interheart/state.json"
LOG_FILE = "/var/log/interheart.log"

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
      --panel:rgba(255,255,255,.04);
      --line:rgba(255,255,255,.08);
      --text:rgba(255,255,255,.92);
      --muted:rgba(255,255,255,.62);
      --blue:#012746;
      --accent:#2a74ff;
      --ok:#23c483;
      --warn:#f7b731;
      --bad:#ff5c5c;

      --shadow: 0 12px 30px rgba(0,0,0,.35);
      --radius: 18px;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    }

    *{box-sizing:border-box}
    body{
      margin:0;
      font-family:var(--sans);
      color:var(--text);
      background:
        radial-gradient(1200px 700px at 20% 10%, rgba(42,116,255,.18), transparent 55%),
        radial-gradient(1000px 600px at 80% 20%, rgba(1,39,70,.35), transparent 60%),
        var(--bg);
    }

    .wrap{max-width:1180px; margin:34px auto; padding:0 18px;}
    .top{display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:16px;}
    .brand{display:flex; flex-direction:column; gap:8px;}
    .title{display:flex; align-items:center; gap:10px; font-size:22px; font-weight:900; letter-spacing:.2px;}
    .pill{
      font-size:12px; padding:5px 10px; border-radius:999px;
      background:linear-gradient(180deg, rgba(42,116,255,.18), rgba(42,116,255,.05));
      border:1px solid var(--line); color:var(--muted);
    }
    .subtitle{color:var(--muted); font-size:13px; line-height:1.4}

    .grid{display:grid; grid-template-columns: 1.25fr .75fr; gap:16px;}
    .card{
      background:linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.02));
      border:1px solid var(--line);
      border-radius:var(--radius);
      box-shadow: var(--shadow);
      padding:16px;
      position:relative;
      overflow:hidden;
    }

    .card:before{
      content:"";
      position:absolute;
      inset:-60px -60px auto auto;
      width:220px; height:220px;
      background: radial-gradient(circle at 30% 30%, rgba(42,116,255,.24), transparent 60%);
      transform: rotate(10deg);
      pointer-events:none;
      opacity:.65;
    }

    .row{display:flex; gap:10px; flex-wrap:wrap; align-items:center}
    .sep{height:1px; background:var(--line); margin:12px 0;}
    h3{margin:0 0 10px 0; font-size:14px; color:rgba(255,255,255,.86); font-weight:850}

    input, button{
      border-radius:14px;
      border:1px solid var(--line);
      background:rgba(0,0,0,.18);
      color:var(--text);
      padding:10px 12px;
      outline:none;
      transition: transform .12s ease, border-color .12s ease, filter .12s ease;
    }
    input{flex:1; min-width:170px;}
    input::placeholder{color:rgba(255,255,255,.35)}

    /* “AU-scraper-ish” knapper: tydelig, moderne, litt “glow” */
    button{
      cursor:pointer;
      font-weight:850;
      background: linear-gradient(180deg, rgba(42,116,255,.30), rgba(42,116,255,.08));
    }
    button:hover{border-color: rgba(42,116,255,.42); transform: translateY(-1px); filter: brightness(1.06)}
    button:active{transform: translateY(0px) scale(.98)}

    .btn-ghost{background: rgba(255,255,255,.05);}
    .btn-danger{
      background: linear-gradient(180deg, rgba(255,92,92,.26), rgba(255,92,92,.08));
    }
    .btn-ok{
      background: linear-gradient(180deg, rgba(35,196,131,.22), rgba(35,196,131,.06));
    }

    .mini{font-size:12px; padding:8px 10px; border-radius:12px;}

    table{width:100%; border-collapse:collapse; overflow:hidden; border-radius:14px;}
    th, td{padding:10px 10px; border-bottom:1px solid var(--line); font-size:13px;}
    th{color:var(--muted); font-weight:850; text-align:left}
    td code{font-family:var(--mono); font-size:12px; color:rgba(255,255,255,.88)}

    .chip{
      display:inline-flex; align-items:center; gap:8px;
      padding:6px 10px; border-radius:999px;
      background:rgba(255,255,255,.06); border:1px solid var(--line);
      color:var(--muted); font-size:12px;
    }
    .dot{width:10px;height:10px;border-radius:999px; display:inline-block;}
    .dot.up{background: var(--ok); box-shadow: 0 0 14px rgba(35,196,131,.25);}
    .dot.down{background: var(--bad); box-shadow: 0 0 14px rgba(255,92,92,.25);}
    .dot.err{background: var(--warn); box-shadow: 0 0 14px rgba(247,183,49,.25);}
    .dot.pinging{
      background: var(--accent);
      box-shadow: 0 0 16px rgba(42,116,255,.35);
      animation: pulse 1.2s ease-in-out infinite;
    }

    @keyframes pulse{
      0%{transform:scale(1); opacity:.75}
      50%{transform:scale(1.35); opacity:1}
      100%{transform:scale(1); opacity:.75}
    }

    .hint{color:rgba(255,255,255,.55); font-size:12px}

    .msg{
      border:1px solid var(--line);
      background:rgba(255,255,255,.03);
      border-radius:14px;
      padding:12px;
      color:var(--muted);
      font-size:13px;
      margin-bottom:14px;
    }

    /* Modal */
    .modal-backdrop{
      position:fixed; inset:0; background:rgba(0,0,0,.62);
      display:none; align-items:center; justify-content:center;
      padding:18px;
    }
    .modal{
      width:min(980px, 100%);
      background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.03));
      border:1px solid var(--line);
      border-radius: 22px;
      box-shadow: 0 20px 60px rgba(0,0,0,.55);
      overflow:hidden;
    }
    .modal-head{
      display:flex; justify-content:space-between; align-items:center;
      padding:14px 14px;
      border-bottom:1px solid var(--line);
    }
    .modal-title{font-weight:900}
    .modal-body{
      padding:14px;
      font-family:var(--mono);
      font-size:12px;
      color:rgba(255,255,255,.78);
      white-space:pre-wrap;
      max-height: 65vh;
      overflow:auto;
      background:rgba(0,0,0,.18);
    }

    .footer{
      margin-top:14px;
      color:var(--muted);
      font-size:12px;
      display:flex;
      justify-content:space-between;
      gap:10px;
      flex-wrap:wrap;
      opacity:.9;
    }
    .footer a{color:rgba(255,255,255,.86); text-decoration:none}
    .footer a:hover{text-decoration:underline}

    @media (max-width: 980px){
      .grid{grid-template-columns:1fr;}
    }
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="brand">
      <div class="title">interheart <span class="pill">ping → endpoint</span></div>
      <div class="subtitle">
        Per-target intervall, status og countdown. Ping OK → endpoint request. Ping feiler → ingenting sendes.
      </div>
    </div>

    <div class="row">
      <form method="post" action="/run-now" style="display:inline">
        <button class="mini btn-ok" type="submit">Kjør nå</button>
      </form>
      <button class="mini btn-ghost" type="button" onclick="openLogs()">Logg</button>
    </div>
  </div>

  {% if message %}
    <div class="msg"><b>{{ message }}</b></div>
  {% endif %}

  <div class="grid">
    <div class="card">
      <h3>Targets</h3>
      <div class="hint">Hver target har egen interval. UI oppdateres automatisk og viser tid til neste ping.</div>
      <div class="sep"></div>

      <table>
        <thead>
          <tr>
            <th>Status</th>
            <th>Name</th>
            <th>IP</th>
            <th>Intervall</th>
            <th>Neste ping</th>
            <th>RTT</th>
            <th>Handling</th>
          </tr>
        </thead>
        <tbody id="targets-body">
          <!-- Filled by JS -->
        </tbody>
      </table>

      <div class="sep"></div>

      <h3>Legg til target</h3>
      <form method="post" action="/add">
        <div class="row">
          <input name="name" placeholder="name (f.eks anl-0161-core-gw)" required>
          <input name="ip" placeholder="ip (f.eks 10.5.0.1)" required>
          <input name="interval" type="number" min="5" max="86400" step="1" placeholder="interval (sek)" required>
        </div>
        <div class="row">
          <input name="endpoint" placeholder="endpoint url (https://...)" required>
          <button type="submit">Legg til</button>
        </div>
      </form>
    </div>

    <div class="card">
      <h3>Driftsstatus</h3>
      <div class="row">
        <span class="chip"><span class="dot pinging"></span> Scheduler: <b id="sched-status">—</b></span>
        <span class="chip">Sist oppdatert: <b id="last-updated">—</b></span>
      </div>
      <div class="sep"></div>

      <div class="hint">
        Tips: systemd kjører “scheduler-check” hvert 5. sekund og pinger kun targets som er due.
      </div>

      <div class="sep"></div>

      <h3>Hurtigvalg</h3>
      <div class="row">
        <button class="mini btn-ghost" type="button" onclick="refreshNow()">Oppdater nå</button>
        <button class="mini btn-ghost" type="button" onclick="openLogs()">Åpne logg</button>
      </div>

      <div class="footer">
        <div>
          UI v{{version}} · <a href="#" onclick="return false;">5echo.io</a> © 2026 All rights reserved
        </div>
        <div class="hint">
          Bind: <code>{{ bind_host }}:{{ bind_port }}</code>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- LOG MODAL -->
<div class="modal-backdrop" id="modal-backdrop" onclick="closeLogs(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <div class="modal-head">
      <div class="modal-title">Ping-logg</div>
      <button class="mini btn-ghost" type="button" onclick="closeLogs()">Lukk</button>
    </div>
    <div class="modal-body" id="logs-body">(laster...)</div>
  </div>
</div>

<script>
  const VERSION = "{{version}}";

  function dotClass(status){
    if(status === "UP") return "up";
    if(status === "DOWN") return "down";
    if(status === "ERR") return "err";
    if(status === "PINGING") return "pinging";
    return "err";
  }

  function fmtSeconds(s){
    s = Math.max(0, parseInt(s || 0));
    if(s < 60) return s + "s";
    const m = Math.floor(s/60);
    const r = s % 60;
    if(m < 60) return m + "m " + r + "s";
    const h = Math.floor(m/60);
    const mm = m % 60;
    return h + "t " + mm + "m";
  }

  async function fetchState(){
    const r = await fetch("/api/state");
    return await r.json();
  }

  async function refreshNow(){
    await renderState(true);
  }

  async function renderState(force){
    const data = await fetchState();
    const tbody = document.getElementById("targets-body");
    tbody.innerHTML = "";

    document.getElementById("sched-status").textContent = data.scheduler_status;
    document.getElementById("last-updated").textContent = data.last_updated_human;

    data.targets.forEach(t => {
      const tr = document.createElement("tr");

      const statusTd = document.createElement("td");
      statusTd.innerHTML = `<span class="chip"><span class="dot ${dotClass(t.status)}"></span><b>${t.status}</b></span>`;
      tr.appendChild(statusTd);

      const nameTd = document.createElement("td");
      nameTd.innerHTML = `<code>${t.name}</code>`;
      tr.appendChild(nameTd);

      const ipTd = document.createElement("td");
      ipTd.innerHTML = `<code>${t.ip}</code>`;
      tr.appendChild(ipTd);

      const intTd = document.createElement("td");
      intTd.innerHTML = `<code>${t.interval}s</code>`;
      tr.appendChild(intTd);

      const nextTd = document.createElement("td");
      nextTd.innerHTML = `<code>${fmtSeconds(t.next_in)}</code>`;
      tr.appendChild(nextTd);

      const rttTd = document.createElement("td");
      rttTd.innerHTML = `<code>${t.rtt_ms}ms</code>`;
      tr.appendChild(rttTd);

      const actionsTd = document.createElement("td");
      actionsTd.innerHTML = `
        <div class="row">
          <form method="post" action="/test" style="display:inline">
            <input type="hidden" name="name" value="${t.name}">
            <button class="mini btn-ghost" type="submit">Test</button>
          </form>

          <form method="post" action="/set-interval" style="display:inline">
            <input type="hidden" name="name" value="${t.name}">
            <input name="seconds" type="number" min="5" max="86400" step="1"
                   value="${t.interval}" style="width:110px; min-width:110px;">
            <button class="mini" type="submit">Sett</button>
          </form>

          <form method="post" action="/remove" style="display:inline" onsubmit="return confirm('Fjerne ${t.name}?');">
            <input type="hidden" name="name" value="${t.name}">
            <button class="mini btn-danger" type="submit">Fjern</button>
          </form>
        </div>
      `;
      tr.appendChild(actionsTd);

      tbody.appendChild(tr);
    });
  }

  async function openLogs(){
    document.getElementById("modal-backdrop").style.display = "flex";
    const r = await fetch("/api/log?lines=200");
    const data = await r.json();
    document.getElementById("logs-body").textContent = data.text || "(ingen logg ennå)";
