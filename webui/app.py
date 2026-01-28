from flask import Flask, request, render_template_string, jsonify
from markupsafe import Markup
import os
import subprocess
import time
import json
import re

APP = Flask(__name__)

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

STATE_DIR = "/var/lib/interheart"
RUNTIME_FILE = os.path.join(STATE_DIR, "runtime.json")

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
        if line.strip().startswith("NAME") or line.strip().startswith("State:"):
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
            "last_response_human": human_ts(last_sent_epoch),
            "last_ping_epoch": last_ping_epoch,
            "last_response_epoch": last_sent_epoch,
        })
    return merged

SUMMARY_RE = re.compile(
    r"total=(\d+)\s+due=(\d+)\s+skipped=(\d+)\s+ping_ok=(\d+)\s+ping_fail=(\d+)\s+sent=(\d+)\s+curl_fail=(\d+)"
)

def parse_run_summary(text: str):
    m = SUMMARY_RE.search(text or "")
    if not m:
        return None
    return {
        "total": int(m.group(1)),
        "due": int(m.group(2)),
        "skipped": int(m.group(3)),
        "ping_ok": int(m.group(4)),
        "ping_fail": int(m.group(5)),
        "sent": int(m.group(6)),
        "curl_fail": int(m.group(7)),
    }

TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>interheart</title>

  <style>
    :root{
      --bg:#091626;
      --panel: rgba(12,18,32,.62);
      --panel2: rgba(12,18,32,.78);
      --line: rgba(255,255,255,.10);

      --text: rgba(255,255,255,.92);
      --muted: rgba(255,255,255,.60);

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

    .subtitle{color:var(--muted);font-size:13px;display:flex;align-items:center;gap:10px}
    .subtitle a{color:rgba(255,255,255,.85);text-decoration:none;border-bottom:1px solid rgba(255,255,255,.18)}
    .subtitle a:hover{border-bottom-color:rgba(255,255,255,.32)}

    .card{
      background: linear-gradient(180deg, rgba(255,255,255,.040), rgba(255,255,255,.018));
      border:1px solid rgba(255,255,255,.10);
      border-radius:var(--radius);
      box-shadow: var(--shadow);
      padding:16px;
      overflow:hidden;
      backdrop-filter: blur(10px);
    }

    .hint{color:rgba(255,255,255,.52);font-size:12px}
    .sep{height:1px;background:var(--line);margin:12px 0}

    input{
      border-radius:14px;
      border:1px solid var(--line);
      background:rgba(255,255,255,.03);
      color:var(--text);
      padding:10px 12px;
      outline:none;
      transition: border-color .15s ease, filter .15s ease, background .15s ease;
      font-family:var(--sans);
    }
    input:focus{
      border-color:rgba(255,255,255,.24);
      filter:brightness(1.03);
      background:rgba(255,255,255,.04);
    }
    input::placeholder{color:rgba(255,255,255,.30)}

    .btn{
      border-radius:14px;
      border:1px solid rgba(255,255,255,.12);
      padding:10px 12px;
      cursor:pointer;
      font-weight:850;
      color:rgba(255,255,255,.90);
      background:rgba(255,255,255,.03);
      transition: transform .12s ease, border-color .12s ease, background .12s ease, filter .12s ease;
      display:inline-flex;
      align-items:center;
      justify-content:center;
      gap:8px;
      user-select:none;
      height:36px;
      line-height:1;
    }
    .btn:hover{
      transform: translateY(-1px);
      border-color: rgba(255,255,255,.20);
      background:rgba(255,255,255,.04);
      filter:brightness(1.03);
    }
    .btn:active{transform: translateY(0px)}
    .btn-mini{font-size:12px;padding:0 12px;border-radius:12px;height:34px}
    .btn-ghost{background:transparent;border-color:rgba(255,255,255,.12)}
    .btn-ghost:hover{border-color:rgba(255,255,255,.22)}
    .btn-primary{border-color:rgba(255,255,255,.22);background:rgba(255,255,255,.06)}
    .btn-danger{
      border-color:rgba(255,59,92,.28);
      background:rgba(255,59,92,.10);
    }
    .btn-danger:hover{
      border-color:rgba(255,59,92,.40);
      background:rgba(255,59,92,.14);
    }

    .right-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}

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
      white-space:nowrap;
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

    .interval-wrap{display:flex;align-items:center;gap:8px}
    .interval-input{
      width:86px;height:34px;padding:8px 10px;border-radius:12px;font-weight:850;
      font-family:var(--mono);
      background:rgba(255,255,255,.03);
    }
    .interval-suffix{color:rgba(255,255,255,.45);font-size:12px;font-weight:850}

    .menu{position:relative;display:inline-block}
    .menu-btn{width:40px;height:34px;display:inline-flex;align-items:center;justify-content:center;border-radius:12px}
    .menu-dd{
      position:absolute;right:0;top:42px;width:220px;
      background:rgba(10,16,28,.96);
      border:1px solid rgba(255,255,255,.12);
      border-radius:14px;
      box-shadow: 0 22px 60px rgba(0,0,0,.70);
      padding:6px;
      display:none;
      z-index:50;
      transform-origin: top right;
      animation: pop .14s ease;
    }
    @keyframes pop{from{transform:translateY(-4px) scale(.98);opacity:.70}to{transform:translateY(0) scale(1);opacity:1}}
    .menu.show .menu-dd{display:block}
    .menu-item{
      width:100%;border:0;background:transparent;color:rgba(255,255,255,.86);
      padding:10px 10px;border-radius:12px;cursor:pointer;
      display:flex;align-items:center;gap:10px;font-weight:850;height:38px;
    }
    .menu-item:hover{background:rgba(255,255,255,.06)}
    .menu-item.danger:hover{background:rgba(255,59,92,.10)}

    .toasts{
      position:fixed;top:18px; right:18px;display:flex;flex-direction:column;gap:10px;
      z-index:9999;width:min(460px, calc(100vw - 24px));pointer-events:none;
    }
    .toast{
      pointer-events:auto;border-radius:16px;border:1px solid rgba(255,255,255,.12);
      background:rgba(10,16,28,.92);box-shadow: 0 18px 54px rgba(0,0,0,.70);
      padding:12px 12px;display:flex;gap:10px;align-items:flex-start;animation: toastIn .14s ease;
    }
    @keyframes toastIn{from{transform:translateY(-6px);opacity:.65}to{transform:translateY(0);opacity:1}}
    .toast b{font-size:13px}
    .toast p{margin:2px 0 0 0;font-size:12px;color:rgba(255,255,255,.64);line-height:1.35}
    .toast .x{margin-left:auto;cursor:pointer;border:0;background:transparent;color:rgba(255,255,255,.70);font-weight:900}

    .modal{
      position:fixed;inset:0;display:none;align-items:center;justify-content:center;
      z-index:9997;padding:26px;background:rgba(0,0,0,.60);backdrop-filter: blur(12px);
    }
    .modal.show{display:flex}
    .modal-card{
      width:min(980px, calc(100vw - 40px));
      max-height:min(82vh, 880px);
      display:flex;flex-direction:column;
      border:1px solid rgba(255,255,255,.12);
      border-radius:22px;
      background:rgba(10,16,28,.94);
      box-shadow: 0 26px 70px rgba(0,0,0,.72);
      overflow:hidden;
    }
    .modal-card.small{
      width:min(560px, calc(100vw - 40px));
      max-height:none;
    }
    .modal-head{
      padding:14px 14px;border-bottom:1px solid rgba(255,255,255,.10);
      display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:nowrap;
    }
    .modal-title{display:flex;align-items:center;gap:10px;min-width:0;white-space:nowrap}
    .modal-title b{font-size:14px}
    .modal-title span{font-size:12px;color:rgba(255,255,255,.62)}
    .modal-actions{display:flex;gap:10px;align-items:center;justify-content:flex-end;flex-wrap:nowrap}

    .modal-body{padding:16px;overflow:auto;flex:1;display:flex;flex-direction:column;gap:12px}

    .logbox{
      width:100%;min-height:380px;background:rgba(255,255,255,.03);
      border:1px solid rgba(255,255,255,.10);border-radius:16px;padding:12px;
      font-family:var(--mono);font-size:12px;line-height:1.45;color:rgba(255,255,255,.84);
      white-space:pre;overflow:auto;position:relative;
    }

    .flash{animation: flash .80s ease;border-radius:10px;padding:2px 6px}
    @keyframes flash{0%{background:rgba(255,255,255,.18)}100%{background:transparent}}

    tr.working td{background:rgba(255,255,255,.035)}
    tr.working td:first-child{position:relative}
    tr.working td:first-child:before{
      content:"";position:absolute;left:0;top:0;bottom:0;width:3px;border-radius:3px;
      background:rgba(255,255,255,.20);
    }
    tr.blink-ok td{animation: rowOk .9s ease}
    tr.blink-bad td{animation: rowBad .9s ease}
    @keyframes rowOk{0%{background:rgba(53,211,159,.16)}100%{background:transparent}}
    @keyframes rowBad{0%{background:rgba(255,59,92,.14)}100%{background:transparent}}

    .footer{
      margin-top:14px;color:var(--muted);font-size:12px;
      display:flex;align-items:center;justify-content:space-between;gap:10px;
      padding-top:10px;border-top:1px solid var(--line);
    }
    .footer a{color:rgba(255,255,255,.82);text-decoration:none;border-bottom:1px solid rgba(255,255,255,.18)}
    .footer a:hover{border-bottom-color:rgba(255,255,255,.34)}

    .grid3{display:grid;grid-template-columns: 1.2fr 1fr .7fr;gap:12px}
    .field label{display:block;font-size:12px;color:rgba(255,255,255,.55);margin:0 0 6px 2px}
    .field input{width:100%}

    .modal-foot-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:12px}

    .summary-wrap{display:grid;grid-template-columns: repeat(5, 1fr);gap:12px}
    .metric{border:1px solid rgba(255,255,255,.10);background:rgba(255,255,255,.03);border-radius:16px;padding:12px}
    .metric b{font-size:12px;color:rgba(255,255,255,.65);display:block;margin-bottom:6px}
    .metric .v{font-size:18px;font-weight:900;letter-spacing:.2px}
    .bar{height:10px;border-radius:999px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.08);overflow:hidden;margin-top:10px}
    .bar > div{height:100%;width:0%;background:rgba(255,255,255,.28);transition: width .25s ease}
    .summary-sub{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:10px;color:rgba(255,255,255,.60);font-size:12px;font-family:var(--mono)}

    .run-live{
      display:inline-flex;align-items:center;gap:10px;
      padding:8px 10px;border-radius:14px;
      border:1px solid rgba(255,255,255,.10);
      background:rgba(255,255,255,.03);
      font-family:var(--mono);
      font-size:12px;
      color:rgba(255,255,255,.78);
    }
    .run-live .pulse{
      width:10px;height:10px;border-radius:999px;background:rgba(255,255,255,.30);
      animation: pulse2 1.2s infinite;
    }
    @keyframes pulse2{
      0%{box-shadow:0 0 0 0 rgba(255,255,255,.18)}
      70%{box-shadow:0 0 0 12px rgba(255,255,255,0)}
      100%{box-shadow:0 0 0 0 rgba(255,255,255,0)}
    }

    /* Small confirm modal */
    .danger-box{
      border:1px solid rgba(255,59,92,.22);
      background:rgba(255,59,92,.08);
      border-radius:16px;
      padding:12px;
      color:rgba(255,255,255,.86);
    }

    @media (max-width: 940px){
      .footer{flex-direction:column;align-items:flex-start}
      .modal-head{flex-direction:column;align-items:stretch;gap:10px}
      .modal-actions{justify-content:flex-start;flex-wrap:wrap}
      .grid3{grid-template-columns:1fr}
      .summary-wrap{grid-template-columns:1fr 1fr}
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
        <input id="logFilter" placeholder="filter (e.g. anl-0161)" style="height:34px; padding:0 12px; border-radius:12px; min-width:220px;">

        <button class="btn btn-ghost btn-mini" id="btnReloadLogs" type="button">
          {{ icons.refresh|safe }} Reload
        </button>

        <!-- Guaranteed inline icon (fix #1) -->
        <button class="btn btn-ghost btn-mini" id="btnCopyLogs" type="button">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
               xmlns="http://www.w3.org/2000/svg" style="opacity:.98">
            <path d="M9 9h11v11H9z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
            <path d="M4 4h11v11H4z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          </svg>
          Copy
        </button>

        <button class="btn btn-ghost btn-mini" id="btnCloseLogs" type="button">
          {{ icons.close|safe }} Close
        </button>
      </div>
    </div>

    <div class="modal-body">
      <div class="logbox" id="logBox">Loading logs…</div>
      <div class="hint" id="logMeta">-</div>
    </div>

    <div class="footer" style="border-top:1px solid var(--line); padding:10px 14px; margin:0;">
      <div class="hint">interheart <code>{{ ui_version }}</code></div>
      <div><a href="https://5echo.io" target="_blank" rel="noreferrer">5echo.io</a> © {{ copyright_year }} All rights reserved</div>
    </div>
  </div>
</div>

<!-- Run summary modal -->
<div class="modal" id="runModal" aria-hidden="true">
  <div class="modal-card" role="dialog" aria-modal="true" aria-label="Run summary">
    <div class="modal-head">
      <div class="modal-title">
        <b>Run summary</b>
        <span id="runTitleMeta">-</span>
      </div>
      <div class="modal-actions">
        <div class="run-live" id="runLive" style="display:none;">
          <span class="pulse"></span>
          <span id="runLiveText">Running…</span>
        </div>
        <button class="btn btn-ghost btn-mini" id="btnCloseRun" type="button">
          {{ icons.close|safe }} Close
        </button>
      </div>
    </div>

    <div class="modal-body">
      <div class="summary-wrap">
        <div class="metric"><b>Total</b><div class="v" id="mTotal">-</div></div>
        <div class="metric"><b>Checked</b><div class="v" id="mDue">-</div></div>
        <div class="metric"><b>Skipped</b><div class="v" id="mSkipped">-</div></div>
        <div class="metric"><b>Ping OK</b><div class="v" id="mOk">-</div></div>
        <div class="metric"><b>Ping fail</b><div class="v" id="mFail">-</div></div>
      </div>

      <div class="metric">
        <b>Progress</b>
        <div class="bar"><div id="runBar"></div></div>
        <div class="summary-sub">
          <span id="runNowLine">Idle</span>
          <span id="runDoneLine">done: 0 / 0</span>
        </div>
      </div>

      <div class="metric">
        <b>Endpoint</b>
        <div class="summary-sub" style="margin-top:0;">
          <span>Responses</span><span id="mSent">-</span>
        </div>
        <div class="summary-sub" style="margin-top:4px;">
          <span>Endpoint failures</span><span id="mCurlFail">-</span>
        </div>
      </div>

      <div class="danger-box" id="runHintBox" style="display:none;">
        <b style="display:block; margin-bottom:6px;">Note</b>
        <div class="hint" id="runHintText" style="color:rgba(255,255,255,.80)"></div>
      </div>

      <div class="hint" id="runRaw" style="display:none;"></div>
    </div>

    <div class="footer" style="border-top:1px solid var(--line); padding:10px 14px; margin:0;">
      <div class="hint">interheart <code>{{ ui_version }}</code></div>
      <div><a href="https://5echo.io" target="_blank" rel="noreferrer">5echo.io</a> © {{ copyright_year }} All rights reserved</div>
    </div>
  </div>
</div>

<!-- Add modal -->
<div class="modal" id="addModal" aria-hidden="true">
  <div class="modal-card" role="dialog" aria-modal="true" aria-label="Add target">
    <div class="modal-head">
      <div class="modal-title">
        <b>Add target</b>
        <span>Ping target, then call endpoint on success</span>
      </div>
      <div class="modal-actions"></div>
    </div>

    <div class="modal-body">
      <form id="addForm">
        <div class="grid3">
          <div class="field">
            <label>Name</label>
            <input name="name" placeholder="e.g. anl-0161-core-gw" required>
          </div>

          <div class="field">
            <label>IP address</label>
            <input name="ip" placeholder="e.g. 10.5.0.1" required>
          </div>

          <div class="field">
            <label>Interval (sec)</label>
            <input name="interval" type="number" min="10" max="86400" step="1" placeholder="60" required>
          </div>
        </div>

        <div class="field" style="margin-top:12px;">
          <label>Endpoint URL</label>
          <input name="endpoint" placeholder="https://..." required>
        </div>

        <div class="modal-foot-actions">
          <button class="btn btn-primary" type="submit" id="btnAddSubmit" data-default-html="">
            {{ icons.plus|safe }} Add target
          </button>
          <button class="btn btn-ghost" type="button" id="btnAddCancel">Cancel</button>
        </div>

        <div class="hint" style="margin-top:10px;">
          Tip: critical targets 30–120s • less critical 300–900s
        </div>
      </form>
    </div>

    <div class="footer" style="border-top:1px solid var(--line); padding:10px 14px; margin:0;">
      <div class="hint">interheart <code>{{ ui_version }}</code></div>
      <div><a href="https://5echo.io" target="_blank" rel="noreferrer">5echo.io</a> © {{ copyright_year }} All rights reserved</div>
    </div>
  </div>
</div>

<!-- Confirm remove modal (fix #2) -->
<div class="modal" id="confirmModal" aria-hidden="true">
  <div class="modal-card small" role="dialog" aria-modal="true" aria-label="Confirm remove">
    <div class="modal-head">
      <div class="modal-title">
        <b>Confirm remove</b>
        <span>This cannot be undone</span>
      </div>
      <div class="modal-actions">
        <button class="btn btn-ghost btn-mini" id="btnCloseConfirm" type="button">
          {{ icons.close|safe }} Close
        </button>
      </div>
    </div>

    <div class="modal-body">
      <div class="danger-box">
        You are about to remove:
        <div style="margin-top:8px;">
          <code id="confirmName" style="font-family:var(--mono); font-size:13px;"></code>
        </div>
      </div>

      <div class="modal-foot-actions" style="margin-top:14px;">
        <button class="btn btn-danger" id="btnConfirmRemove" type="button">Remove</button>
        <button class="btn btn-ghost" id="btnCancelRemove" type="button">Cancel</button>
      </div>
    </div>

    <div class="footer" style="border-top:1px solid var(--line); padding:10px 14px; margin:0;">
      <div class="hint">interheart <code>{{ ui_version }}</code></div>
      <div><a href="https://5echo.io" target="_blank" rel="noreferrer">5echo.io</a> © {{ copyright_year }} All rights reserved</div>
    </div>
  </div>
</div>

<div class="wrap">
  <div class="top">
    <div class="brand">
      <div class="title">interheart <span class="badge">targets</span></div>
      <div class="subtitle">Powered by <a href="https://5echo.io" target="_blank" rel="noreferrer">5echo.io</a></div>
    </div>

    <div class="right-actions">
      <button class="btn btn-ghost btn-mini" id="openLogs" type="button">{{ icons.logs|safe }} Logs</button>
      <button class="btn btn-ghost btn-mini" id="openAdd" type="button">{{ icons.plus|safe }} Add</button>
      <button class="btn btn-primary btn-mini" id="btnRunNow" type="button" data-default-html="">
        {{ icons.play|safe }} Run now
      </button>
    </div>
  </div>

  <div class="card">
    <div class="hint">“Last ping” / “Last response” updates live ({{ poll_seconds }}s refresh)</div>
    <div class="sep"></div>

    <table>
      <thead>
        <tr>
          <th style="width: 210px;">Name</th>
          <th style="width: 130px;">IP</th>
          <th style="width: 140px;">Status</th>
          <th style="width: 150px;">Interval</th>
          <th style="width: 200px;">Last ping</th>
          <th style="width: 200px;">Last response</th>
          <th>Endpoint</th>
          <th style="width: 90px;">Actions</th>
        </tr>
      </thead>
      <tbody>
      {% for t in targets %}
        <tr data-name="{{ t.name }}" data-last-ping="{{ t.last_ping_epoch }}" data-last-resp="{{ t.last_response_epoch }}">
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

          <td><code class="last-ping">{{ t.last_ping_human }}</code></td>
          <td><code class="last-resp">{{ t.last_response_human }}</code></td>
          <td><code class="endpoint">{{ t.endpoint_masked }}</code></td>

          <td style="text-align:right;">
            <div class="menu">
              <button class="btn btn-ghost btn-mini menu-btn" type="button" aria-label="Actions">
                {{ icons.more|safe }}
              </button>
              <div class="menu-dd" role="menu">
                <button class="menu-item" data-action="test" type="button">{{ icons.test|safe }} Test</button>
                <button class="menu-item danger" data-action="remove" type="button">{{ icons.trash|safe }} Remove</button>
              </div>
            </div>
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>

    <div class="footer">
      <div class="hint">WebUI: <code>{{ bind_host }}:{{ bind_port }}</code> • interheart <code>{{ ui_version }}</code></div>
      <div><a href="https://5echo.io" target="_blank" rel="noreferrer">5echo.io</a> © {{ copyright_year }} All rights reserved</div>
    </div>
  </div>
</div>

<script>
(function(){
  const toasts = document.getElementById("toasts");
  function escapeHtml(s){
    return String(s ?? "")
      .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
      .replaceAll('"',"&quot;").replaceAll("'","&#039;");
  }
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
  function show(el){ el.classList.add("show"); el.setAttribute("aria-hidden","false"); }
  function hide(el){ el.classList.remove("show"); el.setAttribute("aria-hidden","true"); }

  function captureDefaultHtml(btn){
    if (!btn) return;
    if (!btn.dataset.defaultHtml || btn.dataset.defaultHtml === ""){
      btn.dataset.defaultHtml = btn.innerHTML;
    }
  }

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
  const addCancel = document.getElementById("btnAddCancel");
  const addForm = document.getElementById("addForm");
  const btnAddSubmit = document.getElementById("btnAddSubmit");
  captureDefaultHtml(btnAddSubmit);

  openAdd.addEventListener("click", () => show(addModal));
  addCancel.addEventListener("click", () => hide(addModal));
  addModal.addEventListener("click", (e) => { if (e.target === addModal) hide(addModal); });

  addForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    btnAddSubmit.disabled = true;
    btnAddSubmit.innerHTML = "Adding…";
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
      btnAddSubmit.disabled = false;
      btnAddSubmit.innerHTML = btnAddSubmit.dataset.defaultHtml || "Add target";
    }
  });

  // ---- Confirm remove modal (fix #2) ----
  const confirmModal = document.getElementById("confirmModal");
  const btnCloseConfirm = document.getElementById("btnCloseConfirm");
  const btnCancelRemove = document.getElementById("btnCancelRemove");
  const btnConfirmRemove = document.getElementById("btnConfirmRemove");
  const confirmName = document.getElementById("confirmName");
  let pendingRemoveName = null;

  function openConfirmRemove(name){
    pendingRemoveName = name;
    confirmName.textContent = name;
    show(confirmModal);
  }
  function closeConfirmRemove(){
    pendingRemoveName = null;
    hide(confirmModal);
  }
  btnCloseConfirm.addEventListener("click", closeConfirmRemove);
  btnCancelRemove.addEventListener("click", closeConfirmRemove);
  confirmModal.addEventListener("click", (e) => { if (e.target === confirmModal) closeConfirmRemove(); });

  async function removeTarget(name){
    const fd = new FormData();
    fd.set("name", name);
    const res = await fetch("/api/remove", {method:"POST", body: fd});
    return await res.json();
  }

  btnConfirmRemove.addEventListener("click", async () => {
    const name = pendingRemoveName;
    if (!name) return;
    btnConfirmRemove.disabled = true;
    btnConfirmRemove.textContent = "Removing…";
    try{
      const data = await removeTarget(name);
      toast(data.ok ? "Removed" : "Error", data.message || (data.ok ? "Done" : "Failed"));
      closeConfirmRemove();
    }catch(e){
      toast("Error", e && e.message ? e.message : "Failed");
    }finally{
      btnConfirmRemove.disabled = false;
      btnConfirmRemove.textContent = "Remove";
      await refreshState(true);
    }
  });

  // ---- Actions dropdown ----
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

  // ---- Run summary modal ----
  const runModal = document.getElementById("runModal");
  const btnCloseRun = document.getElementById("btnCloseRun");
  const runTitleMeta = document.getElementById("runTitleMeta");
  const runLive = document.getElementById("runLive");
  const runLiveText = document.getElementById("runLiveText");

  const mTotal = document.getElementById("mTotal");
  const mDue = document.getElementById("mDue");
  const mSkipped = document.getElementById("mSkipped");
  const mOk = document.getElementById("mOk");
  const mFail = document.getElementById("mFail");
  const mSent = document.getElementById("mSent");
  const mCurlFail = document.getElementById("mCurlFail");
  const runBar = document.getElementById("runBar");
  const runNowLine = document.getElementById("runNowLine");
  const runDoneLine = document.getElementById("runDoneLine");
  const runRaw = document.getElementById("runRaw");
  const runHintBox = document.getElementById("runHintBox");
  const runHintText = document.getElementById("runHintText");

  btnCloseRun.addEventListener("click", () => hide(runModal));
  runModal.addEventListener("click", (e) => { if (e.target === runModal) hide(runModal); });

  function setBar(done, due){
    const pct = (!due || due <= 0) ? 0 : Math.max(0, Math.min(100, Math.round((done / due) * 100)));
    runBar.style.width = pct + "%";
  }

  // runtime poll
  let runtimePoll = null;
  let lastRuntimeUpdated = 0;

  async function fetchRuntime(){
    try{
      const res = await fetch("/runtime", {cache:"no-store"});
      return await res.json();
    }catch(e){
      return null;
    }
  }

  function highlightWorking(name){
    document.querySelectorAll("tr[data-name]").forEach(r => {
      if (r.getAttribute("data-name") === name) r.classList.add("working");
      else r.classList.remove("working");
    });
  }
  function clearWorking(){
    document.querySelectorAll("tr[data-name]").forEach(r => r.classList.remove("working"));
  }

  function startRuntimePoll(){
    stopRuntimePoll();
    lastRuntimeUpdated = 0;
    runtimePoll = setInterval(async () => {
      const rt = await fetchRuntime();
      if (!rt) return;

      const upd = Number(rt.updated || 0);
      if (upd && upd === lastRuntimeUpdated) return;
      if (upd) lastRuntimeUpdated = upd;

      if (rt.status === "running"){
        runLive.style.display = "inline-flex";
        runLiveText.textContent = "Running…";
        const cur = (rt.current || "").trim();
        if (cur){
          highlightWorking(cur);
          runNowLine.textContent = "Now checking: " + cur;
        }else{
          runNowLine.textContent = "Running…";
        }

        const done = Number(rt.done || 0);
        const due = Number(rt.due || 0);
        runDoneLine.textContent = `done: ${done} / ${due}`;
        setBar(done, due);
      }else{
        runLive.style.display = "none";
      }
    }, 250);
  }
  function stopRuntimePoll(){
    if (runtimePoll){
      clearInterval(runtimePoll);
      runtimePoll = null;
    }
  }

  function setRunModalInitial(){
    runTitleMeta.textContent = "running…";
    runLive.style.display = "inline-flex";
    runLiveText.textContent = "Running…";
    mTotal.textContent = "-";
    mDue.textContent = "-";
    mSkipped.textContent = "-";
    mOk.textContent = "-";
    mFail.textContent = "-";
    mSent.textContent = "-";
    mCurlFail.textContent = "-";
    runNowLine.textContent = "Starting…";
    runDoneLine.textContent = "done: 0 / 0";
    runRaw.style.display = "none";
    runHintBox.style.display = "none";
    setBar(0, 0);
  }

  // ---- Run Now ----
  const btnRunNow = document.getElementById("btnRunNow");
  captureDefaultHtml(btnRunNow);

  btnRunNow.addEventListener("click", async () => {
    btnRunNow.disabled = true;

    // show modal immediately
    setRunModalInitial();
    show(runModal);
    startRuntimePoll();

    try{
      // IMPORTANT: force-run all targets (fix #3)
      const res = await fetch("/api/run-now", {method:"POST"});
      const data = await res.json();

      stopRuntimePoll();
      clearWorking();
      runLive.style.display = "none";

      const ts = new Date().toLocaleString();
      runTitleMeta.textContent = ts;

      const summary = data.summary || null;

      if (summary){
        mTotal.textContent = String(summary.total ?? "-");
        mDue.textContent = String(summary.due ?? "-");
        mSkipped.textContent = String(summary.skipped ?? "-");
        mOk.textContent = String(summary.ping_ok ?? "-");
        mFail.textContent = String(summary.ping_fail ?? "-");
        mSent.textContent = String(summary.sent ?? "-");
        mCurlFail.textContent = String(summary.curl_fail ?? "-");

        // progress should reflect "checked" count (due)
        const due = Number(summary.due || 0);
        setBar(due, due);
        runNowLine.textContent = data.ok ? "Completed" : "Failed";
        runDoneLine.textContent = `done: ${due} / ${due}`;

        // helpful hint when nothing happened
        if (due === 0 && Number(summary.total || 0) > 0){
          runHintBox.style.display = "block";
          runHintText.textContent = "No targets were checked. If this happens, verify interheart permissions and runtime directory access.";
        }
      }else{
        runRaw.textContent = data.message || "-";
        runRaw.style.display = "block";
        runNowLine.textContent = data.ok ? "Completed" : "Failed";
      }

      toast(data.ok ? "Run completed" : "Run failed", data.ok ? "Done" : (data.message || "Error"));
    }catch(e){
      stopRuntimePoll();
      clearWorking();
      runLive.style.display = "none";
      toast("Run failed", e && e.message ? e.message : "Error");
      runRaw.textContent = e && e.message ? e.message : "Run failed";
      runRaw.style.display = "block";
      runNowLine.textContent = "Failed";
    }finally{
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
            openConfirmRemove(name);
            return;
          }

          try{
            let data;
            if (action === "test"){
              toast("Testing", `Running test for ${name}…`);
              data = await apiPost("/api/test", fd);
            } else {
              return;
            }
            toast(data.ok ? "OK" : "Error", data.message || (data.ok ? "Done" : "Failed"));
          }catch(e){
            toast("Error", e && e.message ? e.message : "Failed");
          }finally{
            await refreshState(true);
          }
        });
      });
    });
  }

  // ---- Real-time refresh + row blink ----
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
    if (!el) return false;
    if (el.textContent !== newText){
      el.textContent = newText;
      el.classList.remove("flash");
      void el.offsetWidth;
      el.classList.add("flash");
      return true;
    }
    return false;
  }

  function blinkRow(row, ok){
    if (!row) return;
    row.classList.remove("blink-ok","blink-bad");
    void row.offsetWidth;
    row.classList.add(ok ? "blink-ok" : "blink-bad");
    setTimeout(() => row.classList.remove("blink-ok","blink-bad"), 1000);
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

        const prevPing = parseInt(row.getAttribute("data-last-ping") || "0", 10);
        const newPing = parseInt(String(t.last_ping_epoch || 0), 10);

        if (newPing && newPing !== prevPing){
          row.setAttribute("data-last-ping", String(newPing));
          blinkRow(row, t.status === "up");
        }

        flashIfChanged(row.querySelector(".last-ping"), t.last_ping_human || "-");
        flashIfChanged(row.querySelector(".last-resp"), t.last_response_human || "-");

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
      // silent
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
      if (runModal.classList.contains("show")) hide(runModal);
      if (confirmModal.classList.contains("show")) hide(confirmModal);
      closeAllMenus();
    }
  });

})();
</script>
</body>
</html>
"""

def icon_svg(path_d: str, opacity: float = 0.95):
    return Markup(
        f"""<svg width="16" height="16" viewBox="0 0 24 24" fill="none"
        xmlns="http://www.w3.org/2000/svg" style="opacity:{opacity}">
        <path d="{path_d}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>"""
    )

ICONS = {
    "plus": icon_svg("M12 5v14M5 12h14"),
    "logs": icon_svg("M4 6h16M4 12h16M4 18h10"),
    "close": icon_svg("M18 6L6 18M6 6l12 12"),
    "refresh": icon_svg("M21 12a9 9 0 1 1-2.64-6.36M21 3v6h-6"),
    "play": icon_svg("M8 5v14l11-7z"),
    "more": icon_svg("M12 5h.01M12 12h.01M12 19h.01"),
    "test": icon_svg("M4 20h16M6 16l6-12 6 12"),
    "trash": icon_svg("M3 6h18M8 6V4h8v2M9 6v14m6-14v14M6 6l1 16h10l1-16"),
}

@APP.get("/")
def index():
    return render_template_string(
        TEMPLATE,
        targets=merged_targets(),
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
    return jsonify({"updated": int(time.time()), "targets": merged_targets()})

@APP.get("/runtime")
def runtime():
    try:
        if os.path.exists(RUNTIME_FILE):
            with open(RUNTIME_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("status", "idle")
            data.setdefault("current", "")
            data.setdefault("done", 0)
            data.setdefault("due", 0)
            data.setdefault("updated", int(time.time()))
            return jsonify(data)
    except Exception:
        pass
    return jsonify({"status": "idle", "current": "", "done": 0, "due": 0, "updated": int(time.time())})

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
        return jsonify({"source": "journalctl (error)", "lines": 1, "updated": updated, "text": f"(journalctl error: {str(e)})"})

@APP.post("/api/run-now")
def api_run_now():
    # IMPORTANT: run-now forces checking all targets
    rc, out = run_cmd(["run-now"])
    summary = parse_run_summary(out)
    return jsonify({
        "ok": rc == 0,
        "message": out or ("OK" if rc == 0 else "Failed"),
        "summary": summary
    })

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
