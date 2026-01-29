#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template
import os
import subprocess
import time
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

APP = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
)

# ---- config ----
CLI = os.environ.get("INTERHEART_CLI", "/usr/local/bin/interheart")
BIND_HOST = os.environ.get("WEBUI_BIND", "0.0.0.0")
BIND_PORT = int(os.environ.get("WEBUI_PORT", "8088"))

LOG_LINES_DEFAULT = 200
STATE_POLL_SECONDS = 2

STATE_DIR = Path(os.environ.get("INTERHEART_STATE_DIR", "/var/lib/interheart"))
DB_PATH = STATE_DIR / "state.db"
RUN_META_FILE = STATE_DIR / "run_meta.json"
RUN_OUT_FILE = STATE_DIR / "run_last_output.txt"

SUMMARY_RE = re.compile(
    r"total=(\d+)\s+due=(\d+)\s+skipped=(\d+)\s+ping_ok=(\d+)\s+ping_fail=(\d+)\s+sent=(\d+)\s+curl_fail=(\d+)"
)

def read_version() -> str:
    # try repo root VERSION first
    try:
        candidates = [
            (BASE_DIR.parent / "VERSION"),
            (BASE_DIR / "VERSION"),
        ]
        for p in candidates:
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return "0.0.0"

UI_VERSION = read_version()
COPYRIGHT_YEAR = "2026"

def ensure_state_dir():
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        # ensure meta/output exists
        for p in (RUN_META_FILE, RUN_OUT_FILE):
            if not p.exists():
                p.write_text("", encoding="utf-8")
                try:
                    os.chmod(str(p), 0o644)
                except Exception:
                    pass
    except Exception:
        pass

ensure_state_dir()

def die_json(msg: str, code: int = 500):
    return jsonify({"ok": False, "message": msg}), code

def run_cmd(args):
    cmd = [CLI] + args
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    merged = out + (("\n" + err) if err else "")
    return p.returncode, merged.strip()

def journalctl_lines(lines: int) -> str:
    cmd = ["journalctl", "-t", "interheart", "-n", str(lines), "--no-pager", "--output=cat"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "journalctl failed").strip())
    return (p.stdout or "").strip()

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

def pid_is_running(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def load_run_meta() -> dict:
    try:
        if RUN_META_FILE.exists():
            raw = RUN_META_FILE.read_text(encoding="utf-8").strip()
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return {}

def save_run_meta(meta: dict):
    ensure_state_dir()
    try:
        RUN_META_FILE.write_text(json.dumps(meta), encoding="utf-8")
        try:
            os.chmod(str(RUN_META_FILE), 0o644)
        except Exception:
            pass
    except Exception:
        pass

def mask_endpoint(url: str) -> str:
    if not url:
        return "-"
    # scheme://host[:port]/*** (hide path/query)
    try:
        scheme = re.split(r"://", url, maxsplit=1)[0]
        rest = re.sub(r"^[a-zA-Z]+://", "", url)
        host = rest.split("/", 1)[0]
        if scheme and host:
            return f"{scheme}://{host}/***"
    except Exception:
        pass
    return "***"

# --- Data from CLI: list/status/get ---
def parse_list_targets(list_output: str):
    targets = []
    in_table = False
    for line in (list_output or "").splitlines():
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
        # Expected columns from CLI `list`:
        # NAME IP INTERVAL ENABLED ENDPOINT
        if len(parts) < 5:
            continue
        name = parts[0]
        ip = parts[1]
        interval = parts[2].replace("s", "").strip()
        enabled = parts[3]
        endpoint_masked = parts[4]
        targets.append({
            "name": name,
            "ip": ip,
            "interval": int(interval) if interval.isdigit() else 60,
            "enabled": 1 if str(enabled).strip() == "1" else 0,
            "endpoint_masked": endpoint_masked
        })
    return targets

def parse_status(status_output: str):
    state = {}
    in_table = False
    for line in (status_output or "").splitlines():
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
        # Expected columns from CLI `status`:
        # NAME STATUS NEXT_IN NEXT_DUE LAST_PING LAST_RESP LAT_MS
        if len(parts) < 7:
            continue
        name = parts[0]
        status = parts[1]
        last_ping = parts[4]
        last_sent = parts[5]
        lat_ms = parts[6]
        state[name] = {
            "status": status,
            "last_ping_epoch": int(last_ping) if last_ping.isdigit() else 0,
            "last_sent_epoch": int(last_sent) if last_sent.isdigit() else 0,
            "last_rtt_ms": int(lat_ms) if str(lat_ms).lstrip("-").isdigit() else -1,
        }
    return state

def human_ts(epoch: int):
    if not epoch or epoch <= 0:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))
    except Exception:
        return "-"

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
            "name": t["name"],
            "ip": t["ip"],
            "interval": t["interval"],
            "status": status,
            "enabled": int(t.get("enabled") or 0),
            "last_ping_human": human_ts(last_ping_epoch),
            "last_response_human": human_ts(last_sent_epoch),
            "last_ping_epoch": last_ping_epoch,
            "last_response_epoch": last_sent_epoch,
            "last_rtt_ms": int(st.get("last_rtt_ms", -1) or -1),
            # kept for info modal / masking
            "endpoint_masked": t.get("endpoint_masked") or "-",
        })
    return merged


# ---- API: info (DB-backed, uses history samples if present) ----
def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


def compute_uptime_stats(db_path: Path, name: str, seconds: int):
    """Return {samples, up, down, pct, avg_rtt_ms} for the given window.

    Uses `history` table if present. If missing/empty, returns None.
    """
    import sqlite3

    if not db_path.exists():
        return None

    since = int(time.time()) - int(seconds)
    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        # Check table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='history' LIMIT 1;")
        if not cur.fetchone():
            return None

        cur.execute(
            """
            SELECT
              SUM(CASE WHEN status='up' THEN 1 ELSE 0 END) AS up_cnt,
              SUM(CASE WHEN status='down' THEN 1 ELSE 0 END) AS down_cnt,
              AVG(CASE WHEN rtt_ms >= 0 THEN rtt_ms ELSE NULL END) AS avg_rtt
            FROM history
            WHERE name=? AND ts>=? AND status IN ('up','down');
            """,
            (name, since),
        )
        row = cur.fetchone()
        up_cnt = _safe_int(row["up_cnt"], 0)
        down_cnt = _safe_int(row["down_cnt"], 0)
        samples = up_cnt + down_cnt
        if samples <= 0:
            return None

        pct = round((up_cnt / samples) * 100.0, 2)
        avg_rtt = row["avg_rtt"]
        avg_rtt_ms = int(round(avg_rtt)) if avg_rtt is not None else None
        return {
            "samples": samples,
            "up": up_cnt,
            "down": down_cnt,
            "pct": pct,
            "avg_rtt_ms": avg_rtt_ms,
        }
    except Exception:
        return None
    finally:
        try:
            con.close()
        except Exception:
            pass


@APP.get("/api/info")
def api_info():
    name = (request.args.get("name") or "").strip()
    if not name:
        return die_json("Missing name", 400)

    # Get base target info via CLI (source of truth)
    rc, out = run_cmd(["get", name])
    if rc != 0:
        return jsonify({"ok": False, "message": out or "Not found"})

    # CLI get returns: name|ip|endpoint|interval|enabled
    parts = (out or "").split("|")
    ip = parts[1] if len(parts) > 1 else "-"
    endpoint = parts[2] if len(parts) > 2 else "-"
    interval = _safe_int(parts[3] if len(parts) > 3 else 60, 60)
    enabled = _safe_int(parts[4] if len(parts) > 4 else 1, 1)

    # Attach current runtime-ish view from /state aggregation
    cur = None
    try:
        cur = next((t for t in merged_targets() if t.get("name") == name), None)
    except Exception:
        cur = None

    windows = [
        ("24h", 24 * 3600),
        ("7d", 7 * 24 * 3600),
        ("30d", 30 * 24 * 3600),
        ("90d", 90 * 24 * 3600),
    ]
    uptime = {}
    for k, secs in windows:
        uptime[k] = compute_uptime_stats(DB_PATH, name, secs)

    return jsonify({
        "ok": True,
        "name": name,
        "ip": ip,
        "endpoint": endpoint,
        "interval": interval,
        "enabled": 1 if enabled else 0,
        "current": cur or {},
        "uptime": uptime,
    })

# ---- Routes ----
@APP.get("/")
def index():
    # hard fail with a clear error if template missing
    tpl = TEMPLATES_DIR / "index.html"
    if not tpl.exists():
        return f"Missing templates/index.html (looked for {tpl})", 500

    return render_template(
        "index.html",
        targets=merged_targets(),
        bind_host=BIND_HOST,
        bind_port=BIND_PORT,
        ui_version=UI_VERSION,
        copyright_year=COPYRIGHT_YEAR,
        log_lines=LOG_LINES_DEFAULT,
        poll_seconds=STATE_POLL_SECONDS,
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
        text = journalctl_lines(lines)
        src = "journalctl -t interheart -o cat"
        actual = len(text.splitlines()) if text else 0
        return jsonify({"ok": True, "source": src, "lines": actual, "updated": updated, "text": text})
    except Exception as e:
        return jsonify({"ok": False, "source": "journalctl (error)", "lines": 1, "updated": updated, "text": f"(journalctl error: {str(e)})"})

# ---- API: targets ----
@APP.post("/api/add")
def api_add():
    name = request.form.get("name", "").strip()
    ip = request.form.get("ip", "").strip()
    endpoint = request.form.get("endpoint", "").strip()
    interval = request.form.get("interval", "60").strip()
    rc, out = run_cmd(["add", name, ip, endpoint, interval])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/remove")
def api_remove():
    name = request.form.get("name", "").strip()
    rc, out = run_cmd(["remove", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/test")
def api_test():
    name = request.form.get("name", "").strip()
    rc, out = run_cmd(["test", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/enable")
def api_enable():
    name = request.form.get("name", "").strip()
    rc, out = run_cmd(["enable", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/disable")
def api_disable():
    name = request.form.get("name", "").strip()
    rc, out = run_cmd(["disable", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/set-target-interval")
def api_set_target_interval():
    name = request.form.get("name", "").strip()
    sec = request.form.get("seconds", "").strip()
    rc, out = run_cmd(["set-target-interval", name, sec])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.post("/api/edit")
def api_edit():
    old_name = request.form.get("old_name", "").strip()
    new_name = request.form.get("new_name", "").strip()
    ip = request.form.get("ip", "").strip()
    endpoint = request.form.get("endpoint", "").strip()
    interval = request.form.get("interval", "").strip()
    enabled = request.form.get("enabled", "1").strip()
    rc, out = run_cmd(["edit", old_name, new_name, ip, endpoint, interval, enabled])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})

@APP.get("/api/get")
def api_get():
    name = (request.args.get("name") or "").strip()
    if not name:
        return die_json("Missing name", 400)
    rc, out = run_cmd(["get", name])
    # best effort: mask endpoint in a separate field too
    masked = "-"
    m = re.search(r"(https?://\S+)", out or "")
    if m:
        masked = mask_endpoint(m.group(1))
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed"), "endpoint_masked": masked})

# ---- API: run-now (live output tail) ----
@APP.post("/api/run-now")
def api_run_now():
    ensure_state_dir()

    meta = load_run_meta()
    existing_pid = int(meta.get("pid") or 0)
    if existing_pid and pid_is_running(existing_pid):
        return jsonify({"ok": True, "message": "Already running", "pid": existing_pid})

    cmd = [CLI, "run-now"]
    try:
        # truncate output file
        RUN_OUT_FILE.write_text("", encoding="utf-8")
        with open(str(RUN_OUT_FILE), "w", encoding="utf-8") as out_f:
            p = subprocess.Popen(cmd, stdout=out_f, stderr=subprocess.STDOUT, text=True)

        save_run_meta({
            "pid": p.pid,
            "started": int(time.time()),
            "finished": 0,
            "rc": None
        })
        return jsonify({"ok": True, "message": "Started", "pid": p.pid})
    except Exception as e:
        save_run_meta({"pid": 0, "started": 0, "finished": int(time.time()), "rc": 1})
        return jsonify({"ok": False, "message": f"Failed to start run-now: {str(e)}"})

@APP.get("/api/run-status")
def api_run_status():
    meta = load_run_meta()
    pid = int(meta.get("pid") or 0)
    started = int(meta.get("started") or 0)
    finished = int(meta.get("finished") or 0)

    if pid and pid_is_running(pid):
        return jsonify({"running": True, "finished": False, "pid": pid, "started": started})

    if started and not finished:
        meta["finished"] = int(time.time())
        meta["pid"] = 0
        save_run_meta(meta)

    return jsonify({
        "running": False,
        "finished": bool(started),
        "pid": pid,
        "started": started,
        "finished_at": int(meta.get("finished") or 0),
    })

@APP.get("/api/run-output")
def api_run_output():
    # tail last N lines so UI can display progress while running
    try:
        lines = int(request.args.get("lines", "120"))
    except Exception:
        lines = 120
    lines = max(20, min(800, lines))

    try:
        if RUN_OUT_FILE.exists():
            raw = RUN_OUT_FILE.read_text(encoding="utf-8", errors="replace")
        else:
            raw = ""
        arr = raw.splitlines()
        tail = "\n".join(arr[-lines:]) if arr else ""
        summary = parse_run_summary(raw)
        return jsonify({"ok": True, "text": tail, "summary": summary})
    except Exception as e:
        return jsonify({"ok": False, "text": f"(error reading output: {str(e)})", "summary": None})

@APP.get("/api/run-result")
def api_run_result():
    meta = load_run_meta()
    try:
        out = RUN_OUT_FILE.read_text(encoding="utf-8", errors="replace").strip() if RUN_OUT_FILE.exists() else ""
    except Exception:
        out = ""

    summary = parse_run_summary(out)
    ok = True
    if "Unknown command" in out:
        ok = False

    return jsonify({"ok": ok, "message": out or ("OK" if ok else "Failed"), "summary": summary, "meta": meta})

if __name__ == "__main__":
    APP.run(host=BIND_HOST, port=BIND_PORT, threaded=True)
