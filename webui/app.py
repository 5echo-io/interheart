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
    os.makedirs(STATE_DIR, exist_ok=True)
    for p in (RUNTIME_FILE, RUN_META_FILE, RUN_OUT_FILE):
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write("")
    # root service, but keep readable
    try:
        os.chmod(RUNTIME_FILE, 0o644)
        os.chmod(RUN_META_FILE, 0o644)
        os.chmod(RUN_OUT_FILE, 0o644)
    except Exception:
        pass

ensure_state_dir()

def run_cmd(args):
    """
    WebUI now runs as root (systemd service), so we do NOT use sudo here.
    """
    cmd = [CLI] + args
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

def journalctl_lines(lines: int) -> str:
    """
    WebUI runs as root, so no sudo needed.
    Use --output=cat to remove syslog prefixes in UI.
    """
    cmd = ["journalctl", "-t", "interheart", "-n", str(lines), "--no-pager", "--output=cat"]
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

def load_json(path):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return {}

def save_json(path, data):
    ensure_state_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    try:
        os.chmod(path, 0o644)
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

# TEMPLATE unchanged in this patch (keep your existing UI layout)
# To keep this answer focused on the two critical bugs, we reuse your current template from repo.
# If you prefer, paste your existing TEMPLATE here and keep as-is.
# ----
# IMPORTANT:
# Replace this TEMPLATE variable with the one you already have in your repo (from v4.5.x),
# OR keep it exactly as currently in webui/app.py after your last good UI update.
# ----

# ⬇️ PLACEHOLDER TEMPLATE:
# In your repo you already have a full template. Keep it.
TEMPLATE = """<!doctype html><html><body><h3>Template missing</h3></body></html>"""

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
                raw = f.read().strip()
            if raw:
                data = json.loads(raw)
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
        text = journalctl_lines(lines)
        src = "journalctl -t interheart -o cat"
        actual = len(text.splitlines()) if text else 0
        return jsonify({"source": src, "lines": actual, "updated": updated, "text": text})
    except Exception as e:
        return jsonify({"source": "journalctl (error)", "lines": 1, "updated": updated, "text": f"(journalctl error: {str(e)})"})

@APP.post("/api/run-now")
def api_run_now():
    ensure_state_dir()

    meta = load_json(RUN_META_FILE)
    existing_pid = int(meta.get("pid") or 0)
    if existing_pid and pid_is_running(existing_pid):
        return jsonify({"ok": True, "message": "Already running", "pid": existing_pid})

    save_json(RUNTIME_FILE, {"status":"running","current":"","done":0,"due":0,"updated":int(time.time())})

    cmd = [CLI, "run-now"]
    try:
        out_f = open(RUN_OUT_FILE, "w", encoding="utf-8")
        p = subprocess.Popen(cmd, stdout=out_f, stderr=subprocess.STDOUT, text=True)
        save_json(RUN_META_FILE, {"pid": p.pid, "started": int(time.time()), "finished": 0, "rc": None})
        return jsonify({"ok": True, "message": "Started", "pid": p.pid})
    except Exception as e:
        save_json(RUN_META_FILE, {"pid": 0, "started": 0, "finished": int(time.time()), "rc": 1})
        return jsonify({"ok": False, "message": f"Failed to start run-now: {str(e)}"})

@APP.get("/api/run-status")
def api_run_status():
    meta = load_json(RUN_META_FILE)
    pid = int(meta.get("pid") or 0)
    started = int(meta.get("started") or 0)
    finished = int(meta.get("finished") or 0)

    if pid and pid_is_running(pid):
        return jsonify({"running": True, "finished": False, "pid": pid, "started": started})

    if started and not finished:
        meta["finished"] = int(time.time())
        meta["pid"] = 0
        save_json(RUN_META_FILE, meta)

    return jsonify({"running": False, "finished": bool(started), "pid": pid, "started": started, "finished_at": int(meta.get("finished") or 0)})

@APP.get("/api/run-result")
def api_run_result():
    meta = load_json(RUN_META_FILE)
    try:
        out = ""
        if os.path.exists(RUN_OUT_FILE):
            with open(RUN_OUT_FILE, "r", encoding="utf-8") as f:
                out = f.read().strip()
    except Exception:
        out = ""

    summary = parse_run_summary(out)
    ok = True
    if "Unknown command" in out:
        ok = False

    return jsonify({"ok": ok, "message": out or ("OK" if ok else "Failed"), "summary": summary, "meta": meta})

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
    APP.run(host=BIND_HOST, port=BIND_PORT, threaded=True)
