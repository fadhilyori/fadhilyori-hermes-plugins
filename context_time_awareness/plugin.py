from __future__ import annotations

import logging
import os
import datetime as _datetime
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import store

_DateTime = _datetime.datetime
_TzInfo = _datetime.tzinfo

logger = logging.getLogger(__name__)

_last_cleanup_ts = 0


def _resolve_location() -> tuple[_TzInfo, str]:
    tz = os.environ.get("TZ")
    if tz:
        try:
            return ZoneInfo(tz), tz
        except ZoneInfoNotFoundError:
            pass
    local_tz = _DateTime.now().astimezone().tzinfo or _datetime.timezone.utc
    return local_tz, str(local_tz)


def _now() -> _DateTime:
    loc, _ = _resolve_location()
    return _DateTime.now(loc)


def _time_since_str(prior: int, now: int) -> str:
    if prior <= 0:
        return ""
    start = _DateTime.fromtimestamp(prior)
    end = _DateTime.fromtimestamp(now)
    rd = relativedelta(end, start)
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
    if not parts:
        return "Time since last user message: just now"
    return "Time since last user message: " + " ".join(parts)


def _maybe_cleanup(now_ts: int) -> None:
    global _last_cleanup_ts
    if now_ts - _last_cleanup_ts < store.CLEANUP_INTERVAL_SECONDS:
        return
    try:
        deleted = store.cleanup_old_events()
        logger.info("cleaned up %d old events", deleted)
        _last_cleanup_ts = now_ts
    except Exception:
        logger.exception("failed to cleanup old events")


def _build_context(
    now: _DateTime,
    tz_name: str,
    time_since: str,
    upcoming: list[str],
    now_events: list[str],
) -> str:
    msg = (
        f"Current local time: {now.strftime('%Y-%m-%d %H:%M %Z')} "
        f"({now.strftime('%A')}, {tz_name})"
    )
    if time_since:
        msg += "\n" + time_since
    if upcoming:
        msg += "\nUpcoming:\n" + "\n".join(f"- {line}" for line in upcoming)
    if now_events:
        msg += "\nNow:\n" + "\n".join(f"- {line}" for line in now_events)
    return msg


def _inject_context(
    session_id: str = "",
    user_message=None,
    conversation_history: list[dict]=[],
    is_first_turn: bool = False,
    model: str = "",
    platform: str = "",
    **kwargs,
) -> dict:
    loc, tz_name = _resolve_location()
    now_dt = _now()
    ts = int(now_dt.timestamp())

    time_since = ""
    if session_id:
        prior = store.touch_session(session_id, ts)
        if prior is not None:
            time_since = _time_since_str(prior, ts)

    upcoming, now_events = store.get_active_events(ts)
    _maybe_cleanup(ts)

    return {
        "context": _build_context(now_dt, tz_name, time_since, upcoming, now_events)
    }
