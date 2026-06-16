from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import humanize
from tzlocal import get_localzone

from . import store

logger = logging.getLogger(__name__)


def _build_context(
    now: datetime,
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
    tz_name = str(get_localzone())
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)

    time_since = ""

    if session_id:
        now, time_diff = store.touch_session(session_id, now)
        if time_diff is not None:
            time_since = (
                f"Time since last user message: {humanize.naturaltime(time_diff)}"
            )

    upcoming, now_events = store.get_active_events(now)
    return {"context": _build_context(now, tz_name, time_since, upcoming, now_events)}
