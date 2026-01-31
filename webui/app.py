#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template, Response, send_file
import os
import subprocess
import time
import json
import re
import socket
import datetime
from io import BytesIO
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

SCAN_META_FILE = STATE_DIR / "scan_meta.json"
SCAN_OUT_FILE = STATE_DIR / "scan_last_output.txt"

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
        for p in (RUN_META_FILE, RUN_OUT_FILE, SCAN_META_FILE, SCAN_OUT_FILE):
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
    """Return merged targets, but keep the last good state if the CLI errors.

    This avoids the WebUI clearing the table when the DB is temporarily locked
    (e.g. while a run is updating), or when the CLI emits a transient error.
    """
    global _LAST_STATE_CACHE
    try:
        rc_list, list_out = run_cmd(["list"])
        rc_st, st_out = run_cmd(["status"])
        if rc_list != 0 or rc_st != 0:
            # serve cached targets if available
            if _LAST_STATE_CACHE.get("targets"):
                return False, _LAST_STATE_CACHE.get("targets")
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

        def ip_key(ip: str):
            try:
                a,b,c,d = [int(x) for x in (ip or "0.0.0.0").split(".")]
                return (a,b,c,d)
            except Exception:
                return (999,999,999,999)

        merged.sort(key=lambda x: ip_key(x.get("ip")))
        _LAST_STATE_CACHE = {"updated": int(time.time()), "targets": merged}
        return True, merged
    except Exception:
        if _LAST_STATE_CACHE.get("targets"):
            return False, _LAST_STATE_CACHE.get("targets")
        return False, []


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
    return jsonify({"ok": ok, "updated": int(time.time()), "targets": targets})

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
def _get_local_cidrs() -> list[str]:
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
        for itf in data:
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
                cidrs.append(f"{local}/{prefix}")
    except Exception:
        pass

    # 2) Routed private networks (helps scanning across VLANs)
    try:
        j = subprocess.check_output(["ip", "-j", "route", "show"], text=True)
        routes = json.loads(j)
        for r in routes:
            dst = r.get("dst")
            if not dst or dst in ("default", "0.0.0.0/0"):
                continue
            # only RFC1918
            if not (dst.startswith("10.") or dst.startswith("192.168.") or dst.startswith("172.")):
                continue
            # avoid massive scans
            m = re.match(r"^\d+\.\d+\.\d+\.\d+/(\d+)$", dst)
            if not m:
                continue
            pref = int(m.group(1))
            if pref < 16:
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
        p = subprocess.Popen(
            ["python3", str(BASE_DIR / "scan_worker.py")],
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
if __name__ == "__main__":
    APP.run(host=BIND_HOST, port=BIND_PORT, threaded=True)
