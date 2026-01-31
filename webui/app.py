#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template, Response, send_file
import os
import sys
import subprocess
import time
import json
import re
import socket
import datetime
import logging
import signal
import shutil
import ipaddress
import threading
import concurrent.futures
from io import BytesIO
from pathlib import Path
import sqlite3

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

# WebUI debug log (backend) – helpful when the UI appears empty on first load.
WEBUI_DEBUG_FILE = STATE_DIR / "webui_debug.log"
WEBUI_DEBUG_ENABLED = os.environ.get("INTERHEART_WEBUI_DEBUG", "1").strip() not in ("0", "false", "no")
_LAST_DEBUG_TS = 0

SCAN_META_FILE = STATE_DIR / "scan_meta.json"
SCAN_OUT_FILE = STATE_DIR / "scan_last_output.txt"

# New network discovery (nmap-only, realtime)
DISCOVERY_META_FILE = STATE_DIR / "discovery_meta.json"
DISCOVERY_EVENTS_FILE = STATE_DIR / "discovery_events.jsonl"

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
        for p in (RUN_META_FILE, RUN_OUT_FILE, SCAN_META_FILE, SCAN_OUT_FILE, DISCOVERY_META_FILE, DISCOVERY_EVENTS_FILE):
            if not p.exists():
                p.write_text("", encoding="utf-8")
                try:
                    os.chmod(str(p), 0o644)
                except Exception:
                    pass
    except Exception:
        pass

ensure_state_dir()

# Ensure Flask logger is usable under systemd (stdout/stderr -> journal)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def _debug_log(msg: str, force: bool = False):
    """Write a debug line to journal + a persistent file.

    We only log when something looks off, or when explicitly forced (e.g. via /api/debug-state).
    This avoids spamming the journal every 2 seconds (the UI polls /state).
    """
    global _LAST_DEBUG_TS
    if not WEBUI_DEBUG_ENABLED:
        return
    now = int(time.time())
    # throttle to max 1 line / 3 seconds unless forced
    if not force and (now - _LAST_DEBUG_TS) < 3:
        return
    _LAST_DEBUG_TS = now

    line = f"[webui] {msg}"
    try:
        APP.logger.info(line)
    except Exception:
        try:
            print(line, flush=True)
        except Exception:
            pass
    try:
        ensure_state_dir()
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        WEBUI_DEBUG_FILE.open("a", encoding="utf-8").write(f"{ts} {line}\n")
    except Exception:
        pass

def die_json(msg: str, code: int = 500):
    return jsonify({"ok": False, "message": msg}), code


@APP.errorhandler(Exception)
def _handle_all_errors(err):
    """Return JSON for API routes so the frontend doesn't explode on HTML errors."""
    try:
        if request and request.path and request.path.startswith("/api/"):
            code = getattr(err, "code", 500)
            return jsonify({"ok": False, "message": str(err)}), code
    except Exception:
        pass
    # fall back to default Flask handler
    raise err

def run_cmd(args):
    cmd = [CLI] + args
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    merged = out + (("\n" + err) if err else "")
    return p.returncode, merged.strip()

def journalctl_lines(lines: int) -> str:
    cmd = ["journalctl", "-t", "interheart", "-n", str(lines), "--no-pager", "--output=short-iso"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "journalctl failed").strip())

    raw = (p.stdout or "").splitlines()
    out_lines = []
    rx = re.compile(r"^(\d{4}-\d{2}-\d{2}T\S+)\s+\S+\s+interheart\[\d+\]:\s*(.*)$")
    for line in raw:
        line = line.rstrip()
        m = rx.match(line)
        if m:
            out_lines.append(f"{m.group(1)} {m.group(2)}")
        else:
            out_lines.append(line)
    return "\n".join(out_lines).strip()

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
        # If it's a zombie (defunct) we should NOT treat it as running.
        # This matters because the WebUI starts the CLI via Popen without
        # always immediately reaping it, which can leave a zombie process
        # behind. `kill(pid, 0)` will still succeed for zombies.
        try:
            stat = Path(f"/proc/{pid}/stat")
            if stat.exists():
                content = stat.read_text(encoding="utf-8", errors="replace")
                # /proc/<pid>/stat: pid (comm) state ...
                # state is the 3rd field. e.g. 'Z' for zombie.
                parts = content.split()
                if len(parts) >= 3 and parts[2] == "Z":
                    return False
        except Exception:
            pass
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

def load_discovery_meta() -> dict:
    try:
        if DISCOVERY_META_FILE.exists():
            raw = DISCOVERY_META_FILE.read_text(encoding="utf-8").strip()
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return {}


def save_discovery_meta(meta: dict):
    ensure_state_dir()
    try:
        DISCOVERY_META_FILE.write_text(json.dumps(meta), encoding="utf-8")
        try:
            os.chmod(str(DISCOVERY_META_FILE), 0o644)
        except Exception:
            pass
    except Exception:
        pass


def _append_discovery_event(obj: dict):
    """Append a JSONL event for SSE streaming."""
    ensure_state_dir()
    try:
        with open(DISCOVERY_EVENTS_FILE, "a", encoding="utf-8", errors="replace") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        pass


def load_scan_meta() -> dict:
    try:
        if SCAN_META_FILE.exists():
            raw = SCAN_META_FILE.read_text(encoding="utf-8").strip()
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return {}

def save_scan_meta(meta: dict):
    ensure_state_dir()
    try:
        SCAN_META_FILE.write_text(json.dumps(meta), encoding="utf-8")
        try:
            os.chmod(str(SCAN_META_FILE), 0o644)
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
    """Parse `interheart list` output.

    The CLI prints a simple fixed-width table:
      NAME IP INTERVAL ENABLED ENDPOINT
      ---------------- ...
      <rows>

    Older versions printed a long dashed separator line; we tolerate both.
    """
    targets = []
    saw_header = False
    for raw in (list_output or "").splitlines():
        line = (raw or "").rstrip("\n").rstrip()
        if not line.strip():
            continue

        # Header line
        if line.strip().startswith("NAME"):
            saw_header = True
            continue

        # Separator line (either long or column dashes)
        if set(line.strip()) == {"-"} or line.strip().startswith("----------------"):
            saw_header = True
            continue

        # If the CLI prints any preamble before the table, ignore until header seen.
        if not saw_header:
            continue

        parts = line.split()
        if len(parts) < 5:
            continue

        name = parts[0]
        ip = parts[1]

        interval_raw = parts[2]
        enabled_raw = parts[3]
        endpoint_masked = " ".join(parts[4:])

        interval = 60
        if interval_raw.endswith("s") and interval_raw[:-1].isdigit():
            interval = int(interval_raw[:-1])
        elif interval_raw.isdigit():
            interval = int(interval_raw)

        enabled = 1 if str(enabled_raw).strip() == "1" else 0

        targets.append({
            "name": name,
            "ip": ip,
            "interval": interval,
            "enabled": enabled,
            "endpoint_masked": endpoint_masked or "***",
            "snapshots": compute_snapshots(DB_PATH, name, enabled, days=3),
        })

    return targets

def parse_status(status_output: str):
    """Parse `interheart status` output.

    Current CLI prints:
      NAME STATUS PING RESP LAT(ms) NEXT_DUE
      <rows>

    Older formats had a long separator line; we tolerate both.
    """
    state = {}
    saw_header = False
    for raw in (status_output or "").splitlines():
        line = (raw or "").rstrip("\n").rstrip()
        if not line.strip():
            continue

        if line.strip().startswith("NAME"):
            saw_header = True
            continue

        if set(line.strip()) == {"-"} or line.strip().startswith("----------------"):
            saw_header = True
            continue

        if not saw_header:
            continue

        parts = line.split()
        # Expected columns from CLI `status`:
        # NAME STATUS PING RESP LAT(ms) NEXT_DUE
        if len(parts) < 6:
            continue

        name = parts[0]
        status = parts[1]
        last_ping = parts[2]
        last_sent = parts[3]
        lat_ms = parts[4]

        state[name] = {
            "status": status,
            "last_ping_epoch": int(last_ping) if str(last_ping).isdigit() else 0,
            "last_sent_epoch": int(last_sent) if str(last_sent).isdigit() else 0,
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
    rc_list, list_out = run_cmd(["list"])
    targets = parse_list_targets(list_out)

    rc_st, st_out = run_cmd(["status"])
    state = parse_status(st_out)

    merged = []
    for t in targets:
        st = state.get(t["name"], {})
        status = st.get("status", "unknown")
        # When a target has just been enabled, the DB may still contain last_status='disabled'
        # until the first run updates it. Treat that as STARTING so the UI does not flip to DISABLED.
        if int(t.get("enabled") or 0) == 1 and str(status).lower() == "disabled":
            status = "starting"
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
            "snapshots": t.get("snapshots") or [],
        })
        # Default sort: IP ascending
    def ip_key(ip: str):
        try:
            a,b,c,d = [int(x) for x in (ip or "0.0.0.0").split(".")]
            return (a,b,c,d)
        except Exception:
            return (999,999,999,999)

    merged.sort(key=lambda x: ip_key(x.get("ip")))
    return merged


# ---- state caching (avoid wiping the UI on transient CLI/DB lock errors) ----
_LAST_STATE_CACHE = {"updated": 0, "targets": []}

def merged_targets_safe():
    """Return merged targets, preferring direct SQLite reads.

    We previously depended on parsing CLI output (list/status). That turned out
    to be fragile across CLI format changes and could cause the WebUI to show
    an empty table until a "Run now" happened.

    This function reads from /var/lib/interheart/state.db directly.
    If the DB is temporarily locked (e.g. while a run updates), we serve the
    last known good cached state instead of wiping the UI.
    """
    global _LAST_STATE_CACHE

    # Prefer DB-backed state
    ok, rows = db_read_targets(DB_PATH)
    if ok and rows is not None:
        # Edge case:
        # The DB can exist but contain 0 rows in `targets` (e.g. state.db created,
        # but targets were not imported/populated yet). In that situation the UI
        # must not wipe the table on first load; we fall back to CLI if CLI has
        # targets.
        if len(rows) == 0:
            try:
                rc_list, list_out = run_cmd(["list"])
                if rc_list == 0:
                    cli_targets = parse_list_targets(list_out)
                    if cli_targets:
                        rc_st, st_out = run_cmd(["status"])
                        state = parse_status(st_out) if rc_st == 0 else {}
                        merged = []
                        for t in cli_targets:
                            st = state.get(t["name"], {})
                            status = st.get("status", "unknown")
                            if int(t.get("enabled") or 0) == 1 and str(status).lower() == "disabled":
                                status = "starting"
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
                                "endpoint_masked": t.get("endpoint_masked") or "-",
                                "snapshots": t.get("snapshots") or [],
                            })
                        _LAST_STATE_CACHE = {"updated": int(time.time()), "targets": merged}
                        return True, merged
            except Exception:
                # If CLI fallback fails, continue with DB rows (empty)
                pass

        _LAST_STATE_CACHE = {"updated": int(time.time()), "targets": rows}
        return True, rows

    # If DB read failed, serve cache if available
    if _LAST_STATE_CACHE.get("targets"):
        return False, _LAST_STATE_CACHE.get("targets")

    # Last resort: fall back to CLI parsing for fresh installs
    try:
        rc_list, list_out = run_cmd(["list"])
        rc_st, st_out = run_cmd(["status"])
        if rc_list != 0 or rc_st != 0:
            return False, []
        targets = parse_list_targets(list_out)
        state = parse_status(st_out)
        merged = []
        for t in targets:
            st = state.get(t["name"], {})
            status = st.get("status", "unknown")
            if int(t.get("enabled") or 0) == 1 and str(status).lower() == "disabled":
                status = "starting"
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
                "endpoint_masked": t.get("endpoint_masked") or "-",
                "snapshots": t.get("snapshots") or [],
            })
        _LAST_STATE_CACHE = {"updated": int(time.time()), "targets": merged}
        return True, merged
    except Exception:
        return False, []


def db_read_targets(db_path: Path):
    """Read targets + state directly from SQLite.

    Returns (ok, targets). ok=False on transient errors (locked/unavailable).
    """
    import sqlite3
    # If the DB is missing (fresh install / not yet run), fall back to CLI.
    # Returning an empty list here causes the UI to render an empty table
    # until the first "Run now" creates/populates the DB.
    if not db_path.exists():
        return False, None
    try:
        con = sqlite3.connect(str(db_path), timeout=2.0)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA busy_timeout=2000;")
        except Exception:
            pass
        cur = con.cursor()
        cur.execute(
            """
            SELECT
              t.name,
              t.ip,
              t.endpoint,
              t.interval,
              t.enabled,
              COALESCE(r.status, 'unknown') AS last_status,
              COALESCE(r.last_ping, 0) AS last_ping,
              COALESCE(r.last_sent, 0) AS last_response,
              COALESCE(r.last_rtt_ms, -1) AS last_latency
            FROM targets t
            LEFT JOIN runtime r ON r.name = t.name
            ORDER BY t.ip ASC;
            """
        )
        rows = cur.fetchall() or []

        out = []
        for r in rows:
            enabled = int(r["enabled"] or 0)
            status = (r["last_status"] or "unknown")

            # UI rules:
            # - enabled=0 => DISABLED
            # - enabled=1 + status unknown => STARTING.. until first up/down
            if enabled != 1:
                status = "disabled"
            else:
                if str(status).lower() in ("unknown", ""):
                    status = "starting"
                if str(status).lower() == "disabled":
                    status = "starting"

            last_ping_epoch = _safe_int(r["last_ping"], 0)
            last_resp_epoch = _safe_int(r["last_response"], 0)
            last_rtt_ms = _safe_int(r["last_latency"], -1)

            out.append({
                "name": r["name"],
                "ip": r["ip"],
                "interval": _safe_int(r["interval"], 60),
                "status": str(status),
                "enabled": enabled,
                "last_ping_human": human_ts(last_ping_epoch),
                "last_response_human": human_ts(last_resp_epoch),
                "last_ping_epoch": last_ping_epoch,
                "last_response_epoch": last_resp_epoch,
                "last_rtt_ms": last_rtt_ms,
                "endpoint_masked": mask_endpoint(r["endpoint"] or ""),
                "snapshots": compute_snapshots(db_path, r["name"], enabled, days=3),
            })

        return True, out
    except Exception:
        return False, None
    finally:
        try:
            con.close()
        except Exception:
            pass


# ---- API: info (DB-backed, uses history samples if present) ----
def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


def compute_snapshots(db_path: Path, name: str, enabled_now: int, days: int = 3):
    """Return list of {day, state, label} for the last N days (including today).

    States:
      - green: mostly OK
      - yellow: had a down streak >=60s
      - red: down all samples that day
      - gray: no samples and disabled
      - unknown: no samples and enabled

    Heuristic, based on history samples.
    """
    import sqlite3
    import datetime

    if not db_path.exists():
        return []

    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='history' LIMIT 1;")
        if not cur.fetchone():
            return []

        today = datetime.date.fromtimestamp(int(time.time()))
        out = []
        for di in range(days-1, -1, -1):
            day = today - datetime.timedelta(days=di)
            start = int(datetime.datetime.combine(day, datetime.time.min).timestamp())
            end = int(datetime.datetime.combine(day, datetime.time.max).timestamp())
            cur.execute(
                "SELECT ts, status FROM history WHERE name=? AND ts>=? AND ts<=? ORDER BY ts ASC;",
                (name, start, end),
            )
            rows = cur.fetchall()
            if not rows:
                if enabled_now != 1:
                    out.append({"day": day.isoformat(), "state": "gray", "label": f"{day.strftime('%a')} • disabled"})
                else:
                    out.append({"day": day.isoformat(), "state": "unknown", "label": f"{day.strftime('%a')} • no data"})
                continue

            statuses = [r['status'] for r in rows]
            has_up = any(s == 'up' for s in statuses)
            has_down = any(s == 'down' for s in statuses)

            if has_down and not has_up:
                out.append({"day": day.isoformat(), "state": "red", "label": f"{day.strftime('%a')} • down"})
                continue

            # find any down streak >=60s
            streak_start = None
            worst = 0
            for r in rows:
                if r['status'] == 'down':
                    if streak_start is None:
                        streak_start = r['ts']
                    worst = max(worst, int(r['ts']) - int(streak_start))
                else:
                    streak_start = None
            if worst >= 60:
                out.append({"day": day.isoformat(), "state": "yellow", "label": f"{day.strftime('%a')} • degraded"})
            else:
                out.append({"day": day.isoformat(), "state": "green", "label": f"{day.strftime('%a')} • ok"})

        return out
    except Exception:
        return []


def _midnight_ts_local(ts: float) -> int:
    dt = datetime.datetime.fromtimestamp(ts)
    dt0 = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(dt0.timestamp())


def compute_uptime_stats(db_path: Path, name: str, days: int):
    """
    Uptime aligned to local midnight.

    Window: [start_midnight, now)
    - 24h => today (midnight -> now)
    - 7d/30d/90d => from midnight N-1 days ago -> now

    Returns None until at least 1 hour has passed since the window start.
    Also returns a small "series" list for the striped history view:
      - "up"  (green)
      - "hb"  (yellow, heartbeat failed)
      - "down" (red, not responding)
    """
    import sqlite3

    if not db_path.exists():
        return None

    now = time.time()
    start_midnight = _midnight_ts_local(now)
    start = start_midnight - int((max(1, days) - 1) * 86400)

    if now - start < 3600:
        return None

    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='history' LIMIT 1;")
        if not cur.fetchone():
            return None

        cur.execute(
            """
            SELECT
              SUM(CASE WHEN status='up' THEN 1 ELSE 0 END) AS ok_cnt,
              SUM(CASE WHEN status='down' AND rtt_ms >= 0 THEN 1 ELSE 0 END) AS hb_cnt,
              SUM(CASE WHEN status='down' AND (rtt_ms < 0 OR rtt_ms IS NULL) THEN 1 ELSE 0 END) AS down_cnt,
              AVG(CASE WHEN rtt_ms >= 0 THEN rtt_ms ELSE NULL END) AS avg_rtt
            FROM history
            WHERE name=? AND ts>=? AND ts<? AND status IN ('up','down');
            """,
            (name, int(start), int(now)),
        )
        row = cur.fetchone()
        ok_cnt = _safe_int(row["ok_cnt"], 0)
        hb_cnt = _safe_int(row["hb_cnt"], 0)
        down_cnt = _safe_int(row["down_cnt"], 0)
        samples = ok_cnt + hb_cnt + down_cnt
        if samples <= 0:
            return None

        pct = round((ok_cnt / samples) * 100.0, 2)
        avg_rtt = row["avg_rtt"]
        avg_rtt_ms = int(round(avg_rtt)) if avg_rtt is not None else None

        cur.execute(
            """
            SELECT ts, status, rtt_ms
            FROM history
            WHERE name=? AND ts>=? AND ts<? AND status IN ('up','down')
            ORDER BY ts DESC
            LIMIT 200;
            """,
            (name, int(start), int(now)),
        )
        rows = cur.fetchall() or []
        series = []
        for r in reversed(rows):
            st = (r["status"] or "").lower()
            rtt = r["rtt_ms"]
            if st == "up":
                series.append("up")
            else:
                try:
                    rttn = float(rtt)
                except Exception:
                    rttn = None
                if rttn is not None and rttn >= 0:
                    series.append("hb")
                else:
                    series.append("down")

        return {
            "samples": samples,
            "pct": pct,
            "avg_rtt_ms": avg_rtt_ms,
            "series": series,
        }
    except Exception:
        return None
    finally:
        try:
            con.close()
        except Exception:
            pass

# ---- Routes ----
@APP.get("/")
def index():
    # hard fail with a clear error if template missing
    tpl = TEMPLATES_DIR / "index.html"
    if not tpl.exists():
        return f"Missing templates/index.html (looked for {tpl})", 500

    ok, targets = merged_targets_safe()
    return render_template(
        "index.html",
        targets=targets,
        bind_host=BIND_HOST,
        bind_port=BIND_PORT,
        ui_version=UI_VERSION,
        copyright_year=COPYRIGHT_YEAR,
        log_lines=LOG_LINES_DEFAULT,
        poll_seconds=STATE_POLL_SECONDS,
        state_ok=ok,
    )

@APP.get("/state")
def state():
    ok, targets = merged_targets_safe()
    # Detect the common "rows flash then disappear" symptom:
    # - server-rendered table has rows
    # - first /state poll returns 0 targets
    if targets is not None and len(targets) == 0:
        db_exists = DB_PATH.exists()
        db_size = DB_PATH.stat().st_size if db_exists else 0
        # Try a lightweight CLI check (non-fatal)
        cli_rc, cli_out = run_cmd(["list"])
        cli_cnt = len(parse_list_targets(cli_out)) if cli_rc == 0 else -1
        _debug_log(
            f"/state returned 0 targets (ok={ok}) | db_exists={db_exists} db_size={db_size} | cli_list_rc={cli_rc} cli_targets={cli_cnt} | cwd={os.getcwd()} cli={CLI}",
            force=False,
        )
    return jsonify({"ok": ok, "updated": int(time.time()), "targets": targets})


@APP.get("/api/debug-state")
def api_debug_state():
    """Return extra backend diagnostics for troubleshooting empty tables.

    This endpoint is not polled by the UI; it's intended for manual use:
      curl -s http://<host>:8088/api/debug-state | jq
    """
    ok, targets = merged_targets_safe()
    db_exists = DB_PATH.exists()
    db_size = DB_PATH.stat().st_size if db_exists else 0
    cache_cnt = len((_LAST_STATE_CACHE.get("targets") or []))

    cli_list_rc, cli_list_out = run_cmd(["list"])
    cli_targets = parse_list_targets(cli_list_out) if cli_list_rc == 0 else []
    cli_cnt = len(cli_targets)

    cli_status_rc, cli_status_out = run_cmd(["status"])
    status_map = parse_status(cli_status_out) if cli_status_rc == 0 else {}

    diag = {
        "ok": ok,
        "targets_count": len(targets or []),
        "db": {"path": str(DB_PATH), "exists": db_exists, "size": db_size},
        "cli": {
            "path": str(CLI),
            "list_rc": cli_list_rc,
            "list_count": cli_cnt,
            "status_rc": cli_status_rc,
            "status_count": len(status_map),
        },
        "cache": {"count": cache_cnt, "updated": int(_LAST_STATE_CACHE.get("updated") or 0)},
        "env": {"cwd": os.getcwd(), "uid": os.getuid() if hasattr(os, "getuid") else None},
        "updated": int(time.time()),
    }

    _debug_log(
        f"/api/debug-state: ok={ok} targets={len(targets or [])} db_exists={db_exists} db_size={db_size} cli_list_rc={cli_list_rc} cli_targets={cli_cnt} cache={cache_cnt}",
        force=True,
    )
    return jsonify({"ok": True, "diag": diag, "targets": targets})

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
        src = "journalctl -t interheart -o short-iso"
        actual = len(text.splitlines()) if text else 0
        return jsonify({"ok": True, "source": src, "lines": actual, "updated": updated, "text": text})
    except Exception as e:
        return jsonify({"ok": False, "source": "journalctl (error)", "lines": 1, "updated": updated, "text": f"(journalctl error: {str(e)})"})


def filter_log_text(text: str, q: str = "", level: str = "all") -> list[str]:
    q = (q or "").strip().lower()
    level = (level or "all").strip().lower()
    lines = (text or "").splitlines()

    def level_ok(line: str) -> bool:
        ll = line.lower()
        if level == "all":
            return True
        if level == "error":
            return ("error" in ll) or ("fail" in ll)
        if level == "warn":
            return ("warn" in ll) or ("warning" in ll)
        if level == "info":
            return not (("error" in ll) or ("fail" in ll) or ("warn" in ll) or ("warning" in ll))
        return True

    out = []
    for l in lines:
        if not level_ok(l):
            continue
        if q and q not in l.lower():
            continue
        out.append(l)
    return out


@APP.get("/api/logs-export")
def api_logs_export():
    fmt = (request.args.get("fmt") or "csv").strip().lower()
    try:
        lines_n = int(request.args.get("lines", str(LOG_LINES_DEFAULT)))
    except Exception:
        lines_n = LOG_LINES_DEFAULT
    lines_n = max(50, min(5000, lines_n))
    q = (request.args.get("q") or "").strip()
    level = (request.args.get("level") or "all").strip().lower()

    text = journalctl_lines(lines_n)
    lines = filter_log_text(text, q=q, level=level)

    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime(int(time.time())))
    base = f"interheart-logs-{ts}"

    if fmt == "csv":
        csv_text = "line\n" + "\n".join([json.dumps(l)[1:-1] for l in lines])
        return Response(csv_text, mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={base}.csv"})

    if fmt == "xlsx":
        try:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "Logs"
            ws.append(["line"])
            for l in lines:
                ws.append([l])
            bio = BytesIO()
            wb.save(bio)
            bio.seek(0)
            return send_file(bio, as_attachment=True, download_name=f"{base}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            return die_json(f"XLSX export failed: {e}", 500)

    if fmt == "pdf":
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            bio = BytesIO()
            c = canvas.Canvas(bio, pagesize=letter)
            width, height = letter
            def draw_header_footer():
                # Header
                c.setFont("Helvetica-Bold", 10)
                c.drawString(40, height - 38, "interheart – logs")
                c.setFont("Helvetica", 8)
                c.drawRightString(width - 40, height - 38, ts)
                # Footer (branding)
                c.setFont("Helvetica", 8)
                c.setFillColorRGB(0.6, 0.6, 0.6)
                c.drawString(40, 24, "Powered by 5echo.io")
                c.drawRightString(width - 40, 24, f"Page {c.getPageNumber()}")
                c.setFillColorRGB(0, 0, 0)

            draw_header_footer()
            y = height - 60
            c.setFont("Helvetica", 8)
            for l in lines:
                if y < 40:
                    c.showPage()
                    draw_header_footer()
                    y = height - 60
                    c.setFont("Helvetica", 8)
                # trim to fit
                s = l
                if len(s) > 160:
                    s = s[:157] + "..."
                c.drawString(40, y, s)
                y -= 12
            c.save()
            bio.seek(0)
            return send_file(bio, as_attachment=True, download_name=f"{base}.pdf", mimetype="application/pdf")
        except Exception as e:
            return die_json(f"PDF export failed: {e}", 500)

    return die_json("Unknown format", 400)

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


def bulk_from_json() -> list[str]:
    try:
        payload = request.get_json(force=True, silent=True) or {}
        names = payload.get("names") or []
        if not isinstance(names, list):
            return []
        return [str(n).strip() for n in names if str(n).strip()]
    except Exception:
        return []


@APP.post("/api/bulk-enable")
def api_bulk_enable():
    names = bulk_from_json()
    if not names:
        return jsonify({"ok": False, "message": "No targets selected"})
    ok = 0
    for n in names:
        rc, _ = run_cmd(["enable", n])
        if rc == 0:
            ok += 1
    return jsonify({"ok": ok == len(names), "message": f"Enabled {ok}/{len(names)}"})


@APP.post("/api/bulk-disable")
def api_bulk_disable():
    names = bulk_from_json()
    if not names:
        return jsonify({"ok": False, "message": "No targets selected"})
    ok = 0
    for n in names:
        rc, _ = run_cmd(["disable", n])
        if rc == 0:
            ok += 1
    return jsonify({"ok": ok == len(names), "message": f"Disabled {ok}/{len(names)}"})


@APP.post("/api/bulk-test")
def api_bulk_test():
    names = bulk_from_json()
    if not names:
        return jsonify({"ok": False, "message": "No targets selected"})
    ok = 0
    for n in names:
        rc, _ = run_cmd(["test", n])
        if rc == 0:
            ok += 1
    return jsonify({"ok": True, "message": f"Tested {len(names)} targets"})


@APP.post("/api/bulk-remove")
def api_bulk_remove():
    names = bulk_from_json()
    if not names:
        return jsonify({"ok": False, "message": "No targets selected"})
    ok = 0
    for n in names:
        rc, _ = run_cmd(["remove", n])
        if rc == 0:
            ok += 1
    return jsonify({"ok": ok == len(names), "message": f"Removed {ok}/{len(names)}"})

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


@APP.get("/api/info")
def api_info():
    """Return structured target info for the Information + Edit modals.

    This is DB-backed (SQLite) to avoid depending on CLI output format.
    """
    import sqlite3

    name = (request.args.get("name") or "").strip()
    if not name:
        return die_json("Missing name", 400)

    if not DB_PATH.exists():
        return die_json("Database not found", 404)

    try:
        con = sqlite3.connect(str(DB_PATH), timeout=2.0)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA busy_timeout=2000;")
        except Exception:
            pass

        cur = con.cursor()
        cur.execute(
            """
            SELECT
              t.name,
              t.ip,
              t.endpoint,
              t.interval,
              t.enabled,
              COALESCE(r.status, 'unknown') AS last_status,
              COALESCE(r.last_ping, 0) AS last_ping,
              COALESCE(r.last_sent, 0) AS last_response,
              COALESCE(r.last_rtt_ms, -1) AS last_latency
            FROM targets t
            LEFT JOIN runtime r ON r.name = t.name
            WHERE t.name = ?
            LIMIT 1;
            """,
            (name,),
        )
        row = cur.fetchone()
        if not row:
            return die_json("Target not found", 404)

        enabled = int(row["enabled"] or 0)
        status = (row["last_status"] or "unknown")

        if enabled != 1:
            status = "disabled"
        else:
            if str(status).lower() in ("unknown", ""):
                status = "starting"
            if str(status).lower() == "disabled":
                status = "starting"

        last_ping_epoch = _safe_int(row["last_ping"], 0)
        last_resp_epoch = _safe_int(row["last_response"], 0)
        last_rtt_ms = _safe_int(row["last_latency"], -1)

        uptime = {
            "24h": compute_uptime_stats(DB_PATH, name, 1),
            "7d": compute_uptime_stats(DB_PATH, name, 7),
            "30d": compute_uptime_stats(DB_PATH, name, 30),
            "90d": compute_uptime_stats(DB_PATH, name, 90),
        }

        return jsonify({
            "ok": True,
            "name": row["name"],
            "ip": row["ip"],
            "endpoint": row["endpoint"],
            "endpoint_masked": mask_endpoint(row["endpoint"] or ""),
            "interval": _safe_int(row["interval"], 60),
            "enabled": True if enabled == 1 else False,
            "current": {
                "status": str(status),
                "last_ping_epoch": last_ping_epoch,
                "last_response_epoch": last_resp_epoch,
                "last_ping_human": human_ts(last_ping_epoch),
                "last_response_human": human_ts(last_resp_epoch),
                "last_rtt_ms": last_rtt_ms,
            },
            "uptime": uptime,
        })
    except Exception as e:
        return die_json(f"Failed to read info: {e}", 500)
    finally:
        try:
            con.close()
        except Exception:
            pass


# ---- API: name suggestion (reverse DNS best-effort) ----
@APP.get("/api/name-suggest")
def api_name_suggest():
    ip = (request.args.get("ip") or "").strip()
    if not ip:
        return jsonify({"ok": False, "name": ""})
    name = ""
    try:
        # reverse DNS
        name = socket.gethostbyaddr(ip)[0]
    except Exception:
        name = ""
    # keep it short / UI friendly
    if name:
        name = name.strip().split(".")[0]
    return jsonify({"ok": True, "name": name})

# ---- API: run-now (live output tail) ----
@APP.post("/api/run-now")
def api_run_now():
    ensure_state_dir()

    meta = load_run_meta()
    existing_pid = int(meta.get("pid") or 0)
    if existing_pid and pid_is_running(existing_pid):
        return jsonify({"ok": True, "message": "Already running", "pid": existing_pid})

    cmd = [CLI, "run-now", "--force"]
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

    # Reap finished child process (prevents zombie PID from looking "running" forever)
    if pid:
        try:
            wp, status = os.waitpid(pid, os.WNOHANG)
            if wp == pid and wp != 0:
                # Child finished
                meta["rc"] = int(os.WEXITSTATUS(status)) if os.WIFEXITED(status) else 1
                meta["finished"] = int(time.time())
                meta["pid"] = 0
                save_run_meta(meta)
                pid = 0
        except ChildProcessError:
            # Not our child (e.g. after restart). We'll fall back to /proc checks.
            pass
        except Exception:
            pass

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
        raw = RUN_OUT_FILE.read_text(encoding="utf-8", errors="replace") if RUN_OUT_FILE.exists() else ""
        arr = raw.splitlines()
        tail = "\n".join(arr[-lines:]) if arr else ""
        summary = parse_run_summary(raw)

        # Progress: count distinct targets completed based on "run:" lines
        done_names = []
        for ln in arr:
            if ln.startswith("run:"):
                parts = ln.split()
                if len(parts) >= 2:
                    done_names.append(parts[1])
        done = len(set(done_names))
        last_line = arr[-1] if arr else ""

        return jsonify({"ok": True, "text": tail, "summary": summary, "done": done, "last_line": last_line})
    except Exception as e:
        return jsonify({"ok": False, "text": f"(error reading output: {str(e)})", "summary": None, "done": 0, "last_line": ""})

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


# ---- API: network scan ----
def _get_local_cidrs(prefer_iface: str | None = None) -> list[str]:
    """Best-effort list of CIDRs to scan.

    Strategy:
    - Prefer directly configured interface networks (ip -j addr).
    - Add routed RFC1918 networks from `ip -j route` (but avoid huge ranges like /8).

    This keeps scans useful on environments where hosts live behind VLAN gateways.
    """
    cidrs: list[str] = []

    # 1) Interface subnets
    try:
        j = subprocess.check_output(["ip", "-j", "addr", "show"], text=True)
        data = json.loads(j)
        pref = (prefer_iface or '').strip().lower()
        for itf in data:
            ifname = str(itf.get("ifname") or itf.get("name") or "").strip().lower()
            if pref and ifname != pref:
                continue
            for a in itf.get("addr_info", []) or []:
                if a.get("family") != "inet":
                    continue
                local = a.get("local")
                prefix = a.get("prefixlen")
                if not local or prefix is None:
                    continue
                # Skip loopback + link-local
                if str(local).startswith("127.") or str(local).startswith("169.254."):
                    continue

                # Avoid scanning overlay/VPN interfaces and non-private ranges by default.
                # NetBird commonly uses 100.64.0.0/10; we don't want discovery to lock onto that.
                if ifname and any(x in ifname for x in ("wt0", "netbird", "tailscale", "wg", "wireguard", "tun", "tap")):
                    continue

                # Some setups assign /32 to interfaces (point-to-point, overlays). A /32 scan is useless,
                # so we broaden it to /24 for scanning purposes.
                try:
                    pref_i = int(prefix)
                except Exception:
                    pref_i = prefix
                if isinstance(pref_i, int) and pref_i >= 29:
                    net = ipaddress.ip_network(f"{local}/24", strict=False)
                else:
                    net = ipaddress.ip_network(f"{local}/{prefix}", strict=False)

                # Only include private IPv4 networks (RFC1918). This prevents discovery from scanning
                # CGNAT/VPN networks and public interfaces.
                if not (net.version == 4 and net.is_private):
                    continue

                cidrs.append(str(net))
    except Exception:
        pass

    # 2) Routed private networks (helps scanning across VLANs)
    try:
        # include routes from non-main tables too (e.g. policy routing, overlay tables)
        j = subprocess.check_output(["ip", "-j", "route", "show", "table", "all"], text=True)
        routes = json.loads(j)
        for r in routes:
            dst = r.get("dst")
            if not dst or dst in ("default", "0.0.0.0/0"):
                continue
            # only RFC1918
            if not (dst.startswith("10.") or dst.startswith("192.168.") or dst.startswith("172.")):
                continue
            # avoid massive scans by default (user can use Custom scope for very large ranges)
            m = re.match(r"^\d+\.\d+\.\d+\.\d+/(\d+)$", dst)
            if not m:
                continue
            pref = int(m.group(1))
            if pref < 16:
                # too large – skip here, but we may still include a smaller set based on known targets
                continue
            cidrs.append(dst)
    except Exception:
        pass

    # de-dup while preserving order
    seen = set()
    uniq = []
    for c in cidrs:
        if c in seen:
            continue
        seen.add(c)
        uniq.append(c)
    return uniq


def _get_default_gateway_ip() -> str:
    """Return default gateway IP if available (IPv4)."""
    try:
        out = subprocess.check_output(["ip","route","show","default"], text=True, stderr=subprocess.DEVNULL)
        # default via 10.5.0.1 dev eth0 ...
        m = re.search(r"\bvia\s+(\d+\.\d+\.\d+\.\d+)", out)
        if m:
            gw = m.group(1)
            # If the default route is through an overlay/VPN (rare, but possible), ignore it.
            # We want discovery to use local private networks.
            if not _is_rfc1918(gw):
                return ""
            return gw
    except Exception:
        pass
    return ""


def _is_rfc1918(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
        return a.version == 4 and a.is_private
    except Exception:
        return False


def _gateway_first_cidrs(gw: str, series: str = 'auto') -> list[str]:
    """Build a safe, ordered list of CIDRs.

    This is intentionally /24-chunked (later in _discover_build_cidrs we normalize anyway).
    The order follows the user's request:
    - start from the gateway's "family" first (e.g. 10.5.x.x /16 in /24 steps)
    - then continue with the remaining RFC1918 ranges.

    NOTE: scanning *all* of 10/8 is enormous; the global cap will truncate.
    """
    series = (series or 'auto').lower()
    gw = gw or ""
    out: list[str] = []

    def add_10_ordered(pref_second: int | None):
        seconds = list(range(0,256))
        if pref_second is not None and 0 <= pref_second <= 255:
            seconds = [pref_second] + [s for s in seconds if s != pref_second]
        for s in seconds:
            # 10.s.0.0/16 (will be chunked to /24)
            out.append(f"10.{s}.0.0/16")

    def add_172_ordered(pref_second: int | None):
        seconds = list(range(16,32))
        if pref_second is not None and pref_second in seconds:
            seconds = [pref_second] + [s for s in seconds if s != pref_second]
        for s in seconds:
            out.append(f"172.{s}.0.0/16")

    def add_192():
        out.append("192.168.0.0/16")

    if series in ('auto',):
        # gateway's /16 first (if private)
        if _is_rfc1918(gw):
            parts = [int(x) for x in gw.split('.')]
            if parts[0] == 10:
                out.append(f"10.{parts[1]}.0.0/16")
            elif parts[0] == 172 and 16 <= parts[1] <= 31:
                out.append(f"172.{parts[1]}.0.0/16")
            elif parts[0] == 192 and parts[1] == 168:
                out.append("192.168.0.0/16")
        return out

    # explicit series
    if series == '10':
        pref = None
        if _is_rfc1918(gw) and gw.startswith('10.'):
            try: pref = int(gw.split('.')[1])
            except Exception: pref = None
        add_10_ordered(pref)
        return out
    if series == '172':
        pref = None
        if _is_rfc1918(gw) and gw.startswith('172.'):
            try: pref = int(gw.split('.')[1])
            except Exception: pref = None
        add_172_ordered(pref)
        return out
    if series == '192':
        add_192()
        return out
    if series == 'all':
        pref10 = None
        if _is_rfc1918(gw) and gw.startswith('10.'):
            try: pref10 = int(gw.split('.')[1])
            except Exception: pref10 = None
        add_10_ordered(pref10)
        pref172 = None
        if _is_rfc1918(gw) and gw.startswith('172.'):
            try: pref172 = int(gw.split('.')[1])
            except Exception: pref172 = None
        add_172_ordered(pref172)
        add_192()
        return out

    return out


def _cidr_to_host_range(cidr: str) -> str:
    """Human readable host range for UI, e.g. 10.5.0.0/24 -> 10.5.0.1-254."""
    try:
        net = ipaddress.ip_network(cidr, strict=False)
        if net.version != 4:
            return ""
        # hosts() can be huge; compute first/last without iterating
        if net.num_addresses <= 2:
            return str(net.network_address)
        first = int(net.network_address) + 1
        last = int(net.broadcast_address) - 1
        return f"{ipaddress.ip_address(first)}-{ipaddress.ip_address(last)}"
    except Exception:
        return ""


def _cidrs_from_existing_targets() -> list[str]:
    """Derive candidate subnets from existing targets.

    This makes scanning useful even when routing tables are minimal, or when VLAN routes
    live in non-main tables, or when the host is on an overlay network but targets are not.
    """
    out: list[str] = []
    try:
        if not DB_PATH.exists():
            return out
        conn = sqlite3.connect(str(DB_PATH))
        try:
            cur = conn.cursor()
            cur.execute("SELECT ip FROM targets")
            ips = [r[0] for r in cur.fetchall() if r and r[0]]
        finally:
            conn.close()

        for ip in ips:
            try:
                addr = ipaddress.ip_address(str(ip).strip())
                # default to /24 for IPv4
                if addr.version == 4:
                    net = ipaddress.ip_network(f"{addr}/24", strict=False)
                    out.append(str(net))
            except Exception:
                continue
    except Exception:
        return out

    # de-dup while preserving order
    seen = set()
    uniq = []
    for c in out:
        if c in seen:
            continue
        seen.add(c)
        uniq.append(c)
    return uniq


def _scan_log(line: str):
    """Append a line to scan output file."""
    ensure_state_dir()
    try:
        with open(SCAN_OUT_FILE, "a", encoding="utf-8", errors="replace") as f:
            f.write((line or "").rstrip("\n") + "\n")
    except Exception:
        pass


def _get_target_ips() -> list[str]:
    """Read target IPs from the SQLite state DB.

    We use this to make network scanning more reliable across VLANs:
    if the system can already ping targets manually added, we should
    at minimum scan the same subnets as those targets live in.
    """
    ips: list[str] = []
    try:
        if not DB_PATH.exists():
            return ips
        con = sqlite3.connect(str(DB_PATH))
        try:
            cur = con.cursor()
            cur.execute("SELECT ip FROM targets;")
            for (ip,) in cur.fetchall() or []:
                ip = str(ip or "").strip()
                if ip:
                    ips.append(ip)
        finally:
            con.close()
    except Exception:
        return []

    # de-dup
    seen = set()
    out = []
    for ip in ips:
        if ip in seen:
            continue
        seen.add(ip)
        out.append(ip)
    return out


def _mac_vendor_from_nmap_prefixes(mac: str) -> str:
    """Best-effort vendor from nmap-mac-prefixes (if present)."""
    if not mac:
        return ""
    try:
        prefix = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()[:6]
        if len(prefix) != 6:
            return ""
        candidates = [
            Path("/usr/share/nmap/nmap-mac-prefixes"),
            Path("/usr/local/share/nmap/nmap-mac-prefixes"),
        ]
        for p in candidates:
            if not p.exists():
                continue
            # The file is large. Scan linearly but stop early when possible.
            with p.open("r", encoding="utf-8", errors="replace") as f:
                for ln in f:
                    if ln.startswith(prefix):
                        return ln.split(None, 1)[1].strip() if " " in ln else ""
        return ""
    except Exception:
        return ""


def _read_ip_neigh() -> dict:
    """Return {ip: mac} from neighbor/ARP table."""
    out: dict[str, str] = {}
    try:
        raw = subprocess.check_output(["ip", "neigh", "show"], text=True)
        for ln in raw.splitlines():
            # Example: 10.5.10.21 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
            m = re.search(r"^(\d+\.\d+\.\d+\.\d+).*\blladdr\s+([0-9a-f:]{17})\b", ln, re.I)
            if m:
                out[m.group(1)] = m.group(2).lower()
    except Exception:
        pass
    return out


def _resolve_name(ip: str, timeout_s: float = 0.35) -> str:
    """Reverse-DNS with a short timeout."""
    if not ip:
        return ""
    name: str = ""

    def _do():
        nonlocal name
        try:
            name = socket.gethostbyaddr(ip)[0]
        except Exception:
            name = ""

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    return name


def _scan_with_nmap(cidrs: list[str], speed: str, cancel_flag: threading.Event) -> list[dict]:
    """Preferred scan implementation if nmap is available."""
    found: list[dict] = []
    if not shutil.which("nmap"):
        return found

    timing = {"slow": "-T2", "normal": "-T4", "fast": "-T5"}.get((speed or "normal").lower(), "-T4")

    for cidr in cidrs:
        if cancel_flag.is_set():
            break
        _scan_log(f"scan: {cidr}")
        try:
            # We intentionally prefer nmap because it handles host discovery more reliably than
            # pure ping sweeps (and can still work when some devices don't respond to ICMP).
            #
            # -sn = host discovery only
            # -n  = no DNS (we do reverse DNS ourselves to keep output consistent)
            # -oX - = XML output to stdout (we parse minimal fields)
            cmd = [
                "nmap",
                "-sn",
                "-n",
                timing,
                "--max-retries",
                "2",
                "--host-timeout",
                "3s",
                "-oX",
                "-",
                cidr,
            ]

            p = subprocess.run(cmd, capture_output=True, text=True)
            xml = (p.stdout or "") + ("\n" + (p.stderr or "") if p.stderr else "")
            if p.returncode != 0:
                # Include nmap output – this is often the only clue (permissions, missing binary, etc.)
                short = " ".join((xml or "").strip().splitlines()[-3:])
                _scan_log(f"warn: nmap rc={p.returncode} on {cidr}: {short}")
                # Still try to parse if any XML was produced.
        except Exception as e:
            _scan_log(f"warn: nmap error on {cidr}: {str(e)}")
            continue

        # Minimal XML parse (no external deps)
        # Extract <host> blocks, pull IPv4 addr, mac addr, and optional hostname.
        for host_block in re.findall(r"<host[\s\S]*?</host>", xml):
            if cancel_flag.is_set():
                break
            ipm = re.search(r"<address\s+addr=\"(\d+\.\d+\.\d+\.\d+)\"\s+addrtype=\"ipv4\"", host_block)
            if not ipm:
                continue
            ip = ipm.group(1)
            mac = ""
            vendor = ""
            mm = re.search(r"<address\s+addr=\"([0-9A-Fa-f:]{17})\"\s+addrtype=\"mac\"(?:\s+vendor=\"([^\"]*)\")?", host_block)
            if mm:
                mac = (mm.group(1) or "").lower()
                vendor = (mm.group(2) or "").strip()
            hn = ""
            hnm = re.search(r"<hostname\s+name=\"([^\"]+)\"", host_block)
            if hnm:
                hn = hnm.group(1).strip()
            found.append({
                "ip": ip,
                "mac": mac,
                "vendor": vendor,
                "host": hn,
                "type": "",
            })
    return found


def _scan_with_ping(cidrs: list[str], speed: str, cancel_flag: threading.Event) -> list[dict]:
    """Fallback scan: ping sweep + ARP/neigh lookup."""
    found_ips: set[str] = set()
    speed_l = (speed or "normal").lower()
    # Ping tuning
    timeout_s = {"slow": 1.2, "normal": 0.8, "fast": 0.45}.get(speed_l, 0.8)
    max_workers = {"slow": 80, "normal": 160, "fast": 260}.get(speed_l, 160)
    max_hosts_per_cidr = 4096

    def ping_one(ip: str) -> bool:
        if cancel_flag.is_set():
            return False
        try:
            # BusyBox vs iputils differences: keep it conservative.
            cmd = ["ping", "-c", "1", "-W", str(int(max(1, round(timeout_s)))), ip]
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return r.returncode == 0
        except Exception:
            return False

    for cidr in cidrs:
        if cancel_flag.is_set():
            break
        _scan_log(f"scan: {cidr}")
        try:
            net = ipaddress.ip_network(cidr, strict=False)
        except Exception:
            _scan_log(f"warn: invalid cidr: {cidr}")
            continue

        # Avoid insane sweeps
        host_count = max(0, int(net.num_addresses) - 2)
        if host_count > max_hosts_per_cidr:
            _scan_log(f"warn: skipping {cidr} ({host_count} hosts) – too large")
            continue

        hosts = [str(h) for h in net.hosts()]
        # Ping sweep
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(ping_one, ip): ip for ip in hosts}
            for fut in concurrent.futures.as_completed(futs):
                if cancel_flag.is_set():
                    break
                ip = futs[fut]
                try:
                    ok = bool(fut.result())
                except Exception:
                    ok = False
                if ok:
                    found_ips.add(ip)
        # Give neigh table a moment to settle
        time.sleep(0.2)

    neigh = _read_ip_neigh()
    out: list[dict] = []
    for ip in sorted(found_ips, key=lambda s: tuple(int(x) for x in s.split("."))):
        if cancel_flag.is_set():
            break
        mac = neigh.get(ip, "")
        vendor = _mac_vendor_from_nmap_prefixes(mac)
        out.append({
            "ip": ip,
            "mac": mac,
            "vendor": vendor,
            "host": "",
            "type": "",
        })
    return out


def _normalize_scan_devices(devs: list[dict]) -> list[dict]:
    """De-dup by IP, enrich with reverse-DNS name where missing."""
    by_ip: dict[str, dict] = {}
    for d in devs or []:
        ip = str((d or {}).get("ip") or "").strip()
        if not ip:
            continue
        cur = by_ip.get(ip) or {}
        cur.update({k: v for k, v in (d or {}).items() if v})
        cur["ip"] = ip
        by_ip[ip] = cur

    out: list[dict] = []
    for ip in sorted(by_ip.keys(), key=lambda s: tuple(int(x) for x in s.split("."))):
        d = by_ip[ip]
        if not d.get("host"):
            d["host"] = _resolve_name(ip) or ""
        # Ensure keys exist for UI
        d.setdefault("mac", "")
        d.setdefault("vendor", "")
        d.setdefault("type", "")
        out.append(d)
    return out


def _build_scan_cidrs(opts: dict) -> list[str]:
    scope = (opts or {}).get("scope") or "local"
    custom = (opts or {}).get("custom") or ""
    scope = scope.strip().lower()
    cidrs: list[str] = []
    if scope in ("custom", "local+custom"):
        if scope == "local+custom":
            cidrs.extend(_get_local_cidrs())
            cidrs.extend(_cidrs_from_existing_targets())
        for part in re.split(r"[\s,;]+", custom.strip()):
            if not part:
                continue
            try:
                cidrs.append(str(ipaddress.ip_network(part, strict=False)))
            except Exception:
                continue
    else:
        cidrs = []
        cidrs.extend(_get_local_cidrs())
        cidrs.extend(_cidrs_from_existing_targets())

    # de-dup
    seen = set()
    uniq = []
    for c in cidrs:
        if c in seen:
            continue
        seen.add(c)
        uniq.append(c)
    return uniq


def _scan_worker():
    """Background worker invoked by scan_worker.py.

    Writes:
      - scan_last_output.txt (human readable)
      - scan_meta.json (status + found devices)
    """
    ensure_state_dir()
    meta = load_scan_meta() or {}
    opts = meta.get("opts") or {}

    cancel_flag = threading.Event()

    def _on_term(_sig, _frame):
        cancel_flag.set()

    try:
        signal.signal(signal.SIGTERM, _on_term)
        signal.signal(signal.SIGINT, _on_term)
    except Exception:
        pass

    # Reset output
    try:
        SCAN_OUT_FILE.write_text("", encoding="utf-8")
    except Exception:
        pass

    cidrs = _build_scan_cidrs(opts)
    meta.update({
        "pid": int(os.getpid()),
        "started": int(meta.get("started") or time.time()),
        "finished": 0,
        "rc": None,
        "error": "",
        "cidrs": cidrs,
        "found": [],
        "current_ip": "",
    })
    save_scan_meta(meta)

    _scan_log("Network scan started")
    if not cidrs:
        _scan_log("warn: no subnets found to scan")
        meta.update({"finished": int(time.time()), "rc": 0, "found": []})
        save_scan_meta(meta)
        return

    speed = (opts.get("speed") or "normal").strip().lower()

    # Use nmap as the primary scanner.
    # If nmap is missing, stop with a clear message instead of silently returning no results.
    if not shutil.which("nmap"):
        meta.update({"finished": int(time.time()), "rc": 1, "error": "nmap is not installed on this host"})
        save_scan_meta(meta)
        _scan_log("error: nmap is not installed on this host")
        _scan_log("hint: install with: sudo apt-get update && sudo apt-get install -y nmap")
        return

    _scan_log("info: using nmap")
    devices: list[dict] = _scan_with_nmap(cidrs, speed, cancel_flag)

    if cancel_flag.is_set():
        meta.update({"finished": int(time.time()), "rc": 1, "error": "Cancelled"})
        save_scan_meta(meta)
        _scan_log("Scan cancelled")
        return

    devices = _normalize_scan_devices(devices)
    meta["found"] = devices
    meta.update({"finished": int(time.time()), "rc": 0, "error": "", "current_ip": ""})
    save_scan_meta(meta)
    _scan_log(f"Scan finished: found {len(devices)} device(s)")


@APP.post("/api/scan-start")
def api_scan_start():
    ensure_state_dir()
    meta = load_scan_meta()
    form = request.form or {}
    force = str(form.get("force") or "0") == "1"

    pid = int(meta.get("pid") or 0)
    if pid and pid_is_running(pid):
        if not force:
            return jsonify({"ok": True, "message": "Already running", "pid": pid})
        # force => cancel then restart
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        meta.update({"pid": 0, "finished": int(time.time())})
        save_scan_meta(meta)

    started = int(meta.get("started") or 0)
    finished = int(meta.get("finished") or 0)
    if started and finished and not force:
        return jsonify({"ok": True, "message": "Finished", "pid": 0})

    opts = {
        "scope": (form.get("scope") or (meta.get("opts") or {}).get("scope") or "local").strip(),
        "speed": (form.get("speed") or (meta.get("opts") or {}).get("speed") or "normal").strip(),
        "custom": (form.get("custom") or (meta.get("opts") or {}).get("custom") or "").strip(),
    }
    meta["opts"] = opts
    save_scan_meta(meta)

    try:
        worker_path = BASE_DIR / "scan_worker.py"
        if not worker_path.exists():
            raise FileNotFoundError(f"scan worker missing: {worker_path}")
        p = subprocess.Popen(
            ["python3", str(worker_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        m = load_scan_meta()
        m.update({"pid": int(p.pid or 0), "started": int(time.time()), "finished": 0, "rc": None, "error": "", "opts": opts})
        save_scan_meta(m)
        return jsonify({"ok": True, "message": "Started", "pid": int(p.pid or 0)})
    except Exception as e:
        save_scan_meta({"pid": 0, "started": 0, "finished": int(time.time()), "rc": 1, "error": str(e), "opts": opts})
        return jsonify({"ok": False, "message": f"Failed to start scan: {str(e)}"})

@APP.get("/api/scan-status")
def api_scan_status():
    meta = load_scan_meta()
    pid = int(meta.get("pid") or 0)
    started = int(meta.get("started") or 0)
    finished = int(meta.get("finished") or 0)

    if pid and pid_is_running(pid):
        return jsonify({"running": True, "finished": False, "pid": pid, "started": started})

    if started and not finished:
        meta["finished"] = int(time.time())
        meta["pid"] = 0
        save_scan_meta(meta)

    return jsonify({
        "running": False,
        "finished": bool(started and int(meta.get("finished") or 0)),
        "pid": pid,
        "started": started,
        "finished_at": int(meta.get("finished") or 0),
        "rc": meta.get("rc"),
        "error": meta.get("error", ""),
    })


@APP.post("/api/scan-cancel")
def api_scan_cancel():
    meta = load_scan_meta()
    pid = int(meta.get("pid") or 0)
    if not pid or not pid_is_running(pid):
        return jsonify({"ok": True, "message": "Not running"})
    try:
        import signal
        os.kill(pid, signal.SIGTERM)
        meta["error"] = "Cancelled"
        meta["rc"] = 1
        save_scan_meta(meta)
        return jsonify({"ok": True, "message": "Cancelled"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})

@APP.get("/api/scan-output")
def api_scan_output():
    try:
        lines = int(request.args.get("lines", "200"))
    except Exception:
        lines = 200
    lines = max(50, min(1200, lines))
    try:
        raw = SCAN_OUT_FILE.read_text(encoding="utf-8", errors="replace") if SCAN_OUT_FILE.exists() else ""
        arr = raw.splitlines()
        tail = "\n".join(arr[-lines:]) if arr else ""
        meta = load_scan_meta()
        return jsonify({"ok": True, "text": tail, "meta": meta})
    except Exception as e:
        return jsonify({"ok": False, "text": f"(error reading scan output: {str(e)})", "meta": {}})

@APP.get("/api/scan-result")
def api_scan_result():
    meta = load_scan_meta()
    found = meta.get("found") or []
    return jsonify({"ok": True, "found": found, "meta": meta})

# ---- API: network discovery (nmap-only, realtime) ----

def _discover_build_cidrs(opts: dict) -> list[str]:
    """Build CIDRs to scan.

    We try hard to scan the same networks the box can already reach (including VLANs).
    """
    scope = (opts.get('scope') or 'auto').lower()
    prefer_iface = (opts.get('iface') or '').strip().lower()
    if prefer_iface in ('', 'auto', 'default'):
        prefer_iface = ''
    cidrs: list[str] = []

    # Scope values supported by the WebUI:
    # auto = gateway-first + reachable routed nets
    # 10/172/192 = RFC1918 series
    # all = all RFC1918 series (slow)
    # custom = user provided CIDRs
    if scope in ('custom',):
        raw = str(opts.get('custom') or '').strip()
        for part in raw.split(','):
            part = part.strip()
            if part:
                cidrs.append(part)
    else:
        # Gateway-first ordering (best UX: starts where the box most likely lives)
        gw = _get_default_gateway_ip()
        if scope in ('auto',) and gw:
            cidrs += _gateway_first_cidrs(gw, series='auto')

        if scope in ('10','172','192','all'):
            cidrs += _gateway_first_cidrs(gw, series=scope)
        elif scope in ('auto','local','all'):
            # Reachable routed nets + targets (covers VLAN routes)
            cidrs += _get_local_cidrs(prefer_iface or None)
            cidrs += _cidrs_from_existing_targets()

    # de-dup
    seen=set(); uniq=[]
    for c in cidrs:
        if c in seen: continue
        seen.add(c); uniq.append(c)

    # normalize + split huge nets to /24 chunks (safe by default)
    out: list[str] = []
    for c in uniq:
        try:
            net = ipaddress.ip_network(c, strict=False)
        except Exception:
            continue
        if net.version != 4:
            continue
        # Avoid /8 or massive ranges by chunking to /24.
        if net.prefixlen < 24:
            # chunk to /24
            for sub in net.subnets(new_prefix=24):
                out.append(str(sub))
        else:
            out.append(str(net))

    # hard safety cap (can still be large, but avoids accidental /8 expanding forever)
    cap = int(opts.get('cap') or 2048)
    out = out[:max(1, min(10000, cap))]
    return out


def _nmap_args_for_profile(profile: str) -> list[str]:
    p = (profile or 'safe').lower()
    if p == 'fast':
        return ['-T4','--max-retries','1','--host-timeout','2s']
    if p == 'normal':
        return ['-T3','--max-retries','1','--host-timeout','2s']
    # safe
    return ['-T2','--max-retries','1','--host-timeout','3s','--scan-delay','5ms']


def _discover_worker():
    meta = load_discovery_meta() or {}
    opts = meta.get('opts') or {}
    prefer_iface = str(opts.get('iface') or '').strip()
    if prefer_iface.lower() in ('', 'auto', 'default'):
        prefer_iface = ''
    cancel_path = STATE_DIR / 'discovery_cancel'

    # reset output/events
    try:
        DISCOVERY_EVENTS_FILE.write_text('', encoding='utf-8')
        os.chmod(str(DISCOVERY_EVENTS_FILE), 0o644)
    except Exception:
        pass

    cidrs = _discover_build_cidrs(opts)
    meta.update({
        'status':'running',
        'started': int(time.time()),
        'finished': 0,
        'rc': 0,
        'error': '',
        'cidrs': cidrs,
        'found': [],
        'profile': (opts.get('profile') or 'safe'),
    })
    save_discovery_meta(meta)

    if not shutil.which('nmap'):
        meta.update({'status':'error','finished':int(time.time()),'rc':1,'error':'nmap is not installed'})
        save_discovery_meta(meta)
        _append_discovery_event({'type':'error','message':'nmap is not installed'})
        return

    existing_ips = set(_get_target_ips())
    found_ips = set()

    event_id = 1
    _append_discovery_event({'id': event_id, 'type':'status','status':'running','message':'Discovery started','cidrs':len(cidrs)})

    for idx, cidr in enumerate(cidrs):
        if cancel_path.exists():
            meta.update({'status':'cancelled','finished':int(time.time()),'rc':1,'error':'Cancelled'})
            save_discovery_meta(meta)
            event_id += 1
            _append_discovery_event({'id': event_id,'type':'status','status':'cancelled','message':'Cancelled'})
            try:
                cancel_path.unlink(missing_ok=True)
            except Exception:
                pass
            return

        # Emit a live "what are we scanning" hint (used by the WebUI)
        try:
            rng = _cidr_to_host_range(cidr)
        except Exception:
            rng = ""
        event_id += 1
        _append_discovery_event({
            'id': event_id,
            'type':'status',
            'status':'running',
            'message': f"Scanning {cidr}",
            'scanning': f"{cidr}{(' • ' + rng) if rng else ''}",
            'progress': {'current': idx+1, 'total': len(cidrs), 'cidr': cidr}
        })

        args = ['nmap','-sn','-n']
        if prefer_iface:
            # Force interface selection to avoid VPN/overlay interfaces becoming the default.
            args += ['-e', prefer_iface]
        args += _nmap_args_for_profile(meta.get('profile')) + [cidr]
        # stream normal output
        try:
            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception as e:
            meta.update({'status':'error','finished':int(time.time()),'rc':1,'error':str(e)})
            save_discovery_meta(meta)
            event_id += 1
            _append_discovery_event({'id': event_id,'type':'error','message':str(e)})
            return

        cur = {'ip':'','host':'','mac':'','vendor':'','type':''}
        def flush_current():
            nonlocal event_id
            ip = (cur.get('ip') or '').strip()
            if not ip:
                return
            if ip in found_ips:
                return
            found_ips.add(ip)
            dev = dict(cur)
            dev['already_added'] = ip in existing_ips
            # store
            meta = load_discovery_meta() or {}
            found = meta.get('found') or []
            found.append(dev)
            meta['found'] = found
            meta['progress'] = {'current': idx+1, 'total': len(cidrs), 'cidr': cidr}
            save_discovery_meta(meta)
            event_id += 1
            _append_discovery_event({'id': event_id,'type':'device','device':dev})

        for line in p.stdout:
            if cancel_path.exists():
                try:
                    p.terminate()
                except Exception:
                    pass
                break
            line = (line or '').rstrip('\n')
            if not line:
                continue
            # status event occasionally (throttle by subnet boundaries only)
            if line.startswith('Nmap scan report for '):
                # flush previous
                flush_current()
                cur = {'ip':'','host':'','mac':'','vendor':'','type':''}
                rest = line.replace('Nmap scan report for ','').strip()
                # rest can be IP or "name (ip)"; with -n it's usually IP
                if '(' in rest and rest.endswith(')'):
                    # name (ip)
                    name, ip = rest.rsplit('(',1)
                    cur['host'] = name.strip()
                    cur['ip'] = ip.strip(') ').strip()
                else:
                    cur['ip'] = rest
            elif 'MAC Address:' in line:
                # MAC Address: AA:BB:CC:DD:EE:FF (Vendor)
                try:
                    seg = line.split('MAC Address:',1)[1].strip()
                    mac = seg.split()[0].strip().lower()
                    cur['mac'] = mac
                    if '(' in seg and seg.endswith(')'):
                        cur['vendor'] = seg.split('(',1)[1].strip(') ').strip()
                except Exception:
                    pass
            elif line.startswith('Host is up'):
                # nothing
                pass
        try:
            p.wait(timeout=2)
        except Exception:
            pass
        # flush last host in this cidr
        flush_current()

        # progress status per cidr
        event_id += 1
        _append_discovery_event({'id': event_id,'type':'status','status':'running','message':f"Scanned {idx+1}/{len(cidrs)}",'progress':{'current':idx+1,'total':len(cidrs),'cidr':cidr}})

    meta = load_discovery_meta() or {}
    meta.update({'status':'done','finished':int(time.time()),'rc':0})
    save_discovery_meta(meta)
    event_id += 1
    _append_discovery_event({'id': event_id,'type':'status','status':'done','message':'Discovery finished','found':len(meta.get('found') or [])})


@APP.post('/api/discover-start')
def api_discover_start():
    data = request.get_json(silent=True) or {}
    # reset cancel flag
    try:
        (STATE_DIR / 'discovery_cancel').unlink(missing_ok=True)
    except Exception:
        pass

    meta = load_discovery_meta() or {}
    if meta.get('status') == 'running' and pid_is_running(int(meta.get('pid') or 0)):
        return jsonify({'ok': False, 'message':'Discovery already running'})

    opts = {
        'scope': data.get('scope') or 'auto',
        'custom': data.get('custom') or '',
        'iface': data.get('iface') or 'auto',
        'profile': data.get('profile') or 'safe',
        'cap': data.get('cap') or 2048,
    }

    try:
        app.logger.info("DISCOVERY_START request from %s opts=%s", request.remote_addr, opts)
    except Exception:
        pass
    meta = {'opts': opts, 'status':'starting', 'started':int(time.time()), 'finished':0, 'found':[], 'rc':0, 'error':''}
    save_discovery_meta(meta)

    # start background worker
    try:
        worker_path = BASE_DIR / 'discovery_worker.py'
        if not worker_path.exists():
            raise FileNotFoundError(f"discovery worker missing: {worker_path}")
        p = subprocess.Popen([sys.executable, str(worker_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        meta = load_discovery_meta() or {}
        meta['pid'] = int(p.pid)
        meta['status'] = 'running'
        save_discovery_meta(meta)
        return jsonify({'ok': True, 'message':'Discovery started'})
    except Exception as e:
        meta = load_discovery_meta() or {}
        meta.update({'status':'error','rc':1,'finished':int(time.time()),'error':str(e)})
        save_discovery_meta(meta)
        return jsonify({'ok': False, 'message': f"Failed to start discovery: {str(e)}"})


@APP.get('/api/discover-status')
def api_discover_status():
    meta = load_discovery_meta() or {}
    pid = int(meta.get('pid') or 0)
    if meta.get('status') == 'running' and pid and not pid_is_running(pid):
        # if process died, mark as error
        meta['status'] = 'error'
        meta['rc'] = int(meta.get('rc') or 1)
        meta['finished'] = int(meta.get('finished') or int(time.time()))
        meta['error'] = meta.get('error') or 'Worker stopped unexpectedly'
        save_discovery_meta(meta)
    return jsonify({'ok': True, 'meta': meta})


@APP.post('/api/discover-cancel')
def api_discover_cancel():
    try:
        (STATE_DIR / 'discovery_cancel').write_text('1', encoding='utf-8')
    except Exception:
        pass
    meta = load_discovery_meta() or {}
    meta['status'] = 'cancelling'
    save_discovery_meta(meta)
    return jsonify({'ok': True, 'message':'Cancelling'})


@APP.get('/api/netifs')
def api_netifs():
    """Return a list of local network interfaces.

    Used by the Discovery UI so the user can force nmap to use a specific interface
    (e.g. eth0) and avoid VPN/overlay interfaces.
    """
    interfaces = []
    try:
        j = subprocess.check_output(["ip", "-j", "addr", "show"], text=True)
        data = json.loads(j)
        for itf in data:
            name = str(itf.get("ifname") or itf.get("name") or "").strip()
            if not name or name == "lo":
                continue
            low = name.lower()
            addrs = []
            for a in (itf.get("addr_info") or []):
                if a.get("family") != "inet":
                    continue
                local = a.get("local")
                pref = a.get("prefixlen")
                if not local or pref is None:
                    continue
                ip = str(local)
                if ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                addrs.append(f"{ip}/{pref}")
            if not addrs:
                # still show interface name, but without meta
                interfaces.append({"name": name, "meta": ""})
                continue
            meta = ", ".join(addrs[:2])
            if len(addrs) > 2:
                meta += f" (+{len(addrs)-2})"
            interfaces.append({"name": name, "meta": meta})
    except Exception:
        interfaces = []

    # Sort: prefer non-overlay interfaces first for nicer UX
    def is_overlay(n: str) -> bool:
        n = (n or '').lower()
        return any(x in n for x in ("wt0", "netbird", "tailscale", "wg", "wireguard", "tun", "tap"))

    interfaces.sort(key=lambda x: (is_overlay(x.get("name")), x.get("name") or ""))
    return jsonify({"ok": True, "interfaces": interfaces})


def _sse_format(event: str, data: str, event_id: int | None = None) -> str:
    out = ''
    if event_id is not None:
        out += f"id: {event_id}\n"
    if event:
        out += f"event: {event}\n"
    for ln in (data or '').splitlines() or ['']:
        out += f"data: {ln}\n"
    out += '\n'
    return out


@APP.get('/api/discover-stream')
def api_discover_stream():
    """Server-Sent Events stream from discovery_events.jsonl."""
    try:
        last_id = int(request.headers.get('Last-Event-ID') or request.args.get('last_id') or 0)
    except Exception:
        last_id = 0

    def gen():
        ensure_state_dir()
        path = DISCOVERY_EVENTS_FILE
        # ensure file exists
        if not path.exists():
            try:
                path.write_text('', encoding='utf-8')
            except Exception:
                pass
        pos = 0
        # If there is existing content and client didn't pass last_id, start from beginning.
        while True:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(pos)
                    while True:
                        ln = f.readline()
                        if not ln:
                            pos = f.tell()
                            break
                        ln = ln.strip()
                        if not ln:
                            continue
                        try:
                            import json as _json
                            obj = _json.loads(ln)
                            eid = int(obj.get('id') or 0)
                            if eid and eid <= last_id:
                                continue
                            ev = obj.get('type') or 'message'
                            yield _sse_format(ev, _json.dumps(obj, ensure_ascii=False), eid if eid else None)
                        except Exception:
                            continue
                # heartbeat
                yield ': ping\n\n'
                import time as _t
                _t.sleep(0.6)
            except GeneratorExit:
                return
            except Exception:
                import time as _t
                _t.sleep(0.8)

    return Response(gen(), mimetype='text/event-stream')


@APP.get('/api/discover-result')
def api_discover_result():
    meta = load_discovery_meta() or {}
    return jsonify({'ok': True, 'meta': meta, 'found': meta.get('found') or []})

if __name__ == "__main__":
    APP.run(host=BIND_HOST, port=BIND_PORT, threaded=True)
