#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_from_directory, Response
from markupsafe import Markup
import os
import subprocess
import time
import json
import re
import sqlite3

APP = Flask(__name__)

# -----------------------------
# Paths / config
# -----------------------------
CLI = os.environ.get("INTERHEART_CLI", "/usr/local/bin/interheart")

WEBUI_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.environ.get("INTERHEART_DIR", os.path.dirname(WEBUI_DIR))

STATIC_DIR = os.path.join(WEBUI_DIR, "static")

BIND_HOST = os.environ.get("WEBUI_BIND", "0.0.0.0")
BIND_PORT = int(os.environ.get("WEBUI_PORT", "8088"))

COPYRIGHT_YEAR = os.environ.get("WEBUI_COPYRIGHT_YEAR", "2026")

LOG_LINES_DEFAULT = int(os.environ.get("WEBUI_LOG_LINES", "200"))
STATE_POLL_SECONDS = int(os.environ.get("WEBUI_STATE_POLL_SECONDS", "2"))

STATE_DIR = "/var/lib/interheart"
DB_PATH = os.path.join(STATE_DIR, "state.db")

RUNTIME_FILE = os.path.join(STATE_DIR, "runtime.json")
RUN_META_FILE = os.path.join(STATE_DIR, "run_meta.json")
RUN_OUT_FILE = os.path.join(STATE_DIR, "run_last_output.txt")


def read_version() -> str:
    try:
        candidates = [
            os.path.join(REPO_DIR, "VERSION"),
            os.path.join(WEBUI_DIR, "VERSION"),
        ]
        for p in candidates:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    return f.read().strip()
    except Exception:
        pass
    return "0.0.0"


UI_VERSION = read_version()


# -----------------------------
# Helpers
# -----------------------------
def ensure_state_dir():
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        for p in [RUNTIME_FILE, RUN_META_FILE, RUN_OUT_FILE]:
            if not os.path.exists(p):
                with open(p, "w", encoding="utf-8") as f:
                    f.write("")
        # keep permissions readable
        for p in [RUNTIME_FILE, RUN_META_FILE, RUN_OUT_FILE]:
            try:
                os.chmod(p, 0o644)
            except Exception:
                pass
    except Exception:
        pass


ensure_state_dir()


def die_json(msg: str, code: int = 400):
    return jsonify({"ok": False, "message": msg}), code


def run_cmd(args):
    """
    WebUI runs as root via systemd in your setup -> no sudo here.
    """
    cmd = [CLI] + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    return p.returncode, out.strip()


def mask_endpoint(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return "-"
    # scheme://host[:port]/*** (hide path/query)
    try:
        scheme = url.split("://", 1)[0]
        rest = url.split("://", 1)[1] if "://" in url else url
        host = rest.split("/", 1)[0]
        if scheme and host:
            return f"{scheme}://{host}/***"
    except Exception:
        pass
    return "***"


def human_ts(epoch: int) -> str:
    if not epoch or epoch <= 0:
        return "-"
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))
    except Exception:
        return "-"


def db_connect():
    # sqlite file might not exist yet; CLI init-db should create it.
    return sqlite3.connect(DB_PATH)


def fetch_targets_from_db():
    """
    Pull everything we need for UI from sqlite directly:
      - targets table: name, ip, endpoint, interval, enabled
      - runtime table: status, last_ping, last_sent, last_rtt_ms
    """
    if not os.path.exists(DB_PATH):
        return []

    try:
        con = db_connect()
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        # Targets
        cur.execute(
            """
            SELECT name, ip, endpoint, interval, enabled
            FROM targets
            ORDER BY name ASC
            """
        )
        targets = {r["name"]: dict(r) for r in cur.fetchall()}

        # Runtime
        cur.execute(
            """
            SELECT name, status, last_ping, last_sent, last_rtt_ms
            FROM runtime
            """
        )
        runtime = {r["name"]: dict(r) for r in cur.fetchall()}

        out = []
        for name, t in targets.items():
            rt = runtime.get(name, {})
            status = (rt.get("status") or "unknown").strip()
            last_ping = int(rt.get("last_ping") or 0)
            last_sent = int(rt.get("last_sent") or 0)
            last_rtt_ms = int(rt.get("last_rtt_ms") or -1)

            out.append(
                {
                    "name": name,
                    "ip": (t.get("ip") or "").strip(),
                    "interval": int(t.get("interval") or 60),
                    "enabled": int(t.get("enabled") or 0),
                    "endpoint": (t.get("endpoint") or "").strip(),
                    "endpoint_masked": mask_endpoint(t.get("endpoint") or ""),
                    "status": status,
                    "last_ping_epoch": last_ping,
                    "last_sent_epoch": last_sent,
                    "last_ping_human": human_ts(last_ping),
                    "last_response_human": human_ts(last_sent),
                    "last_rtt_ms": last_rtt_ms,
                }
            )

        return out
    except Exception:
        return []
    finally:
        try:
            con.close()
        except Exception:
            pass


def journalctl_lines(lines: int) -> str:
    cmd = ["journalctl", "-t", "interheart", "-n", str(lines), "--no-pager", "--output=cat"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "journalctl failed").strip())
    return (p.stdout or "").strip()


# Run summary parsing (same as old)
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


def load_run_meta():
    try:
        if os.path.exists(RUN_META_FILE):
            raw = open(RUN_META_FILE, "r", encoding="utf-8").read().strip()
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return {}


def save_run_meta(meta: dict):
    ensure_state_dir()
    try:
        with open(RUN_META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        try:
            os.chmod(RUN_META_FILE, 0o644)
        except Exception:
            pass
    except Exception:
        pass


def pid_is_running(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


# -----------------------------
# Static + Index
# -----------------------------
@APP.get("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


@APP.get("/")
def index():
    """
    We keep index.html in /static but still render variables into it.
    """
    path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(path):
        return Response("Missing static/index.html", status=500)

    tpl = open(path, "r", encoding="utf-8").read()

    # render via Flask's Jinja environment
    return APP.jinja_env.from_string(tpl).render(
        ui_version=UI_VERSION,
        copyright_year=COPYRIGHT_YEAR,
        bind_host=BIND_HOST,
        bind_port=BIND_PORT,
        poll_seconds=STATE_POLL_SECONDS,
        log_lines=LOG_LINES_DEFAULT,
    )


# -----------------------------
# Data endpoints used by UI
# -----------------------------
@APP.get("/state")
def state():
    targets = fetch_targets_from_db()
    return jsonify({"updated": int(time.time()), "targets": targets})


@APP.get("/runtime")
def runtime():
    """
    UI polls this rapidly during run-now.
    interheart.sh should update /var/lib/interheart/runtime.json while running.
    If not present, we still return an "idle" structure.
    """
    try:
        if os.path.exists(RUNTIME_FILE):
            raw = open(RUNTIME_FILE, "r", encoding="utf-8").read().strip()
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
        return jsonify(
            {
                "source": "journalctl (error)",
                "lines": 1,
                "updated": updated,
                "text": f"(journalctl error: {str(e)})",
            }
        )


# -----------------------------
# API: run-now realtime
# -----------------------------
@APP.post("/api/run-now")
def api_run_now():
    ensure_state_dir()

    meta = load_run_meta()
    existing_pid = int(meta.get("pid") or 0)
    if existing_pid and pid_is_running(existing_pid):
        return jsonify({"ok": True, "message": "Already running", "pid": existing_pid})

    # mark runtime quickly so UI instantly shows "running"
    try:
        with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
            json.dump({"status": "running", "current": "", "done": 0, "due": 0, "updated": int(time.time())}, f)
        try:
            os.chmod(RUNTIME_FILE, 0o644)
        except Exception:
            pass
    except Exception:
        pass

    cmd = [CLI, "run-now"]
    try:
        with open(RUN_OUT_FILE, "w", encoding="utf-8") as out_f:
            p = subprocess.Popen(cmd, stdout=out_f, stderr=subprocess.STDOUT, text=True)
        save_run_meta({"pid": p.pid, "started": int(time.time()), "finished": 0, "rc": None})
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

    return jsonify(
        {
            "running": False,
            "finished": bool(started),
            "pid": pid,
            "started": started,
            "finished_at": int(meta.get("finished") or 0),
        }
    )


@APP.get("/api/run-result")
def api_run_result():
    meta = load_run_meta()
    try:
        out = open(RUN_OUT_FILE, "r", encoding="utf-8").read().strip() if os.path.exists(RUN_OUT_FILE) else ""
    except Exception:
        out = ""

    summary = parse_run_summary(out)
    ok = True
    if "Unknown command" in out or ("ERROR" in out and not out.startswith("OK:")):
        ok = False

    return jsonify({"ok": ok, "message": out or ("OK" if ok else "Failed"), "summary": summary, "meta": meta})


# -----------------------------
# API: targets
# -----------------------------
@APP.post("/api/add")
def api_add():
    name = (request.form.get("name") or "").strip()
    ip = (request.form.get("ip") or "").strip()
    endpoint = (request.form.get("endpoint") or "").strip()
    interval = (request.form.get("interval") or "60").strip()

    if not name or not ip or not endpoint:
        return die_json("Missing required fields (name, ip, endpoint)")

    rc, out = run_cmd(["add", name, ip, endpoint, interval])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})


@APP.post("/api/remove")
def api_remove():
    name = (request.form.get("name") or "").strip()
    if not name:
        return die_json("Missing name")
    rc, out = run_cmd(["remove", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})


@APP.post("/api/test")
def api_test():
    name = (request.form.get("name") or "").strip()
    if not name:
        return die_json("Missing name")
    rc, out = run_cmd(["test", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})


@APP.post("/api/set-target-interval")
def api_set_target_interval():
    name = (request.form.get("name") or "").strip()
    sec = (request.form.get("seconds") or "").strip()
    if not name or not sec:
        return die_json("Missing name or seconds")
    rc, out = run_cmd(["set-target-interval", name, sec])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})


@APP.post("/api/disable")
def api_disable():
    name = (request.form.get("name") or "").strip()
    if not name:
        return die_json("Missing name")
    rc, out = run_cmd(["disable", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})


@APP.post("/api/enable")
def api_enable():
    name = (request.form.get("name") or "").strip()
    if not name:
        return die_json("Missing name")
    rc, out = run_cmd(["enable", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})


@APP.post("/api/edit")
def api_edit():
    """
    Expected from UI:
      old_name, new_name, ip, endpoint, interval, enabled(0|1)
    """
    old_name = (request.form.get("old_name") or "").strip()
    new_name = (request.form.get("new_name") or "").strip()
    ip = (request.form.get("ip") or "").strip()
    endpoint = (request.form.get("endpoint") or "").strip()
    interval = (request.form.get("interval") or "").strip()
    enabled = (request.form.get("enabled") or "").strip()

    if not old_name or not new_name or not ip or not endpoint or not interval or enabled not in ("0", "1"):
        return die_json("Missing or invalid fields for edit")

    rc, out = run_cmd(["edit", old_name, new_name, ip, endpoint, interval, enabled])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})


# Optional: details endpoint if you want it later (UI can use /state today)
@APP.get("/api/get")
def api_get():
    name = (request.args.get("name") or "").strip()
    if not name:
        return die_json("Missing name")
    rc, out = run_cmd(["get", name])
    return jsonify({"ok": rc == 0, "message": out or ("OK" if rc == 0 else "Failed")})


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    # For local testing (systemd runs it anyway)
    APP.run(host=BIND_HOST, port=BIND_PORT, threaded=True)
