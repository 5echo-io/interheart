from __future__ import annotations

import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request


APP_NAME = "interheart"

# Må være samme DB som CLI bruker
DEFAULT_DB_PATH = "/var/lib/interheart/interheart.db"
DB_PATH = os.environ.get("INTERHEART_DB", DEFAULT_DB_PATH)

DEFAULT_INTERVAL = int(os.environ.get("INTERHEART_DEFAULT_INTERVAL", "60"))
MAX_INTERVAL = int(os.environ.get("INTERHEART_MAX_INTERVAL", "3600"))

NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{2,64}$")
IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def now_ts() -> int:
    return int(time.time())


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def db_init() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with connect_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS targets (
              name TEXT PRIMARY KEY,
              ip TEXT NOT NULL,
              endpoint TEXT NOT NULL,
              interval INTEGER NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 1,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL,
              last_status TEXT DEFAULT NULL,
              last_ping INTEGER DEFAULT NULL,
              last_response INTEGER DEFAULT NULL,
              last_latency_ms INTEGER DEFAULT NULL,
              next_due_at INTEGER DEFAULT NULL
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_targets_enabled ON targets(enabled);"
        )


def validate_name(name: str) -> None:
    if not NAME_RE.match(name or ""):
        raise ValueError("Invalid name (2-64 chars: a-z A-Z 0-9 . _ -)")


def validate_ip(ip: str) -> None:
    if not IP_RE.match(ip or ""):
        raise ValueError("Invalid IP format")
    parts = ip.split(".")
    if any(int(p) > 255 for p in parts):
        raise ValueError("Invalid IP range")


def validate_interval(interval: int) -> None:
    if interval < 5 or interval > MAX_INTERVAL:
        raise ValueError(f"Interval must be between 5 and {MAX_INTERVAL} seconds")


def validate_endpoint(endpoint: str) -> None:
    if not endpoint or not isinstance(endpoint, str):
        raise ValueError("Endpoint is required")
    if not (endpoint.startswith("http://") or endpoint.startswith("https://")):
        raise ValueError("Endpoint must start with http:// or https://")


def row_to_dict(r: sqlite3.Row) -> Dict[str, Any]:
    return {k: r[k] for k in r.keys()}


def list_targets() -> List[Dict[str, Any]]:
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT * FROM targets ORDER BY name COLLATE NOCASE ASC;"
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_target(name: str) -> Optional[Dict[str, Any]]:
    with connect_db() as conn:
        row = conn.execute(
            "SELECT * FROM targets WHERE name = ?;",
            (name,),
        ).fetchone()
    return row_to_dict(row) if row else None


def add_target(name: str, ip: str, endpoint: str, interval: int) -> None:
    ts = now_ts()
    with connect_db() as conn:
        existing = conn.execute(
            "SELECT name FROM targets WHERE name = ?;",
            (name,),
        ).fetchone()
        if existing:
            raise ValueError("Target already exists")

        conn.execute(
            """
            INSERT INTO targets
              (name, ip, endpoint, interval, enabled, created_at, updated_at, next_due_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?);
            """,
            (name, ip, endpoint, interval, ts, ts, ts),
        )


def delete_target(name: str) -> None:
    with connect_db() as conn:
        cur = conn.execute("DELETE FROM targets WHERE name = ?;", (name,))
        if cur.rowcount == 0:
            raise ValueError("Target not found")


def update_target(
    name: str,
    *,
    new_name: Optional[str] = None,
    ip: Optional[str] = None,
    endpoint: Optional[str] = None,
    interval: Optional[int] = None,
    enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    ts = now_ts()

    with connect_db() as conn:
        row = conn.execute(
            "SELECT * FROM targets WHERE name = ?;",
            (name,),
        ).fetchone()
        if not row:
            raise ValueError("Target not found")

        current = row_to_dict(row)

        if new_name and new_name != name:
            exists = conn.execute(
                "SELECT name FROM targets WHERE name = ?;",
                (new_name,),
            ).fetchone()
            if exists:
                raise ValueError("New name already exists")

        fields = []
        params: List[Any] = []

        if new_name is not None:
            fields.append("name = ?")
            params.append(new_name)
        if ip is not None:
            fields.append("ip = ?")
            params.append(ip)
        if endpoint is not None:
            fields.append("endpoint = ?")
            params.append(endpoint)
        if interval is not None:
            fields.append("interval = ?")
            params.append(interval)
        if enabled is not None:
            fields.append("enabled = ?")
            params.append(1 if enabled else 0)

        if not fields:
            return current

        fields.append("updated_at = ?")
        params.append(ts)

        params.append(name)

        conn.execute(
            f"UPDATE targets SET {', '.join(fields)} WHERE name = ?;",
            tuple(params),
        )

    return get_target(new_name or name) or {}


def api_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


app = Flask(__name__, template_folder="templates", static_folder="static")

# Flask 2.3+ fjernet before_first_request, så vi init’er DB ved oppstart (import-time).
db_init()


@app.get("/")
def index():
    return render_template(
        "index.html",
        app_name=APP_NAME,
        default_interval=DEFAULT_INTERVAL,
        max_interval=MAX_INTERVAL,
    )


@app.get("/api/targets")
def api_list_targets():
    return jsonify({"ok": True, "data": list_targets()})


@app.get("/api/targets/<name>")
def api_get_target(name: str):
    t = get_target(name)
    if not t:
        return api_error("Target not found", 404)
    return jsonify({"ok": True, "data": t})


@app.post("/api/targets")
def api_add_target():
    payload = request.get_json(silent=True) or {}
    try:
        name = str(payload.get("name", "")).strip()
        ip = str(payload.get("ip", "")).strip()
        endpoint = str(payload.get("endpoint", "")).strip()
        interval = int(payload.get("interval", DEFAULT_INTERVAL))

        validate_name(name)
        validate_ip(ip)
        validate_endpoint(endpoint)
        validate_interval(interval)

        add_target(name, ip, endpoint, interval)
        return jsonify({"ok": True, "data": get_target(name)})
    except ValueError as e:
        return api_error(str(e), 400)
    except Exception:
        return api_error("Unexpected error", 500)


@app.delete("/api/targets/<name>")
def api_delete_target(name: str):
    try:
        validate_name(name)
        delete_target(name)
        return jsonify({"ok": True})
    except ValueError as e:
        msg = str(e)
        return api_error(msg, 404 if "not found" in msg.lower() else 400)
    except Exception:
        return api_error("Unexpected error", 500)


@app.patch("/api/targets/<name>")
def api_patch_target(name: str):
    payload = request.get_json(silent=True) or {}

    try:
        validate_name(name)

        new_name = payload.get("name")
        ip = payload.get("ip")
        endpoint = payload.get("endpoint")
        interval = payload.get("interval")
        enabled = payload.get("enabled")

        if new_name is not None:
            new_name = str(new_name).strip()
            validate_name(new_name)

        if ip is not None:
            ip = str(ip).strip()
            validate_ip(ip)

        if endpoint is not None:
            endpoint = str(endpoint).strip()
            validate_endpoint(endpoint)

        if interval is not None:
            interval = int(interval)
            validate_interval(interval)

        if enabled is not None:
            enabled = bool(enabled)

        updated = update_target(
            name,
            new_name=new_name,
            ip=ip,
            endpoint=endpoint,
            interval=interval,
            enabled=enabled,
        )
        return jsonify({"ok": True, "data": updated})
    except ValueError as e:
        msg = str(e)
        status = 404 if "not found" in msg.lower() else 400
        return api_error(msg, status)
    except Exception:
        return api_error("Unexpected error", 500)


@app.get("/api/health")
def api_health():
    return jsonify(
        {
            "ok": True,
            "app": APP_NAME,
            "db": DB_PATH,
            "ts": now_ts(),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), debug=True)
