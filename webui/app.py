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
RUN_META_FILE = os.path.join(STATE_DIR, "run_meta.json")
RUN_OUT_FILE = os.path.join(STATE_DIR, "run_last_output.txt")

def ensure_state_dir():
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        try:
            os.chmod(STATE_DIR, 0o777)
        except Exception:
            pass

        for p in [RUNTIME_FILE, RUN_META_FILE, RUN_OUT_FILE]:
            if not os.path.exists(p):
                with open(p, "w", encoding="utf-8") as f:
                    f.write("")
            try:
                os.chmod(p, 0o666)
            except Exception:
                pass
    except Exception:
        pass

ensure_state_dir()

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
        # NAME IP INTERVAL ENABLED ENDPOINT(masked)
        if len(parts) < 5:
            continue
        name = parts[0]
        ip = parts[1]
        interval = parts[2].replace("s", "").strip()
        enabled = parts[3].strip()
        endpoint_masked = parts[4]
        targets.append({
            "name": name,
            "ip": ip,
            "interval": int(interval) if interval.isdigit() else 60,
            "enabled": True if enabled == "1" else False,
            "endpoint_masked": endpoint_masked
        })
    return targets

def parse_status(status_output: str):
    """
    interheart status table:
      NAME STATUS NEXT_IN NEXT_DUE LAST_PING LAST_RESP LAT_MS
    """
    state = {}
    in_table = False
    for line in status_output.splitlines():
        if line.startswith("----------------------------------------------------------------------------------------------------------------------------") or \
           line.startswith("-------------------------------------------------------------------------------------------------------------------------------"):
            in_table = True
            continue
        if not in_table:
            continue
        if line.strip().startswith("NAME") or line.strip().startswith("State:"):
            continue
        if not line.strip():
            continue

        parts = line.split()
        # NAME STATUS NEXT_IN NEXT_DUE LAST_PING LAST_RESP LAT_MS
        if len(parts) < 7:
            continue
        name = parts[0]
        status = parts[1]
        next_due = parts[3]
        last_ping = parts[4]
        last_sent = parts[5]
        last_rtt = parts[6]
        state[name] = {
            "status": status,
            "next_due_epoch": int(next_due) if next_due.isdigit() else 0,
            "last_ping_epoch": int(last_ping) if last_ping.isdigit() else 0,
            "last_sent_epoch": int(last_sent) if last_sent.isdigit() else 0,
            "last_rtt_ms": int(last_rtt) if last_rtt.lstrip("-").isdigit() else -1,
        }
    return state

def human_ts(epoch: int):
    if not epoch or epoch <= 0:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))
    except Exception:
        return "-"

def human_due(epoch: int):
    if not epoch or epoch <= 0:
        return "-"
    now = int(time.time())
    if epoch <= now:
        return f"due ({human_ts(epoch)})"
    diff = epoch - now
    if diff < 60:
        return f"in {diff}s ({human_ts(epoch)})"
    if diff < 3600:
        return f"in {diff//60}m ({human_ts(epoch)})"
    return f"in {diff//3600}h {((diff%3600)//60)}m ({human_ts(epoch)})"

def sudo_journalctl(lines: int) -> str:
    cmd = ["sudo", "journalctl", "-t", "interheart", "-n", str(lines), "--no-pager", "--output=cat"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "journalctl failed").strip())
    return (p.stdout or "").strip()

def load_run_meta():
    try:
        if os.path.exists(RUN_META_FILE):
            with open(RUN_META_FILE, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if not raw:
                return {}
            return json.loads(raw)
    except Exception:
        return {}
    return {}

def save_run_meta(meta: dict):
    ensure_state_dir()
    try:
        with open(RUN_META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        try:
            os.chmod(RUN_META_FILE, 0o666)
        except Exception:
            pass
    except Exception:
        pass

def pid_is_running(pid: int):
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False

SUMMARY_RE = re.compile(
    r"total=(\d+)\s+due=(\d+)\s+skipped=(\d+)\s+ping_ok=(\d+)\s+ping_fail=(\d+)\s+sent=(\d+)\s+curl_fail=(\d+)(?:\s+disabled=(\d+))?(?:\s+force=(\d+))?(?:\s+duration_ms=(\d+))?"
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
        "disabled": int(m.group(8) or 0),
        "force": int(m.group(9) or 0),
        "duration_ms": int(m.group(10) or 0),
    }

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
    "copy": icon_svg("M9 9h11v11H9zM4 4h11v11H4z"),
    "search": icon_svg("M21 21l-4.35-4.35M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15"),
    "ban": icon_svg("M18 6L6 18M6 6l12 12"),
    "check": icon_svg("M20 6 9 17l-5-5"),
    "info": icon_svg("M12 16v-4M12 8h.01"),
    "edit": icon_svg("M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5"),
}

def merged_targets():
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
        last_rtt_ms = st.get("last_rtt_ms", -1)

        if not t.get("enabled", True):
            status = "disabled"

        merged.append({
            **t,
            "status": status,
            "next_due_epoch": next_due_epoch,
            "next_due_human": human_due(next_due_epoch),
            "last_ping_human": human_ts(last_ping_epoch),
            "last_response_human": human_ts(last_sent_epoch),
            "last_ping_epoch": last_ping_epoch,
            "last_response_epoch": last_sent_epoch,
            "last_rtt_ms": last_rtt_ms,
        })
    return merged

def stats_from_targets(ts):
    up = sum(1 for t in ts if t.get("status") == "up")
    down = sum(1 for t in ts if t.get("status") == "down")
    unknown = sum(1 for t in ts if t.get("status") in ("unknown",))
    disabled = sum(1 for t in ts if t.get("status") == "disabled")
    return {"up": up, "down": down, "unknown": unknown, "disabled": disabled, "total": len(ts)}

def format_duration_ms(ms: int):
    if not ms or ms <= 0:
        return "-"
    if ms < 1000:
        return f"{ms} ms"
    sec = ms / 1000.0
    if sec < 60:
        return f"{sec:.1f}s"
    m = int(sec // 60)
    s = sec - (m * 60)
    return f"{m}m {s:.0f}s"

def get_last_run_summary():
    try:
        if os.path.exists(RUN_OUT_FILE):
            with open(RUN_OUT_FILE, "r", encoding="utf-8") as f:
                out = f.read().strip()
            s = parse_run_summary(out or "")
            return s
    except Exception:
        return None
    return None

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
      --info:#73b7ff;

      --shadow: 0 18px 54px rgba(0,0,0,.60);
      --radius: 18px;

      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    }

    *{box-sizing:border-box}
    body{ margin:0; font-family:var(--sans); color:var(--text); background: var(--bg); }

    .wrap{max-width:1280px;margin:34px auto;padding:0 18px}
    .top{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:14px}
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

    input, select{
      border-radius:14px;
      border:1px solid var(--line);
      background:rgba(255,255,255,.03);
      color:var(--text);
      padding:10px 12px;
      outline:none;
      transition: border-color .15s ease, filter .15s ease, background .15s ease;
      font-family:var(--sans);
      height:36px;
    }
    input:focus, select:focus{ border-color:rgba(255,255,255,.24); filter:brightness(1.03); background:rgba(255,255,255,.04); }
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
      white-space:nowrap;
    }
    .btn:hover{ transform: translateY(-1px); border-color: rgba(255,255,255,.20); background:rgba(255,255,255,.04); filter:brightness(1.03); }
    .btn:active{transform: translateY(0px)}
    .btn-mini{font-size:12px;padding:0 12px;border-radius:12px;height:34px}
    .btn-ghost{background:transparent;border-color:rgba(255,255,255,.12)}
    .btn-ghost:hover{border-color:rgba(255,255,255,.22)}
    .btn-primary{border-color:rgba(255,255,255,.22);background:rgba(255,255,255,.06)}
    .btn-danger{ border-color:rgba(255,59,92,.28); background:rgba(255,59,92,.10); }
    .btn-danger:hover{ border-color:rgba(255,59,92,.40); background:rgba(255,59,92,.14); }
    .btn-disabled{ opacity:.6; pointer-events:none; }

    .right-actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}

    table{width:100%;border-collapse:collapse;border-radius:14px;overflow:hidden}
    th,td{padding:10px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:middle}
    th{color:var(--muted);font-weight:850;text-align:left;user-select:none}
    td code{font-family:var(--mono);font-size:12px;color:rgba(255,255,255,.88)}
    tr:hover td{background:rgba(255,255,255,.020)}

    th.sortable{cursor:pointer}
    th.sortable:hover{color:rgba(255,255,255,.78)}
    .sort-ind{opacity:.65;font-size:11px;margin-left:8px}
    .sort-ind.on{opacity:.95}

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
    .status-disabled{border-color:rgba(115,183,255,.22);background:rgba(115,183,255,.06)}
    .status-disabled .dot{background:var(--info)}
    @keyframes pulse{
      0%{box-shadow:0 0 0 0 rgba(53,211,159,.28)}
      70%{box-shadow:0 0 0 10px rgba(53,211,159,0)}
      100%{box-shadow:0 0 0 0 rgba(53,211,159,0)}
    }

    .interval-wrap{display:flex;align-items:center;gap:8px}
    .interval-input{
      width:72px;height:34px;padding:8px 10px;border-radius:12px;font-weight:850;
      font-family:var(--mono);
      background:rgba(255,255,255,.03);
    }
    .interval-suffix{color:rgba(255,255,255,.45);font-size:12px;font-weight:850}

    .menu{position:relative;display:inline-block}
    .menu-btn{width:40px;height:34px;display:inline-flex;align-items:center;justify-content:center;border-radius:12px}
    .menu-dd{
      position:absolute;right:0;top:42px;width:240px;
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
      z-index:9999;width:min(520px, calc(100vw - 24px));pointer-events:none;
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
    .toast-actions{display:flex;gap:8px;margin-left:auto;align-items:center}
    .toast-actions .btn-mini{height:30px}

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
    .modal-card.small{ width:min(560px, calc(100vw - 40px)); max-height:none; }
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
    .field input, .field select{width:100%}
    .modal-foot-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:12px}

    .danger-box{
      border:1px solid rgba(255,59,92,.22);
      background:rgba(255,59,92,.08);
      border-radius:16px;
      padding:12px;
      color:rgba(255,255,255,.86);
    }

    /* mini cards + filter row */
    .stats-row{
      display:grid;
      grid-template-columns: repeat(4, 1fr);
      gap:12px;
      margin: 8px 0 14px 0;
    }
    .stat{
      border:1px solid rgba(255,255,255,.10);
      background:rgba(255,255,255,.03);
      border-radius:18px;
      padding:12px;
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap:12px;
      overflow:hidden;
      position:relative;
    }
    .stat.clickable{cursor:pointer}
    .stat.clickable:hover{border-color:rgba(255,255,255,.16); background:rgba(255,255,255,.04)}
    .stat .k{font-size:12px;color:rgba(255,255,255,.62);font-weight:850}
    .stat .v{font-size:22px;font-weight:950;letter-spacing:.2px}
    .pill{
      display:inline-flex;align-items:center;gap:8px;
      border-radius:999px;padding:6px 10px;
      background:rgba(255,255,255,.04);
      border:1px solid rgba(255,255,255,.10);
      color:rgba(255,255,255,.75);
      font-size:12px;
      font-family:var(--mono);
      white-space:nowrap;
    }
    .pill.good{border-color:rgba(53,211,159,.22); background:rgba(53,211,159,.08)}
    .pill.bad{border-color:rgba(255,59,92,.24); background:rgba(255,59,92,.08)}
    .pill.warn{border-color:rgba(255,211,77,.20); background:rgba(255,211,77,.06)}
    .pill.info{border-color:rgba(115,183,255,.22); background:rgba(115,183,255,.06)}

    .filters{
      display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;
      margin: 6px 0 10px 0;
    }
    .filters-left{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
    .filters-right{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
    .chipbtn{
      border-radius:999px;
      border:1px solid rgba(255,255,255,.12);
      background:rgba(255,255,255,.03);
      color:rgba(255,255,255,.78);
      padding:8px 10px;
      cursor:pointer;
      font-weight:900;
      display:inline-flex;align-items:center;gap:8px;
      height:36px;
    }
    .chipbtn.active{border-color:rgba(255,255,255,.22); background:rgba(255,255,255,.06)}

    /* prettier checkbox */
    .selbox{
      width:18px;height:18px;
      appearance:none;-webkit-appearance:none;
      border-radius:6px;
      border:1px solid rgba(255,255,255,.18);
      background:rgba(255,255,255,.04);
      display:inline-grid;
      place-content:center;
      cursor:pointer;
      transition: transform .12s ease, background .12s ease, border-color .12s ease, filter .12s ease;
    }
    .selbox:hover{
      border-color: rgba(255,255,255,.26);
      background: rgba(255,255,255,.06);
      transform: translateY(-1px);
    }
    .selbox:checked{
      border-color: rgba(115,183,255,.35);
      background: rgba(115,183,255,.14);
    }
    .selbox:checked::after{
      content:"";
      width:9px;height:5px;
      border-left:2px solid rgba(255,255,255,.92);
      border-bottom:2px solid rgba(255,255,255,.92);
      transform: rotate(-45deg);
      margin-top:-1px;
    }

    /* Popover */
    .pop{
      position:absolute;
      right:12px;
      top:56px;
      width:min(520px, calc(100vw - 40px));
      background:rgba(10,16,28,.96);
      border:1px solid rgba(255,255,255,.12);
      border-radius:16px;
      box-shadow: 0 22px 60px rgba(0,0,0,.70);
      padding:12px;
      z-index:70;
      display:none;
      animation: pop .14s ease;
    }
    .pop.show{display:block}
    .pop h4{margin:0 0 8px 0;font-size:13px}
    .pop .grid{
      display:grid;
      grid-template-columns: repeat(3, 1fr);
      gap:10px;
      margin-top:10px;
    }
    .pop .m{
      border:1px solid rgba(255,255,255,.10);
      background:rgba(255,255,255,.03);
      border-radius:14px;
      padding:10px;
    }
    .pop .m b{display:block;font-size:12px;color:rgba(255,255,255,.64);margin-bottom:6px}
    .pop .m .v{font-size:16px;font-weight:950;font-family:var(--mono)}
    .pop .row{display:flex;align-items:center;justify-content:space-between;gap:10px}
    .pop .row .xbtn{border:0;background:transparent;color:rgba(255,255,255,.72);cursor:pointer;font-weight:950}
    .pop .hint{margin-top:8px}

    /* info rows */
    .info-grid{
      display:grid;
      grid-template-columns: 1fr 1fr;
      gap:12px;
    }
    .info-item{
      border:1px solid rgba(255,255,255,.10);
      background:rgba(255,255,255,.03);
      border-radius:16px;
      padding:12px;
      overflow:hidden;
    }
    .info-item b{display:block;font-size:12px;color:rgba(255,255,255,.62);margin-bottom:6px}
    .info-item code{font-family:var(--mono);font-size:12px;color:rgba(255,255,255,.88);word-break:break-all}
    .copy-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
    .copy-row .btn-mini{height:32px}

    @media (max-width: 940px){
      .footer{flex-direction:column;align-items:flex-start}
      .modal-head{flex-direction:column;align-items:stretch;gap:10px}
      .modal-actions{justify-content:flex-start;flex-wrap:wrap}
      .grid3{grid-template-columns:1fr}
      .stats-row{grid-template-columns: 1fr 1fr}
      .info-grid{grid-template-columns:1fr}
      .pop .grid{grid-template-columns: 1fr 1fr}
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
        <button class="btn btn-ghost btn-mini" id="btnReloadLogs" type="button">{{ icons.refresh|safe }} Reload</button>
        <button class="btn btn-ghost btn-mini" id="btnCopyLogs" type="button">{{ icons.copy|safe }} Copy</button>
        <button class="btn btn-ghost btn-mini" id="btnCloseLogs" type="button">{{ icons.close|safe }} Close</button>
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
          <button class="btn btn-ghost" type="button" id="btnAddCancel">Cancel</button>
          <button class="btn btn-primary" type="submit" id="btnAddSubmit" data-default-html="">
            {{ icons.plus|safe }} Add target
          </button>
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

<!-- Confirm remove modal -->
<div class="modal" id="confirmModal" aria-hidden="true">
  <div class="modal-card small" role="dialog" aria-modal="true" aria-label="Confirm remove">
    <div class="modal-head">
      <div class="modal-title">
        <b>Confirm remove</b>
        <span>This cannot be undone</span>
      </div>
      <div class="modal-actions"></div>
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

<!-- Target information modal -->
<div class="modal" id="infoModal" aria-hidden="true">
  <div class="modal-card" role="dialog" aria-modal="true" aria-label="Target information">
    <div class="modal-head">
      <div class="modal-title">
        <b>Target information</b>
        <span id="infoSubtitle">-</span>
      </div>
      <div class="modal-actions">
        <button class="btn btn-ghost btn-mini" id="btnCloseInfo" type="button">{{ icons.close|safe }} Close</button>
      </div>
    </div>

    <div class="modal-body">
      <div class="info-grid">
        <div class="info-item">
          <b>Name</b>
          <code id="infoName">-</code>
        </div>
        <div class="info-item">
          <b>IP</b>
          <code id="infoIP">-</code>
        </div>

        <div class="info-item">
          <b>Endpoint</b>
          <code id="infoEndpoint">-</code>
        </div>
        <div class="info-item">
          <b>Enabled</b>
          <code id="infoEnabled">-</code>
        </div>

        <div class="info-item">
          <b>Interval</b>
          <code id="infoInterval">-</code>
        </div>
        <div class="info-item">
          <b>Next due</b>
          <code id="infoNextDue">-</code>
        </div>

        <div class="info-item">
          <b>Last ping</b>
          <code id="infoLastPing">-</code>
        </div>
        <div class="info-item">
          <b>Last response</b>
          <code id="infoLastResp">-</code>
        </div>

        <div class="info-item">
          <b>Last latency</b>
          <code id="infoLatency">-</code>
        </div>
        <div class="info-item">
          <b>Status</b>
          <code id="infoStatus">-</code>
        </div>
      </div>

      <div class="copy-row">
        <button class="btn btn-ghost btn-mini" id="btnCopyName" type="button">{{ icons.copy|safe }} Copy name</button>
        <button class="btn btn-ghost btn-mini" id="btnCopyIP" type="button">{{ icons.copy|safe }} Copy IP</button>
        <button class="btn btn-ghost btn-mini" id="btnCopyEndpoint" type="button">{{ icons.copy|safe }} Copy endpoint</button>
      </div>

      <div class="modal-foot-actions">
        <button class="btn btn-ghost" id="btnInfoEdit" type="button">{{ icons.edit|safe }} Edit</button>
        <button class="btn btn-primary" id="btnInfoToggle" type="button">{{ icons.ban|safe }} Disable</button>
      </div>
    </div>

    <div class="footer" style="border-top:1px solid var(--line); padding:10px 14px; margin:0;">
      <div class="hint">interheart <code>{{ ui_version }}</code></div>
      <div><a href="https://5echo.io" target="_blank" rel="noreferrer">5echo.io</a> © {{ copyright_year }} All rights reserved</div>
    </div>
  </div>
</div>

<!-- Edit target modal -->
<div class="modal" id="editModal" aria-hidden="true">
  <div class="modal-card" role="dialog" aria-modal="true" aria-label="Edit target">
    <div class="modal-head">
      <div class="modal-title">
        <b>Edit target</b>
        <span id="editSubtitle">-</span>
      </div>
      <div class="modal-actions">
        <button class="btn btn-ghost btn-mini" id="btnCloseEdit" type="button">{{ icons.close|safe }} Close</button>
      </div>
    </div>

    <div class="modal-body">
      <form id="editForm">
        <input type="hidden" name="old_name" id="editOldName">

        <div class="grid3">
          <div class="field">
            <label>Name</label>
            <input name="name" id="editName" required>
          </div>

          <div class="field">
            <label>IP address</label>
            <input name="ip" id="editIP" required>
          </div>

          <div class="field">
            <label>Interval (sec)</label>
            <input name="interval" id="editInterval" type="number" min="10" max="86400" step="1" required>
          </div>
        </div>

        <div class="field" style="margin-top:12px;">
          <label>Endpoint URL</label>
          <input name="endpoint" id="editEndpoint" required>
        </div>

        <div class="field" style="margin-top:12px;">
          <label>Enabled</label>
          <select name="enabled" id="editEnabled">
            <option value="1">Enabled</option>
            <option value="0">Disabled</option>
          </select>
        </div>

        <div class="modal-foot-actions">
          <button class="btn btn-ghost" type="button" id="btnEditCancel">Cancel</button>
          <button class="btn btn-primary" type="submit" id="btnEditSave">{{ icons.check|safe }} Save changes</button>
        </div>

        <div class="hint" id="editHint" style="margin-top:10px;">Tip: URL must start with http:// or https://</div>
      </form>
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
      <button class="btn btn-primary btn-mini" id="btnRunNowAll" type="button">
        {{ icons.play|safe }} Run now
      </button>
    </div>
  </div>

  <!-- Mini cards -->
  <div class="stats-row">
    <div class="stat">
      <div>
        <div class="k">Up</div>
        <div class="v" id="statUp">{{ stats.up }}</div>
      </div>
      <div class="pill good"><span class="dot" style="background:var(--good)"></span> live</div>
    </div>
    <div class="stat">
      <div>
        <div class="k">Down</div>
        <div class="v" id="statDown">{{ stats.down }}</div>
      </div>
      <div class="pill bad"><span class="dot" style="background:var(--danger)"></span> live</div>
    </div>
    <div class="stat">
      <div>
        <div class="k">Unknown</div>
        <div class="v" id="statUnknown">{{ stats.unknown }}</div>
      </div>
      <div class="pill warn"><span class="dot" style="background:var(--warn)"></span> live</div>
    </div>

    <div class="stat clickable" id="statDurCard">
      <div>
        <div class="k">Last run duration</div>
        <div class="v" id="statDur">{{ last_run_duration }}</div>
      </div>
      <div class="pill info"><span class="dot" style="background:var(--info)"></span> summary</div>

      <div class="pop" id="runSummaryPop">
        <div class="row">
          <h4 style="margin:0;">Last run summary</h4>
          <button class="xbtn" id="btnCloseSummary" type="button">×</button>
        </div>
        <div class="hint" id="runSummaryMeta">Parsed from last output</div>

        <div class="grid" id="runSummaryGrid">
          <div class="m"><b>Total</b><div class="v" id="rsTotal">-</div></div>
          <div class="m"><b>Due</b><div class="v" id="rsDue">-</div></div>
          <div class="m"><b>Skipped</b><div class="v" id="rsSkipped">-</div></div>
          <div class="m"><b>Ping OK</b><div class="v" id="rsPingOk">-</div></div>
          <div class="m"><b>Ping FAIL</b><div class="v" id="rsPingFail">-</div></div>
          <div class="m"><b>Sent</b><div class="v" id="rsSent">-</div></div>
          <div class="m"><b>Curl FAIL</b><div class="v" id="rsCurlFail">-</div></div>
          <div class="m"><b>Disabled</b><div class="v" id="rsDisabled">-</div></div>
          <div class="m"><b>Force</b><div class="v" id="rsForce">-</div></div>
        </div>

        <div class="hint" style="margin-top:10px;" id="rsDuration">Duration: -</div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="filters">
      <div class="filters-left">
        <div style="position:relative;">
          <div style="position:absolute;left:12px;top:9px;opacity:.85">{{ icons.search|safe }}</div>
          <input id="searchBox" placeholder="Search (name / IP / status)" style="padding-left:38px; min-width:320px;">
        </div>

        <button class="chipbtn active" data-filter="all" type="button">All</button>
        <button class="chipbtn" data-filter="up" type="button">Up</button>
        <button class="chipbtn" data-filter="down" type="button">Down</button>
        <button class="chipbtn" data-filter="unknown" type="button">Unknown</button>
        <button class="chipbtn" data-filter="disabled" type="button">Disabled</button>
      </div>

      <div class="filters-right">
        <button class="btn btn-ghost btn-mini btn-disabled" id="btnRunSelected" type="button">
          {{ icons.play|safe }} Run selected
        </button>
        <button class="btn btn-ghost btn-mini btn-disabled" id="btnDisableSelected" type="button">
          {{ icons.ban|safe }} Disable selected
        </button>
        <button class="btn btn-ghost btn-mini btn-disabled" id="btnEnableSelected" type="button">
          {{ icons.check|safe }} Activate selected
        </button>
      </div>
    </div>

    <div class="hint">“Last ping” / “Last response” updates live ({{ poll_seconds }}s refresh)</div>
    <div class="sep"></div>

    <table>
      <thead>
        <tr>
          <th style="width: 42px;"><input type="checkbox" id="selAll" class="selbox"></th>

          <th class="sortable" data-sort="name" style="width: 230px;">Name <span class="sort-ind" data-ind="name">↕</span></th>
          <th class="sortable" data-sort="ip" style="width: 140px;">IP <span class="sort-ind" data-ind="ip">↕</span></th>
          <th class="sortable" data-sort="status" style="width: 150px;">Status <span class="sort-ind" data-ind="status">↕</span></th>
          <th class="sortable" data-sort="interval" style="width: 130px;">Interval <span class="sort-ind" data-ind="interval">↕</span></th>
          <th class="sortable" data-sort="last_ping" style="width: 220px;">Last ping <span class="sort-ind" data-ind="last_ping">↕</span></th>
          <th style="width: 220px;">Last response</th>
          <th style="width: 90px;">Actions</th>
        </tr>
      </thead>

      <tbody id="tbody">
      {% for t in targets %}
        <tr
          data-name="{{ t.name }}"
          data-ip="{{ t.ip }}"
          data-status="{{ t.status }}"
          data-enabled="{{ '1' if t.enabled else '0' }}"
          data-interval="{{ t.interval }}"
          data-next-due="{{ t.next_due_epoch }}"
          data-last-ping="{{ t.last_ping_epoch }}"
          data-last-resp="{{ t.last_response_epoch }}"
          data-lat="{{ t.last_rtt_ms }}"
        >
          <td><input type="checkbox" class="selbox selRow"></td>
          <td><code>{{ t.name }}</code></td>
          <td><code>{{ t.ip }}</code></td>
          <td>
            <span class="chip status-chip
              {% if t.status == 'up' %}status-up{% elif t.status == 'down' %}status-down{% elif t.status == 'disabled' %}status-disabled{% else %}status-unknown{% endif %}">
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

          <td style="text-align:right;">
            <div class="menu">
              <button class="btn btn-ghost btn-mini menu-btn" type="button" aria-label="Actions">
                {{ icons.more|safe }}
              </button>
              <div class="menu-dd" role="menu">
                <button class="menu-item" data-action="info" type="button">{{ icons.info|safe }} Information</button>
                <button class="menu-item" data-action="edit" type="button">{{ icons.edit|safe }} Edit</button>
                <button class="menu-item" data-action="toggle" type="button">{{ icons.ban|safe }} <span class="toggle-label">Disable</span></button>
                <div style="height:1px;background:rgba(255,255,255,.10);margin:6px 0;"></div>
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

  function toast(title, msg, opts={}){
    const el = document.createElement("div");
    el.className = "toast";

    const actionHtml = opts.actionText ? `
      <div class="toast-actions">
        <button class="btn btn-ghost btn-mini" data-act="1">${escapeHtml(opts.actionText)}</button>
      </div>
    ` : `<div style="margin-left:auto"></div>`;

    el.innerHTML = `
      <div style="min-width:0;">
        <b>${escapeHtml(title)}</b>
        <p>${escapeHtml(msg || "")}</p>
      </div>
      ${actionHtml}
      <button class="x" aria-label="Close">×</button>
    `;

    el.querySelector(".x").onclick = () => el.remove();

    if (opts.onAction){
      const btn = el.querySelector('[data-act="1"]');
      if (btn) btn.onclick = () => opts.onAction(el);
    }

    toasts.appendChild(el);

    const ttl = typeof opts.ttl === "number" ? opts.ttl : 5200;
    if (ttl > 0){
      setTimeout(() => { if (el && el.parentNode) el.remove(); }, ttl);
    }
    return el;
  }

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
  const addCancel = document.getElementById("btnAddCancel");
  const addForm = document.getElementById("addForm");
  const btnAddSubmit = document.getElementById("btnAddSubmit");
  btnAddSubmit.dataset.defaultHtml = btnAddSubmit.innerHTML;

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

  // ---- Confirm remove modal ----
  const confirmModal = document.getElementById("confirmModal");
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

  // ---- Info modal ----
  const infoModal = document.getElementById("infoModal");
  const btnCloseInfo = document.getElementById("btnCloseInfo");
  const btnInfoEdit = document.getElementById("btnInfoEdit");
  const btnInfoToggle = document.getElementById("btnInfoToggle");
  const infoSubtitle = document.getElementById("infoSubtitle");

  const infoName = document.getElementById("infoName");
  const infoIP = document.getElementById("infoIP");
  const infoEndpoint = document.getElementById("infoEndpoint");
  const infoEnabled = document.getElementById("infoEnabled");
  const infoInterval = document.getElementById("infoInterval");
  const infoNextDue = document.getElementById("infoNextDue");
  const infoLastPing = document.getElementById("infoLastPing");
  const infoLastResp = document.getElementById("infoLastResp");
  const infoLatency = document.getElementById("infoLatency");
  const infoStatus = document.getElementById("infoStatus");

  const btnCopyName = document.getElementById("btnCopyName");
  const btnCopyIP = document.getElementById("btnCopyIP");
  const btnCopyEndpoint = document.getElementById("btnCopyEndpoint");

  let currentInfoName = null;
  let currentInfoEndpoint = null;

  btnCloseInfo.addEventListener("click", () => hide(infoModal));
  infoModal.addEventListener("click", (e) => { if (e.target === infoModal) hide(infoModal); });

  async function copyText(label, text){
    try{
      await navigator.clipboard.writeText(text || "");
      toast("Copied", `${label} copied`);
    }catch(e){
      toast("Error", "Copy failed");
    }
  }

  btnCopyName.addEventListener("click", () => copyText("Name", currentInfoName || ""));
  btnCopyIP.addEventListener("click", () => copyText("IP", (infoIP.textContent || "").trim()));
  btnCopyEndpoint.addEventListener("click", () => copyText("Endpoint", currentInfoEndpoint || ""));

  async function fetchTargetInfo(name){
    const res = await fetch("/api/target-info?name=" + encodeURIComponent(name), {cache:"no-store"});
    return await res.json();
  }

  function setInfoFromRow(row){
    const name = row.getAttribute("data-name") || "-";
    const ip = row.getAttribute("data-ip") || "-";
    const enabled = row.getAttribute("data-enabled") === "1";
    const interval = row.getAttribute("data-interval") || "-";
    const nextDue = parseInt(row.getAttribute("data-next-due") || "0", 10);
    const lastPingText = (row.querySelector(".last-ping")?.textContent || "-").trim();
    const lastRespText = (row.querySelector(".last-resp")?.textContent || "-").trim();
    const status = (row.getAttribute("data-status") || "unknown").trim();
    const lat = parseInt(row.getAttribute("data-lat") || "-1", 10);

    currentInfoName = name;
    infoName.textContent = name;
    infoIP.textContent = ip;
    infoEnabled.textContent = enabled ? "Enabled (1)" : "Disabled (0)";
    infoInterval.textContent = interval + "s";
    infoNextDue.textContent = nextDue > 0 ? String(nextDue) + " (" + humanDue(nextDue) + ")" : "-";
    infoLastPing.textContent = lastPingText;
    infoLastResp.textContent = lastRespText;
    infoLatency.textContent = (lat >= 0) ? (lat + " ms") : "-";
    infoStatus.textContent = status.toUpperCase();

    infoSubtitle.textContent = name + " • " + ip;
    btnInfoToggle.innerHTML = (enabled ? `{{ icons.ban|safe }} Disable` : `{{ icons.check|safe }} Activate`);
  }

  function humanDue(epoch){
    const e = parseInt(epoch || "0", 10);
    if (!e) return "-";
    const now = Math.floor(Date.now()/1000);
    if (e <= now) return "due";
    const diff = e - now;
    if (diff < 60) return `in ${diff}s`;
    if (diff < 3600) return `in ${Math.floor(diff/60)}m`;
    return `in ${Math.floor(diff/3600)}h ${Math.floor((diff%3600)/60)}m`;
  }

  async function openInfo(name){
    const row = document.querySelector(`tr[data-name="${CSS.escape(name)}"]`);
    if (!row) return;
    setInfoFromRow(row);

    // Fetch full endpoint + canonical values from CLI get
    try{
      const data = await fetchTargetInfo(name);
      if (data.ok && data.target){
        currentInfoEndpoint = data.target.endpoint || "";
        infoEndpoint.textContent = data.target.endpoint || "-";

        // keep enabled/interval/name/ip coherent if CLI returns it
        infoEnabled.textContent = data.target.enabled ? "Enabled (1)" : "Disabled (0)";
        infoInterval.textContent = String(data.target.interval || 60) + "s";
        infoIP.textContent = data.target.ip || infoIP.textContent;
        infoName.textContent = data.target.name || infoName.textContent;
        currentInfoName = data.target.name || currentInfoName;

        btnInfoToggle.innerHTML = (data.target.enabled ? `{{ icons.ban|safe }} Disable` : `{{ icons.check|safe }} Activate`);
      }else{
        infoEndpoint.textContent = "(unable to read endpoint)";
      }
    }catch(e){
      infoEndpoint.textContent = "(failed to load endpoint)";
    }

    show(infoModal);
  }

  // ---- Edit modal ----
  const editModal = document.getElementById("editModal");
  const btnCloseEdit = document.getElementById("btnCloseEdit");
  const btnEditCancel = document.getElementById("btnEditCancel");
  const editForm = document.getElementById("editForm");
  const btnEditSave = document.getElementById("btnEditSave");
  const editSubtitle = document.getElementById("editSubtitle");

  const editOldName = document.getElementById("editOldName");
  const editName = document.getElementById("editName");
  const editIP = document.getElementById("editIP");
  const editInterval = document.getElementById("editInterval");
  const editEndpoint = document.getElementById("editEndpoint");
  const editEnabled = document.getElementById("editEnabled");

  btnCloseEdit.addEventListener("click", () => hide(editModal));
  btnEditCancel.addEventListener("click", () => hide(editModal));
  editModal.addEventListener("click", (e) => { if (e.target === editModal) hide(editModal); });

  function validIP(ip){
    const parts = String(ip||"").trim().split(".");
    if (parts.length !== 4) return false;
    for (const p of parts){
      if (!/^\d+$/.test(p)) return false;
      const n = parseInt(p, 10);
      if (n < 0 || n > 255) return false;
    }
    return true;
  }
  function validURL(u){
    const s = String(u||"").trim().toLowerCase();
    return s.startsWith("http://") || s.startsWith("https://");
  }

  function openEditFromData(data){
    const t = data.target || {};
    editOldName.value = t.name || "";
    editName.value = t.name || "";
    editIP.value = t.ip || "";
    editInterval.value = String(t.interval || 60);
    editEndpoint.value = t.endpoint || "";
    editEnabled.value = (t.enabled ? "1" : "0");
    editSubtitle.textContent = (t.name || "-") + " • edit details";
    show(editModal);
  }

  async function openEdit(name){
    try{
      const data = await fetchTargetInfo(name);
      if (!data.ok){
        toast("Error", data.message || "Failed to load target");
        return;
      }
      openEditFromData(data);
    }catch(e){
      toast("Error", "Failed to load target");
    }
  }

  btnInfoEdit.addEventListener("click", async () => {
    if (!currentInfoName) return;
    hide(infoModal);
    await openEdit(currentInfoName);
  });

  editForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const oldName = editOldName.value.trim();
    const name = editName.value.trim();
    const ip = editIP.value.trim();
    const interval = editInterval.value.trim();
    const endpoint = editEndpoint.value.trim();
    const enabled = editEnabled.value;

    if (!name){
      toast("Invalid", "Name is required");
      return;
    }
    if (!validIP(ip)){
      toast("Invalid", "IP address is not valid");
      return;
    }
    const n = parseInt(interval, 10);
    if (!Number.isFinite(n) || n < 10 || n > 86400){
      toast("Invalid", "Interval must be 10–86400 seconds");
      return;
    }
    if (!validURL(endpoint)){
      toast("Invalid", "Endpoint URL must start with http:// or https://");
      return;
    }

    btnEditSave.disabled = true;
    btnEditSave.textContent = "Saving…";
    try{
      const fd = new FormData();
      fd.set("old_name", oldName);
      fd.set("name", name);
      fd.set("ip", ip);
      fd.set("interval", String(n));
      fd.set("endpoint", endpoint);
      fd.set("enabled", enabled);

      const res = await fetch("/api/edit-target", {method:"POST", body: fd});
      const data = await res.json();
      if (data.ok){
        toast("Saved", data.message || "Updated");
        hide(editModal);
        await refreshState(true);
      }else{
        toast("Error", data.message || "Failed to save");
      }
    }catch(err){
      toast("Error", err && err.message ? err.message : "Failed to save");
    }finally{
      btnEditSave.disabled = false;
      btnEditSave.innerHTML = `{{ icons.check|safe }} Save changes`;
    }
  });

  // ---- API helpers ----
  async function apiPost(url, fd){
    const res = await fetch(url, {method:"POST", body: fd});
    return await res.json();
  }

  async function postJson(url, payload){
    const res = await fetch(url, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(payload || {})
    });
    return await res.json();
  }

  // ---- Disable/enable with Undo toast ----
  async function disableOne(name){
    const fd = new FormData();
    fd.set("name", name);
    return await apiPost("/api/disable", fd);
  }
  async function enableOne(name){
    const fd = new FormData();
    fd.set("name", name);
    return await apiPost("/api/enable", fd);
  }

  async function toggleTarget(name, makeEnabled){
    if (makeEnabled){
      const r = await enableOne(name);
      return r;
    }
    const r = await disableOne(name);
    return r;
  }

  async function confirmDisableWithUndo(name){
    // do disable now
    const r = await disableOne(name);
    if (!r.ok){
      toast("Error", r.message || "Disable failed");
      return;
    }
    await refreshState(true);

    toast("Disabled", `${name} disabled`, {
      actionText: "Undo",
      ttl: 5000,
      onAction: async (el) => {
        el.remove();
        const rr = await enableOne(name);
        toast(rr.ok ? "Restored" : "Error", rr.message || (rr.ok ? "Enabled" : "Failed"));
        await refreshState(true);
      }
    });
  }

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

  function syncToggleLabelForRow(row){
    const enabled = row.getAttribute("data-enabled") === "1";
    const label = row.querySelector(".toggle-label");
    if (label) label.textContent = enabled ? "Disable" : "Activate";
  }

  function attachMenuActions(){
    document.querySelectorAll("tr[data-name]").forEach(row => {
      const name = row.getAttribute("data-name");
      syncToggleLabelForRow(row);

      row.querySelectorAll(".menu-item").forEach(btn => {
        if (btn.dataset.bound === "1") return;
        btn.dataset.bound = "1";
        btn.addEventListener("click", async () => {
          closeAllMenus();
          const action = btn.getAttribute("data-action");

          if (action === "remove"){
            openConfirmRemove(name);
            return;
          }

          if (action === "info"){
            await openInfo(name);
            return;
          }

          if (action === "edit"){
            await openEdit(name);
            return;
          }

          if (action === "toggle"){
            const enabled = row.getAttribute("data-enabled") === "1";
            if (enabled){
              await confirmDisableWithUndo(name);
            }else{
              const r = await enableOne(name);
              toast(r.ok ? "Activated" : "Error", r.message || (r.ok ? "Enabled" : "Failed"));
              await refreshState(true);
            }
            return;
          }

          try{
            if (action === "test"){
              toast("Testing", `Running test for ${name}…`);
              const fd = new FormData();
              fd.set("name", name);
              const data = await apiPost("/api/test", fd);
              toast(data.ok ? "OK" : "Error", data.message || (data.ok ? "Done" : "Failed"));
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
            row.setAttribute("data-interval", String(n));
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

  // ---- Search + quick filter ----
  const searchBox = document.getElementById("searchBox");
  let statusFilter = "all";

  function applyFilters(){
    const q = (searchBox.value || "").trim().toLowerCase();
    document.querySelectorAll("#tbody tr[data-name]").forEach(row => {
      const name = (row.getAttribute("data-name") || "").toLowerCase();
      const ip = (row.getAttribute("data-ip") || "").toLowerCase();
      const st = (row.getAttribute("data-status") || "").toLowerCase();

      const matchQ = !q || name.includes(q) || ip.includes(q) || st.includes(q);
      const matchSt = (statusFilter === "all") || (st === statusFilter);

      row.style.display = (matchQ && matchSt) ? "" : "none";
    });
    updateBulkButtons();
  }

  searchBox.addEventListener("input", applyFilters);

  document.querySelectorAll(".chipbtn[data-filter]").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".chipbtn[data-filter]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      statusFilter = btn.getAttribute("data-filter") || "all";
      applyFilters();
    });
  });

  // ---- Selection + bulk actions ----
  const selAll = document.getElementById("selAll");
  const btnRunSelected = document.getElementById("btnRunSelected");
  const btnDisableSelected = document.getElementById("btnDisableSelected");
  const btnEnableSelected = document.getElementById("btnEnableSelected");
  const btnRunNowAll = document.getElementById("btnRunNowAll");

  function selectedNames(){
    const out = [];
    document.querySelectorAll("#tbody tr[data-name]").forEach(row => {
      if (row.style.display === "none") return;
      const cb = row.querySelector(".selRow");
      if (cb && cb.checked) out.push(row.getAttribute("data-name"));
    });
    return out;
  }

  function updateBulkButtons(){
    const names = selectedNames();
    const has = names.length > 0;

    [btnRunSelected, btnDisableSelected, btnEnableSelected].forEach(b => {
      b.classList.toggle("btn-disabled", !has);
      b.disabled = !has;
    });

    const visibleRows = Array.from(document.querySelectorAll("#tbody tr[data-name]")).filter(r => r.style.display !== "none");
    const visibleCbs = visibleRows.map(r => r.querySelector(".selRow")).filter(Boolean);
    const allChecked = visibleCbs.length > 0 && visibleCbs.every(cb => cb.checked);
    const anyChecked = visibleCbs.some(cb => cb.checked);
    selAll.checked = allChecked;
    selAll.indeterminate = !allChecked && anyChecked;
  }

  selAll.addEventListener("change", () => {
    const visibleRows = Array.from(document.querySelectorAll("#tbody tr[data-name]")).filter(r => r.style.display !== "none");
    visibleRows.forEach(row => {
      const cb = row.querySelector(".selRow");
      if (cb) cb.checked = selAll.checked;
    });
    updateBulkButtons();
  });

  function attachSelHandlers(){
    document.querySelectorAll(".selRow").forEach(cb => {
      if (cb.dataset.bound === "1") return;
      cb.dataset.bound = "1";
      cb.addEventListener("change", updateBulkButtons);
    });
  }

  btnRunSelected.addEventListener("click", async () => {
    const names = selectedNames();
    if (!names.length) return;
    toast("Run selected", `Starting ${names.length} target(s)…`);
    const data = await postJson("/api/run-selected", {targets: names});
    toast(data.ok ? "Started" : "Error", data.message || (data.ok ? "Started" : "Failed"));
  });

  btnDisableSelected.addEventListener("click", async () => {
    const names = selectedNames();
    if (!names.length) return;

    // disable each (with one undo toast per item is too noisy)
    toast("Disable selected", `Disabling ${names.length} target(s)…`);
    const data = await postJson("/api/disable-selected", {targets: names});
    toast(data.ok ? "Done" : "Error", data.message || (data.ok ? "Done" : "Failed"));
    await refreshState(true);
  });

  btnEnableSelected.addEventListener("click", async () => {
    const names = selectedNames();
    if (!names.length) return;
    toast("Activate selected", `Activating ${names.length} target(s)…`);
    const data = await postJson("/api/enable-selected", {targets: names});
    toast(data.ok ? "Done" : "Error", data.message || (data.ok ? "Done" : "Failed"));
    await refreshState(true);
  });

  btnRunNowAll.addEventListener("click", async () => {
    toast("Run now", "Starting run…");
    const data = await postJson("/api/run-selected", {targets: []});
    toast(data.ok ? "Started" : "Error", data.message || (data.ok ? "Started" : "Failed"));
  });

  // ---- Sorting ----
  let sortKey = null;
  let sortDir = 1; // 1 asc, -1 desc

  function statusRank(st){
    // smaller first
    const s = String(st||"unknown").toLowerCase();
    if (s === "down") return 1;
    if (s === "unknown") return 2;
    if (s === "up") return 3;
    if (s === "disabled") return 4;
    return 9;
  }

  function ipToNum(ip){
    const p = String(ip||"").split(".");
    if (p.length !== 4) return 0;
    let n = 0;
    for (let i=0;i<4;i++){
      const v = parseInt(p[i],10);
      if (!Number.isFinite(v)) return 0;
      n = (n*256) + v;
    }
    return n;
  }

  function getSortVal(row, key){
    if (key === "name") return (row.getAttribute("data-name") || "").toLowerCase();
    if (key === "ip") return ipToNum(row.getAttribute("data-ip") || "");
    if (key === "status") return statusRank(row.getAttribute("data-status") || "unknown");
    if (key === "interval") return parseInt(row.getAttribute("data-interval") || "0", 10) || 0;
    if (key === "last_ping") return parseInt(row.getAttribute("data-last-ping") || "0", 10) || 0;
    return (row.getAttribute("data-name") || "").toLowerCase();
  }

  function applySort(){
    if (!sortKey) return;
    const tbody = document.getElementById("tbody");
    const rows = Array.from(tbody.querySelectorAll("tr[data-name]"));

    rows.sort((a,b) => {
      const va = getSortVal(a, sortKey);
      const vb = getSortVal(b, sortKey);
      if (va < vb) return -1 * sortDir;
      if (va > vb) return 1 * sortDir;
      return 0;
    });

    rows.forEach(r => tbody.appendChild(r));

    document.querySelectorAll(".sort-ind").forEach(ind => {
      ind.classList.remove("on");
      ind.textContent = "↕";
    });
    const ind = document.querySelector(`.sort-ind[data-ind="${sortKey}"]`);
    if (ind){
      ind.classList.add("on");
      ind.textContent = sortDir === 1 ? "↑" : "↓";
    }
  }

  document.querySelectorAll("th.sortable[data-sort]").forEach(th => {
    th.addEventListener("click", () => {
      const k = th.getAttribute("data-sort");
      if (!k) return;
      if (sortKey === k){
        sortDir = sortDir * -1;
      }else{
        sortKey = k;
        sortDir = 1;
      }
      applySort();
      applyFilters();
    });
  });

  // ---- Run summary popover ----
  const statDurCard = document.getElementById("statDurCard");
  const runSummaryPop = document.getElementById("runSummaryPop");
  const btnCloseSummary = document.getElementById("btnCloseSummary");

  function setRunSummary(summary){
    const s = summary || {};
    document.getElementById("rsTotal").textContent = String(s.total ?? "-");
    document.getElementById("rsDue").textContent = String(s.due ?? "-");
    document.getElementById("rsSkipped").textContent = String(s.skipped ?? "-");
    document.getElementById("rsPingOk").textContent = String(s.ping_ok ?? "-");
    document.getElementById("rsPingFail").textContent = String(s.ping_fail ?? "-");
    document.getElementById("rsSent").textContent = String(s.sent ?? "-");
    document.getElementById("rsCurlFail").textContent = String(s.curl_fail ?? "-");
    document.getElementById("rsDisabled").textContent = String(s.disabled ?? "-");
    document.getElementById("rsForce").textContent = String(s.force ?? "-");
    document.getElementById("rsDuration").textContent = "Duration: " + (s.duration_ms ? (s.duration_ms + " ms") : "-");
  }

  async function loadRunSummary(){
    try{
      const res = await fetch("/api/last-run-summary", {cache:"no-store"});
      const data = await res.json();
      if (data.ok && data.summary){
        setRunSummary(data.summary);
        return;
      }
    }catch(e){}
    setRunSummary(null);
  }

  function closeSummary(){
    runSummaryPop.classList.remove("show");
  }
  btnCloseSummary.addEventListener("click", (e) => { e.stopPropagation(); closeSummary(); });

  statDurCard.addEventListener("click", async (e) => {
    // toggle
    const isOpen = runSummaryPop.classList.contains("show");
    if (isOpen){
      closeSummary();
      return;
    }
    await loadRunSummary();
    runSummaryPop.classList.add("show");
  });

  document.addEventListener("click", (e) => {
    if (runSummaryPop.classList.contains("show")){
      if (!e.target.closest("#statDurCard")){
        closeSummary();
      }
    }
  });

  // ---- Real-time refresh + row blink ----
  function setStatusChip(row, status){
    const chip = row.querySelector(".status-chip");
    const text = row.querySelector(".status-text");
    if (!chip || !text) return;

    chip.classList.remove("status-up","status-down","status-unknown","status-disabled");
    if (status === "up") chip.classList.add("status-up");
    else if (status === "down") chip.classList.add("status-down");
    else if (status === "disabled") chip.classList.add("status-disabled");
    else chip.classList.add("status-unknown");

    text.textContent = (status || "unknown").toUpperCase();
  }

  function blinkRow(row, ok){
    if (!row) return;
    row.classList.remove("blink-ok","blink-bad");
    void row.offsetWidth;
    row.classList.add(ok ? "blink-ok" : "blink-bad");
    setTimeout(() => row.classList.remove("blink-ok","blink-bad"), 1000);
  }

  function recomputeStats(targets){
    const up = targets.filter(t => t.status === "up").length;
    const down = targets.filter(t => t.status === "down").length;
    const unknown = targets.filter(t => t.status === "unknown").length;
    document.getElementById("statUp").textContent = String(up);
    document.getElementById("statDown").textContent = String(down);
    document.getElementById("statUnknown").textContent = String(unknown);
  }

  function refreshToggleLabelEverywhere(){
    document.querySelectorAll("tr[data-name]").forEach(row => syncToggleLabelForRow(row));
  }

  async function refreshState(force=false){
    try{
      const res = await fetch("/state", {cache:"no-store"});
      const data = await res.json();
      const map = new Map();
      (data.targets || []).forEach(t => map.set(t.name, t));
      recomputeStats(data.targets || []);

      document.querySelectorAll("tr[data-name]").forEach(row => {
        const name = row.getAttribute("data-name");
        const t = map.get(name);
        if (!t) return;

        row.setAttribute("data-status", t.status || "unknown");
        row.setAttribute("data-enabled", t.enabled ? "1" : "0");
        row.setAttribute("data-interval", String(t.interval || 60));
        row.setAttribute("data-next-due", String(t.next_due_epoch || 0));
        row.setAttribute("data-lat", String(t.last_rtt_ms ?? -1));

        setStatusChip(row, t.status);

        const prevPing = parseInt(row.getAttribute("data-last-ping") || "0", 10);
        const newPing = parseInt(String(t.last_ping_epoch || 0), 10);

        if (newPing && newPing !== prevPing){
          row.setAttribute("data-last-ping", String(newPing));
          blinkRow(row, t.status === "up");
        }

        const lp = row.querySelector(".last-ping");
        const lr = row.querySelector(".last-resp");
        if (lp && lp.textContent !== (t.last_ping_human || "-")) lp.textContent = t.last_ping_human || "-";
        if (lr && lr.textContent !== (t.last_response_human || "-")) lr.textContent = t.last_response_human || "-";

        const iv = row.querySelector(".interval-input");
        if (iv && force){
          iv.value = String(t.interval || 60);
          iv.setAttribute("data-interval", String(t.interval || 60));
        }
      });

      // if info modal is open for current target, keep it fresh (except endpoint)
      if (infoModal.classList.contains("show") && currentInfoName){
        const row = document.querySelector(`tr[data-name="${CSS.escape(currentInfoName)}"]`);
        if (row) setInfoFromRow(row);
      }

      attachIntervalHandlers();
      attachMenuActions();
      attachSelHandlers();
      refreshToggleLabelEverywhere();

      // keep sort stable after refresh
      applySort();

      applyFilters();
    }catch(e){
      // silent
    }
  }

  // ---- Info modal toggle button ----
  btnInfoToggle.addEventListener("click", async () => {
    if (!currentInfoName) return;
    const row = document.querySelector(`tr[data-name="${CSS.escape(currentInfoName)}"]`);
    const enabled = row ? (row.getAttribute("data-enabled") === "1") : true;

    if (enabled){
      await confirmDisableWithUndo(currentInfoName);
    }else{
      const r = await enableOne(currentInfoName);
      toast(r.ok ? "Activated" : "Error", r.message || (r.ok ? "Enabled" : "Failed"));
      await refreshState(true);
    }
  });

  // ---- Bulk initial state ----
  applyFilters();
  updateBulkButtons();

  // init
  attachIntervalHandlers();
  attachMenuActions();
  attachSelHandlers();
  setInterval(() => refreshState(false), {{ poll_seconds }} * 1000);

  // ESC closes modals + menus + popover
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape"){
      if (logModal.classList.contains("show")) hide(logModal);
      if (addModal.classList.contains("show")) hide(addModal);
      if (confirmModal.classList.contains("show")) hide(confirmModal);
      if (infoModal.classList.contains("show")) hide(infoModal);
      if (editModal.classList.contains("show")) hide(editModal);
      closeAllMenus();
      closeSummary();
    }
  });

})();
</script>
</body>
</html>
"""

@APP.get("/")
def index():
    ts = merged_targets()

    last_dur = ""
    try:
        if os.path.exists(RUN_OUT_FILE):
            with open(RUN_OUT_FILE, "r", encoding="utf-8") as f:
                out = f.read().strip()
            s = parse_run_summary(out or "")
            if s and s.get("duration_ms"):
                last_dur = format_duration_ms(int(s.get("duration_ms") or 0))
    except Exception:
        pass
    last_dur = last_dur or "-"

    return render_template_string(
        TEMPLATE,
        targets=ts,
        stats=stats_from_targets(ts),
        last_run_duration=last_dur,
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
        src = "journalctl -t interheart -o cat"
        actual = len(text.splitlines()) if text else 0
        return jsonify({"source": src, "lines": actual, "updated": updated, "text": text})
    except Exception as e:
        return jsonify({"source": "journalctl (error)", "lines": 1, "updated": updated, "text": f"(journalctl error: {str(e)})"})

@APP.get("/api/last-run-summary")
def api_last_run_summary():
    s = get_last_run_summary()
    return jsonify({"ok": True, "summary": s})

@APP.get("/api/target-info")
def api_target_info():
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "message": "Missing name"})
    rc, out = run_cmd(["get", name])
    if rc != 0:
        return jsonify({"ok": False, "message": out or "Not found"})

    parts = (out or "").strip().split("|")
    if len(parts) < 5:
        return jsonify({"ok": False, "message": "Bad get output"})
    return jsonify({
        "ok": True,
        "target": {
            "name": parts[0],
            "ip": parts[1],
            "endpoint": parts[2],
            "interval": int(parts[3]) if parts[3].isdigit() else 60,
            "enabled": True if parts[4] == "1" else False,
        }
    })

@APP.post("/api/edit-target")
def api_edit_target():
    old_name = request.form.get("old_name", "").strip()
    new_name = request.form.get("name", "").strip()
    ip = request.form.get("ip", "").strip()
    endpoint = request.form.get("endpoint", "").strip()
    interval = request.form.get("interval", "").strip()
    enabled = request.form.get("enabled", "1").strip()
    enabled = "0" if enabled == "0" else "1"

    rc, out = run_cmd(["edit", old_name, new_name, ip, endpoint, interval, enabled])
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

@APP.post("/api/disable")
def api_disable_one():
    name = request.form.get("name", "")
    rc, out = run_cmd(["disable", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/enable")
def api_enable_one():
    name = request.form.get("name", "")
    rc, out = run_cmd(["enable", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/disable-selected")
def api_disable_selected():
    data = request.get_json(silent=True) or {}
    targets = data.get("targets") or []
    targets = [str(x).strip() for x in targets if str(x).strip()]
    if not targets:
        return jsonify({"ok": False, "message": "No targets selected"})

    failed = []
    for name in targets:
        rc, out = run_cmd(["disable", name])
        if rc != 0:
            failed.append(f"{name}: {out}")

    if failed:
        return jsonify({"ok": False, "message": "Some failed: " + " | ".join(failed)})
    return jsonify({"ok": True, "message": f"Disabled {len(targets)} target(s)"})


@APP.post("/api/enable-selected")
def api_enable_selected():
    data = request.get_json(silent=True) or {}
    targets = data.get("targets") or []
    targets = [str(x).strip() for x in targets if str(x).strip()]
    if not targets:
        return jsonify({"ok": False, "message": "No targets selected"})

    failed = []
    for name in targets:
        rc, out = run_cmd(["enable", name])
        if rc != 0:
            failed.append(f"{name}: {out}")

    if failed:
        return jsonify({"ok": False, "message": "Some failed: " + " | ".join(failed)})
    return jsonify({"ok": True, "message": f"Enabled {len(targets)} target(s)"})


@APP.post("/api/run-selected")
def api_run_selected():
    """
    Starts a run-now in background.
    If targets list is empty => run all targets now.
    """
    ensure_state_dir()

    data = request.get_json(silent=True) or {}
    targets = data.get("targets") or []
    targets = [str(x) for x in targets if str(x).strip()]
    targets_arg = ",".join(targets)

    meta = load_run_meta()
    existing_pid = int(meta.get("pid") or 0)
    if existing_pid and pid_is_running(existing_pid):
        return jsonify({"ok": True, "message": "Already running", "pid": existing_pid})

    cmd = ["sudo", CLI, "run-now"]
    if targets_arg:
        cmd += ["--targets", targets_arg]

    try:
        out_f = open(RUN_OUT_FILE, "w", encoding="utf-8")
        p = subprocess.Popen(cmd, stdout=out_f, stderr=subprocess.STDOUT, text=True)
        save_run_meta({"pid": p.pid, "started": int(time.time()), "finished": 0, "rc": None})
        return jsonify({"ok": True, "message": "Started", "pid": p.pid})
    except Exception as e:
        save_run_meta({"pid": 0, "started": 0, "finished": int(time.time()), "rc": 1})
        return jsonify({"ok": False, "message": f"Failed to start run-now: {str(e)}"})

if __name__ == "__main__":
    APP.run(host=BIND_HOST, port=BIND_PORT, threaded=True)
