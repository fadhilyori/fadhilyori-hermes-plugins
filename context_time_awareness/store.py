from __future__ import annotations

import logging
import os
import random
import sqlite3
import threading
import time
import uuid
import datetime as _datetime
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

DB_FILENAME = "sessions.db"
SCHEMA_RETRY_ATTEMPTS = 8
BUSY_TIMEOUT_MS = 10000
DEFAULT_REMINDER_MINUTES = 5
CLEANUP_INTERVAL_SECONDS = 3600
EVENT_RETENTION_DAYS = 30
ACTIVE_WINDOW_AFTER_START_SECONDS = 1800
UPCOMING_LIMIT_DAYS = 14

_DateTime = _datetime.datetime
_TzInfo = _datetime.tzinfo

_store: sqlite3.Connection | None = None
_store_lock = threading.Lock()


def _is_transient(err: BaseException | None) -> bool:
    if err is None:
        return False
    msg = str(err)
    return "SQLITE_BUSY" in msg or "database is locked" in msg


def _resolve_local_tz() -> _TzInfo:
    tz = os.environ.get("TZ")
    if tz:
        try:
            return ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            pass
    return _DateTime.now().astimezone().tzinfo or _datetime.timezone.utc


def _open_store() -> sqlite3.Connection | None:
    path = os.path.join(PLUGIN_DIR, DB_FILENAME)
    conn = sqlite3.connect(
        path,
        timeout=BUSY_TIMEOUT_MS / 1000.0,
        check_same_thread=False,
        isolation_level=None,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")

    base_ms = 5
    for i in range(SCHEMA_RETRY_ATTEMPTS):
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "id TEXT PRIMARY KEY, ts INTEGER NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS events ("
                "event_id TEXT PRIMARY KEY, "
                "title TEXT NOT NULL, "
                "description TEXT DEFAULT '', "
                "start_time INTEGER NOT NULL, "
                "end_time INTEGER, "
                "reminder_offset INTEGER NOT NULL DEFAULT 300, "
                "created_at INTEGER NOT NULL, "
                "updated_at INTEGER NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_start_time ON events(start_time)"
            )
            _ensure_columns(conn)
            break
        except sqlite3.OperationalError as e:
            if not _is_transient(e) or i == SCHEMA_RETRY_ATTEMPTS - 1:
                conn.close()
                logger.warning("failed to open sessions DB at %s", path)
                return None
            base = base_ms * (2 ** i)
            jitter = random.uniform(-base / 4, base / 4)
            time.sleep((base + jitter) / 1000.0)
    return conn


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(events)")
    existing = {row[1] for row in cur.fetchall()}
    if "completed_at" not in existing:
        conn.execute("ALTER TABLE events ADD COLUMN completed_at INTEGER")


def init_store() -> None:
    global _store
    _store = _open_store()


def close_store() -> None:
    global _store
    if _store is not None:
        _store.close()
        _store = None


def _with_session(conn: sqlite3.Connection, sid: str, now: int) -> int | None:
    with _store_lock:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            return None
        try:
            cur = conn.execute("SELECT ts FROM sessions WHERE id = ?", (sid,))
            row = cur.fetchone()
            prior = row[0] if row else 0
            conn.execute(
                "INSERT INTO sessions(id, ts) VALUES(?, ?) "
                "ON CONFLICT(id) DO UPDATE SET ts = excluded.ts",
                (sid, now),
            )
            conn.execute("COMMIT")
            return prior
        except sqlite3.OperationalError as e:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            if _is_transient(e):
                return None
            raise


def touch_session(session_id: str, now: int) -> int | None:
    if _store is None or not session_id:
        return None
    return _with_session(_store, session_id, now)


def _generate_event_id() -> str:
    return str(uuid.uuid4())


def _parse_datetime(dt_str: str) -> int:
    if not dt_str or not isinstance(dt_str, str):
        raise ValueError("start_time/end_time must be a non-empty string")
    s = dt_str.strip().replace("Z", "+00:00")
    try:
        dt = _DateTime.fromisoformat(s)
    except ValueError as e:
        raise ValueError(
            f"Invalid datetime '{dt_str}'. Expected ISO 8601, e.g. "
            "'2024-01-15T14:30:00' or '2024-01-15T14:30:00+07:00'"
        ) from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_resolve_local_tz())
    return int(dt.timestamp())


def _format_event(row: tuple, local_tz: _TzInfo) -> dict:
    event_id, title, description, start_time, end_time, reminder_offset, _, _ , completed_at = row
    start_dt = _DateTime.fromtimestamp(start_time, tz=local_tz)
    now_ts = int(time.time())
    now_dt = _DateTime.fromtimestamp(now_ts, tz=local_tz)
    result = {
        "event_id": event_id,
        "title": title,
        "description": description or "",
        "start_time": f"{start_dt.strftime('%Y-%m-%d %H:%M %Z')} ({_start_time_hint(start_dt, now_dt)})",
        "reminder_minutes_before": reminder_offset // 60,
        "completed": completed_at is not None,
        "completed_at": (
            _DateTime.fromtimestamp(completed_at, tz=local_tz).strftime("%Y-%m-%d %H:%M %Z")
            if completed_at is not None
            else None
        ),
    }
    if end_time is not None:
        end_dt = _DateTime.fromtimestamp(end_time, tz=local_tz)
        result["end_time"] = (
            f"{end_dt.strftime('%Y-%m-%d %H:%M %Z')} "
            f"({_event_duration_str(start_dt, end_dt)})"
        )
    return result


def _start_time_hint(dt: _DateTime, now: _DateTime) -> str:
    delta_days = (dt.date() - now.date()).days
    time_str = dt.strftime("%H:%M")
    if delta_days == 0:
        return f"today at {time_str}"
    if delta_days == 1:
        return f"tomorrow at {time_str}"
    if delta_days == -1:
        return f"yesterday at {time_str}"
    if delta_days > 1:
        return f"in {delta_days} days at {time_str}"
    return f"{abs(delta_days)} days ago at {time_str}"


def _event_duration_str(start_dt: _DateTime, end_dt: _DateTime) -> str:
    seconds = int((end_dt - start_dt).total_seconds())
    if seconds <= 0:
        return "0m"
    if seconds < 60:
        return "<1m"
    base = _DateTime(1970, 1, 1, 0, 0, 0)
    end = base + _datetime.timedelta(seconds=seconds)
    rd = relativedelta(end, base)
    parts = []
    if rd.days:
        parts.append(f"{rd.days}d")
    if rd.hours:
        parts.append(f"{rd.hours}h")
    if rd.minutes:
        parts.append(f"{rd.minutes}m")
    return " ".join(parts) if parts else "0m"


def _duration_str(seconds: int) -> str:
    if seconds < 60:
        return "just now"
    base = _DateTime(1970, 1, 1, 0, 0, 0)
    end = base + _datetime.timedelta(seconds=seconds)
    rd = relativedelta(end, base)
    parts = []
    if rd.years:
        parts.append(f"{rd.years}y")
    if rd.months:
        parts.append(f"{rd.months}M")
    if rd.days:
        parts.append(f"{rd.days}d")
    if rd.hours:
        parts.append(f"{rd.hours}h")
    if rd.minutes:
        parts.append(f"{rd.minutes}m")
    return " ".join(parts)


def _relative_time(now_ts: int, start_ts: int) -> str:
    if now_ts < start_ts:
        delta = start_ts - now_ts
        if delta < 60:
            return "starting now"
        return f"in {_duration_str(delta)}"
    delta = now_ts - start_ts
    if delta < 60:
        return "started just now"
    return f"{_duration_str(delta)} ago"


def create_event(
    title: str,
    start_time: str,
    end_time: str | None = None,
    description: str | None = None,
    reminder_minutes_before: int = DEFAULT_REMINDER_MINUTES,
) -> dict:
    if _store is None:
        raise RuntimeError("Store not initialized")
    if not title or not isinstance(title, str):
        raise ValueError("title must be a non-empty string")

    start_ts = _parse_datetime(start_time)
    end_ts = _parse_datetime(end_time) if end_time else None
    reminder_offset = max(0, int(reminder_minutes_before)) * 60
    now = int(time.time())
    event_id = _generate_event_id()

    row = (
        event_id,
        title,
        description or "",
        start_ts,
        end_ts,
        reminder_offset,
        now,
        now,
        None,
    )
    with _store_lock:
        _store.execute(
            "INSERT INTO events(event_id, title, description, start_time, end_time, "
            "reminder_offset, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            row[:8],
        )

    return _format_event(row, _resolve_local_tz())


def create_events(events: list[dict]) -> int:
    if _store is None:
        raise RuntimeError("Store not initialized")
    if not events:
        return 0

    now = int(time.time())
    records = []
    for e in events:
        start_ts = _parse_datetime(e["start_time"])
        end_ts = _parse_datetime(e["end_time"]) if e.get("end_time") else None
        reminder_offset = max(0, int(e.get("reminder_minutes_before", DEFAULT_REMINDER_MINUTES))) * 60
        event_id = _generate_event_id()
        records.append(
            (
                event_id,
                e["title"],
                e.get("description", ""),
                start_ts,
                end_ts,
                reminder_offset,
                now,
                now,
            )
        )

    with _store_lock:
        _store.executemany(
            "INSERT INTO events(event_id, title, description, start_time, end_time, "
            "reminder_offset, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            records,
        )

    return len(records)


def _get_local_day_bounds(local_tz: _TzInfo, now_ts: int) -> tuple[int, int]:
    now_local = _DateTime.fromtimestamp(now_ts, tz=local_tz)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + _datetime.timedelta(days=1)
    return int(start_local.timestamp()), int(end_local.timestamp())


def fetch_events(filter: str = "upcoming", limit: int = 10) -> list[dict]:
    if _store is None:
        return []

    now = int(time.time())
    local_tz = _resolve_local_tz()
    limit = max(1, min(int(limit), 100))

    if filter == "upcoming":
        two_weeks = now + UPCOMING_LIMIT_DAYS * 86400
        rows = _store.execute(
            "SELECT * FROM events WHERE start_time > ? AND start_time <= ? "
            "AND completed_at IS NULL "
            "ORDER BY start_time ASC LIMIT ?",
            (now, two_weeks, limit),
        ).fetchall()
    elif filter == "past":
        rows = _store.execute(
            "SELECT * FROM events WHERE start_time <= ? "
            "AND completed_at IS NULL "
            "ORDER BY start_time DESC LIMIT ?",
            (now, limit),
        ).fetchall()
    elif filter == "today":
        day_start, day_end = _get_local_day_bounds(local_tz, now)
        rows = _store.execute(
            "SELECT * FROM events WHERE start_time >= ? AND start_time < ? "
            "AND completed_at IS NULL "
            "ORDER BY start_time ASC LIMIT ?",
            (day_start, day_end, limit),
        ).fetchall()
    else:
        rows = []

    return [_format_event(row, local_tz) for row in rows]


def fetch_event(event_id: str) -> dict | None:
    if _store is None:
        return None
    row = _store.execute(
        "SELECT * FROM events WHERE event_id = ?", (event_id,)
    ).fetchone()
    if row is None:
        return None
    return _format_event(row, _resolve_local_tz())


def modify_event(event_id: str, **fields) -> dict | None:
    if _store is None:
        return None

    updates: dict[str, object] = {}
    if "title" in fields:
        updates["title"] = fields["title"]
    if "description" in fields:
        updates["description"] = fields["description"]
    if "start_time" in fields:
        updates["start_time"] = _parse_datetime(fields["start_time"])
    if "end_time" in fields:
        if fields["end_time"] is None:
            updates["end_time"] = None
        else:
            updates["end_time"] = _parse_datetime(fields["end_time"])
    if "reminder_minutes_before" in fields:
        updates["reminder_offset"] = max(0, int(fields["reminder_minutes_before"])) * 60
    if "completed_at" in fields:
        if fields["completed_at"] is None:
            updates["completed_at"] = None
        else:
            raise ValueError(
                "completed_at can only be set to null (to unmark). "
                "Use mark_event_complete to mark an event as complete."
            )

    if not updates:
        return None

    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [event_id]

    with _store_lock:
        cur = _store.execute(f"UPDATE events SET {set_clause} WHERE event_id = ?", values)
        if cur.rowcount == 0:
            return None

    return fetch_event(event_id)


def remove_event(event_id: str) -> bool:
    if _store is None:
        return False
    with _store_lock:
        cur = _store.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
        return cur.rowcount > 0


def mark_event_complete(event_id: str) -> dict | None:
    if _store is None:
        return None
    with _store_lock:
        cur = _store.execute(
            "SELECT completed_at FROM events WHERE event_id = ?", (event_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        if row[0] is not None:
            return fetch_event(event_id)
        now = int(time.time())
        _store.execute(
            "UPDATE events SET completed_at = ?, updated_at = ? WHERE event_id = ?",
            (now, now, event_id),
        )
    return fetch_event(event_id)


def fetch_completed_events(limit: int = 10) -> list[dict]:
    if _store is None:
        return []
    local_tz = _resolve_local_tz()
    limit = max(1, min(int(limit), 100))
    rows = _store.execute(
        "SELECT * FROM events WHERE completed_at IS NOT NULL "
        "ORDER BY completed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_format_event(row, local_tz) for row in rows]


def cleanup_old_events(retention_days: int = EVENT_RETENTION_DAYS) -> int:
    if _store is None:
        return 0
    cutoff = int(time.time()) - retention_days * 86400
    with _store_lock:
        cur = _store.execute("DELETE FROM events WHERE start_time < ?", (cutoff,))
        return cur.rowcount


def get_active_events(now_ts: int) -> tuple[list[str], list[str]]:
    if _store is None:
        return [], []

    local_tz = _resolve_local_tz()
    rows = _store.execute(
        "SELECT title, start_time, end_time, reminder_offset FROM events "
        "WHERE start_time - reminder_offset <= ? AND start_time + ? >= ? "
        "AND completed_at IS NULL "
        "ORDER BY start_time ASC",
        (now_ts, ACTIVE_WINDOW_AFTER_START_SECONDS, now_ts),
    ).fetchall()

    upcoming: list[str] = []
    now_events: list[str] = []
    for title, start_ts, end_ts, _ in rows:
        parts = [title]
        if end_ts is not None:
            end_str = _DateTime.fromtimestamp(end_ts, tz=local_tz).strftime("%H:%M")
            parts.append(f"until {end_str}")
        parts.append(f"({_relative_time(now_ts, start_ts)})")
        line = " ".join(parts)
        if now_ts < start_ts:
            upcoming.append(line)
        else:
            now_events.append(line)

    return upcoming, now_events
