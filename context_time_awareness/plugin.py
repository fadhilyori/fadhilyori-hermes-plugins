from __future__ import annotations

import logging
import os
import datetime as _datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import store

logger = logging.getLogger(__name__)


def _now() -> _datetime.datetime:
    tz = os.environ.get("TZ")
    if tz:
        try:
            return _datetime.datetime.now(ZoneInfo(tz))
        except ZoneInfoNotFoundError:
            pass
    return _datetime.datetime.now().astimezone()


def _time_since_str(prior: int, now: int) -> str:
    if prior <= 0:
        return ""
    delta = now - prior
    if delta < 60:
        return "Time since last user message: just now"
    return f"Time since last user message: {store.fmt_duration(prior, now)}"


def _build_context(
    now: _datetime.datetime,
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


def _inject_context(session_id: str = "", **kwargs) -> dict:
    now = _now()
    ts = int(now.timestamp())
    tz_name = now.tzname() or "UTC"

    time_since = ""
    if session_id:
        prior = store.touch_session(session_id, ts)
        if prior is not None:
            time_since = _time_since_str(prior, ts)

    upcoming, now_events = store.get_active_events(ts)
    return {
        "context": _build_context(now, tz_name, time_since, upcoming, now_events)
    }
