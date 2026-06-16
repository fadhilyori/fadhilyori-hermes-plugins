from __future__ import annotations

import datetime as _datetime
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from datetime import time as t
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import humanize
from dateutil.relativedelta import relativedelta
from tzlocal import get_localzone

logger = logging.getLogger(__name__)

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

DB_FILENAME = "sessions.db"
BUSY_TIMEOUT_MS = 10000
DEFAULT_REMINDER_MINUTES = 5
EVENT_RETENTION_DAYS = 30
ACTIVE_WINDOW_AFTER_START_SECONDS = 1800
UPCOMING_LIMIT_DAYS = 14
DEFAULT_EVENT_DURATION_SECONDS = 3600

_store: sqlite3.Connection | None = None
_store_lock = threading.Lock()


@dataclass
class EventSchema():
    id: str = field(init=False)
    title: str
    description: str | None
    start_time: datetime
    end_time: datetime | None
    reminder_offset: int = 0
    completed_at: datetime | None = field(init=False)
    created_at: datetime | None = field(init=False)
    updated_at: datetime | None = field(init=False)

    def __post_init__(self):
        now, _ = get_current_time()
        self.id = str(uuid.uuid4())
        self.completed_at = None
        self.created_at = now
        self.updated_at = now

    @property
    def start_in(self):
        now, _ = get_current_time()
        return humanize.naturaltime(self.start_time - now)

    @property
    def end_in(self):
        now, _ = get_current_time()

        if not self.end_time:
            end_time = self.start_time + timedelta(seconds=DEFAULT_EVENT_DURATION_SECONDS)
            return humanize.naturaltime(end_time - now)

        return humanize.naturaltime(self.end_time - now)

    @property
    def reminder_offset_minutes(self):
        return self.reminder_offset // 60

    @property
    def is_time_to_remind(self):
        now, _ = get_current_time()

        return self.reminder_offset and self.start_time - timedelta(seconds=self.reminder_offset) < now

    @property
    def duration_humanized(self):
        if not self.end_time:
            return humanize.naturaldelta(timedelta(seconds=DEFAULT_EVENT_DURATION_SECONDS))
        return humanize.naturaldelta(self.end_time - self.start_time)

def eventschema_factory(cursor, row) -> EventSchema:
    columns = [col[0] for col in cursor.description]

    row_dict = dict(zip(columns, row))

    return EventSchema(**row_dict)


def _resolve_local_tz() -> _TzInfo:
    tz = os.environ.get("TZ")
    if tz:
        try:
            return ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            pass
    return _DateTime.now().astimezone().tzinfo or _datetime.timezone.utc


def _open_store() -> sqlite3.Connection:
    path = os.path.join(PLUGIN_DIR, DB_FILENAME)
    sqlite3.register_adapter(datetime, lambda dt: dt.timestamp())
    sqlite3.register_converter(
        "TIMESTAMP", lambda ts: datetime.fromtimestamp(float(ts), tz=timezone.utc))
    conn = sqlite3.connect(
        path,
        timeout=BUSY_TIMEOUT_MS / 1000.0,
        check_same_thread=False,
        detect_types=sqlite3.PARSE_DECLTYPES,
    )
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, updated_at TIMESTAMP NOT NULL)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        "id TEXT PRIMARY KEY, "
        "title TEXT NOT NULL, "
        "description TEXT DEFAULT '', "
        "start_time TIMESTAMP NOT NULL, "
        "end_time TIMESTAMP, "
        "reminder_offset INTEGER NOT NULL DEFAULT 300, "
        "completed_at TIMESTAMP, "
        "created_at TIMESTAMP NOT NULL, "
        "updated_at TIMESTAMP NOT NULL)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_start_time ON events(start_time)"
    )
    conn.commit()
    return conn


def init_store() -> None:
    global _store
    _store = _open_store()
    deleted = cleanup_old_events()
    if deleted > 0:
        logger.info("cleaned up %d old events at startup", deleted)


def close_store() -> None:
    global _store
    if _store is not None:
        _store.close()
        _store = None


def touch_session(session_id: str, now: datetime) -> tuple[datetime, timedelta | None]:
    if _store is None or not session_id:
        logger.debug("no store or no session_id, skipping touch")
        return now, None

    cursor: sqlite3.Cursor = _store.cursor()

    with _store_lock:
        # Fetch last touch time for this session
        row = cursor.execute(
            "SELECT updated_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        time_diff = now - row[0] if row else None

        # Update the session's touch time
        cursor.execute(
            "INSERT INTO sessions(id, updated_at) VALUES(?, ?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at",
            (session_id, now),
        )
        _store.commit()

        return now, time_diff


def _parse_datetime_(dt_str: str) -> int:
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


def _format_relativedelta(rd: relativedelta) -> str:
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
    return " ".join(parts) if parts else "<1m"


def fmt_duration(prior_ts: int, now_ts: int) -> str:
    delta = now_ts - prior_ts

    if delta <= 0:
        return "0m"
    if delta < 60:
        return "<1m"

    rd = relativedelta(
        _DateTime.fromtimestamp(now_ts), _DateTime.fromtimestamp(prior_ts)
    )
    return _format_relativedelta(rd)


# def _format_event(row: EventSchema) -> dict:
#     now, _ = get_current_time()

#     result = {
#         "event_id": row.event_id,
#         "title": row.title,
#         "description": row.description,
#         "start_time": f"{row.start_time.strftime('%Y-%m-%d %H:%M %Z')} ({humanize.naturaltime(now - row.start_time)})",
#         "reminder_minutes_before": row.reminder_offset // 60,
#         "duration_minutes": (
#             (row.end_time - row.start_time) // 60
#             if row.end_time is not None
#             else DEFAULT_EVENT_DURATION_SECONDS // 60
#         ),
#         "completed": row.completed_at is not None,
#         "completed_at": (
#             row.completed_at
#             if row.completed_at is not None
#             else None
#         ),
#     }
#     if row.end_time is not None:
#         result["end_time"] = (
#             f"{row.end_time.strftime('%Y-%m-%d %H:%M %Z')} "
#             f"({humanize.naturaldelta(row.end_time - row.start_time)})"
#         )
#     return result


def create_event(
    event: EventSchema
) -> EventSchema:
    if _store is None:
        raise RuntimeError("Store not initialized")

    now, _ = get_current_time()

    with _store_lock:
        cursor: sqlite3.Cursor = _store.cursor()

        cursor.execute(
            "INSERT INTO events(id, title, description, start_time, end_time, "
            "reminder_offset, completed_at, created_at, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event.id, event.title, event.description, event.start_time,
             event.end_time, event.reminder_offset, event.completed_at, now, now),
        )
        _store.commit()

    return event


def create_events(events: list[EventSchema]) -> int:
    if _store is None:
        raise RuntimeError("Store not initialized")

    if not events:
        return 0

    now, _ = get_current_time()

    records = [(e.id, e.title, e.description, e.start_time, e.end_time, e.reminder_offset, now, now) for e in events]

    with _store_lock:
        _store.executemany(
            "INSERT INTO events(event_id, title, description, start_time, end_time, "
            "reminder_offset, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            records,
        )
    return len(records)


def fetch_events(filter: str = "upcoming", limit: int = 10) -> list[dict]:
    if _store is None:
        return []

    _store.row_factory = eventschema_factory

    cursor: sqlite3.Cursor = _store.cursor()

    now, _ = get_current_time()
    limit = max(1, min(int(limit), 100))

    if filter == "upcoming":
        rows = cursor.execute(
            "SELECT * FROM events WHERE start_time > ? AND start_time <= ? "
            "AND completed_at IS NULL "
            "ORDER BY start_time ASC LIMIT ?",
            (now, timedelta(weeks=2), limit),
        ).fetchall()
    elif filter == "past":
        rows = cursor.execute(
            "SELECT * FROM events WHERE start_time <= ? "
            "AND completed_at IS NULL "
            "ORDER BY start_time DESC LIMIT ?",
            (now, limit),
        ).fetchall()
    elif filter == "today":
        start_time = datetime.combine(now, t.min)
        end_time = datetime.combine(now, t.max)
        rows = _store.execute(
            "SELECT * FROM events WHERE start_time >= ? AND start_time < ? "
            "AND completed_at IS NULL "
            "ORDER BY start_time ASC LIMIT ?",
            (start_time, end_time, limit),
        ).fetchall()
    else:
        rows = []

    return [_format_event(row, local_tz, now) for row in rows]


def fetch_event(event_id: str) -> dict | None:
    if _store is None:
        return None

    cursor: sqlite3.Cursor = _store.cursor()

    row = cursor.execute(
        "SELECT * FROM events WHERE event_id = ?", (event_id,)
    ).fetchone()

    if row is None:
        return None

    return _format_event(row, _resolve_local_tz(), int(time.time()))


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
        updates["reminder_offset"] = max(
            0, int(fields["reminder_minutes_before"])) * 60
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

    now, _ = get_current_time()

    updates["updated_at"] = now
    set_clause = ", ".join(f"{k} = ?" for k in updates)

    values = list(updates.values()) + [event_id]

    cursor: sqlite3.Cursor = _store.cursor()

    with _store_lock:
        cur = cursor.execute(
            f"UPDATE events SET {set_clause} WHERE event_id = ?", values
        )
        _store.commit()

        if cur.rowcount == 0:
            return None

        return fetch_event(event_id)


def remove_event(event_id: str) -> bool:
    if _store is None:
        return False

    cursor: sqlite3.Cursor = _store.cursor()

    with _store_lock:
        cur = cursor.execute(
            "DELETE FROM events WHERE event_id = ?", (event_id,))
        _store.commit()

        return cur.rowcount > 0


def get_current_time():
    tz_name = str(get_localzone())
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)

    return now, tz


def mark_event_complete(event_id: str) -> dict | None:
    if _store is None:
        return None

    cursor: sqlite3.Cursor = _store.cursor()

    with _store_lock:
        row = cursor.execute(
            "SELECT completed_at FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()

        if row is None:
            return None

        if row[0] is not None:
            return fetch_event(event_id)

        now, _ = get_current_time()

        cursor.execute(
            "UPDATE events SET completed_at = ?, updated_at = ? WHERE event_id = ?",
            (now, now, event_id),
        )
        _store.commit()

        return fetch_event(event_id)


def fetch_completed_events(filter: str = "upcoming", limit: int = 10) -> list[dict]:
    if _store is None:
        return []
    local_tz = _resolve_local_tz()
    limit = max(1, min(int(limit), 100))
    now = int(time.time())

    if filter == "upcoming":
        rows = _store.execute(
            "SELECT * FROM events WHERE completed_at IS NOT NULL "
            "AND completed_at >= ? "
            "ORDER BY completed_at DESC LIMIT ?",
            (now, limit),
        ).fetchall()
    elif filter == "past":
        rows = _store.execute(
            "SELECT * FROM events WHERE completed_at IS NOT NULL "
            "AND completed_at < ? "
            "ORDER BY completed_at DESC LIMIT ?",
            (now, limit),
        ).fetchall()
    elif filter == "today":
        day_start, day_end = _get_local_day_bounds(local_tz, now)
        rows = _store.execute(
            "SELECT * FROM events WHERE completed_at IS NOT NULL "
            "AND completed_at >= ? AND completed_at < ? "
            "ORDER BY completed_at DESC LIMIT ?",
            (day_start, day_end, limit),
        ).fetchall()
    else:
        rows = []

    return [_format_event(row, local_tz, now) for row in rows]


def _parse_date_range(start_date: str, end_date: str | None) -> tuple[int, int]:
    """Parse 'YYYY-MM-DD' inputs to (start_ts, end_ts_exclusive) in local time.

    end_date is inclusive: the returned end_ts is start of the day after
    end_date, so the range can be used directly as [start, end) in SQL.
    """
    if not start_date:
        raise ValueError("start_date is required")
    start_ts = _parse_datetime(start_date)
    if not end_date:
        return start_ts, start_ts + 86400
    end_ts = _parse_datetime(end_date)
    if end_ts < start_ts:
        raise ValueError(
            f"end_date ({end_date}) must be on or after start_date ({start_date})"
        )
    end_local_next = _DateTime.fromtimestamp(
        end_ts, tz=_resolve_local_tz()
    ) + _datetime.timedelta(days=1)
    return start_ts, int(end_local_next.timestamp())


def fetch_events_by_range(start_ts: int, end_ts: int, limit: int = 100) -> list[dict]:
    """Return active events overlapping [start_ts, end_ts).

    An event is included if its start_time is before end_ts AND
    (end_time is null OR end_time is after start_ts). Events without
    completed_at only. Sorted ascending by start_time.
    """
    if _store is None:
        return []
    limit = max(1, min(int(limit), 100))
    local_tz = _resolve_local_tz()
    rows = _store.execute(
        "SELECT * FROM events WHERE completed_at IS NULL "
        "AND start_time < ? AND (end_time IS NULL OR end_time > ?) "
        "ORDER BY start_time ASC LIMIT ?",
        (end_ts, start_ts, limit),
    ).fetchall()
    return [_format_event(row, local_tz, int(time.time())) for row in rows]


def fetch_completed_events_by_range(
    start_ts: int, end_ts: int, limit: int = 100
) -> list[dict]:
    """Return completed events whose completed_at falls in [start_ts, end_ts)."""
    if _store is None:
        return []
    limit = max(1, min(int(limit), 100))
    local_tz = _resolve_local_tz()
    rows = _store.execute(
        "SELECT * FROM events WHERE completed_at IS NOT NULL "
        "AND completed_at >= ? AND completed_at < ? "
        "ORDER BY completed_at DESC LIMIT ?",
        (start_ts, end_ts, limit),
    ).fetchall()
    return [_format_event(row, local_tz, int(time.time())) for row in rows]


def cleanup_old_events(retention_days: int = 30) -> int:
    """Remove old events older than retention_days

    Args:
        retention_days (int, optional): Retention days. Defaults to 30 days.

    Returns:
        int: Number of events deleted.
    """
    if _store is None:
        return 0

    cutoff = int(time.time()) - retention_days * 86400

    cursor: sqlite3.Cursor = _store.cursor()

    with _store_lock:
        cur = cursor.execute(
            "DELETE FROM events WHERE start_time < ?", (cutoff,))
        return cur.rowcount


def get_active_events(now: datetime) -> tuple[list[str], list[str]]:
    if _store is None:
        logger.warning("database connection is not initialized")
        return [], []

    # Get timezone from now datetime object
    tz = now.tzinfo

    cursor: sqlite3.Cursor = _store.cursor()

    rows = cursor.execute(
        "SELECT title, start_time, end_time, reminder_offset FROM events "
        "WHERE ("
        "  (start_time - reminder_offset <= ? AND start_time + ? >= ?)"
        "  OR (end_time IS NOT NULL AND start_time <= ? AND end_time >= ?)"
        ") "
        "AND completed_at IS NULL "
        "ORDER BY start_time ASC",
        (now, ACTIVE_WINDOW_AFTER_START_SECONDS, now, now, now),
    ).fetchall()

    upcoming: list[str] = []
    now_events: list[str] = []

    for title, start_dt, end_dt, _ in rows:
        parts = [title]

        if end_dt is not None:
            end_str = end_dt.astimezone(tz).strftime("%H:%M")
            parts.append(f"until {end_str}")

        parts.append(
            f"({humanize.naturaltime(now - start_dt.astimezone(tz))})")
        line = " ".join(parts)

        if now < start_dt:
            upcoming.append(line)
        else:
            now_events.append(line)

    return upcoming, now_events
