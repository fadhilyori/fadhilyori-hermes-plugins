from __future__ import annotations

import logging
from datetime import datetime

from hermes_time import get_timezone, now

logger = logging.getLogger(__name__)


def _build_context(now: datetime, tz_name: str) -> str:
    offset = now.strftime("%z")
    return (
        f"{now.strftime('%Y-%m-%dT%H:%M')}{offset[:3]}:{offset[3:]} "
        f"{now.strftime('%a')} {tz_name}"
    )


def inject_context(**kwargs) -> dict:
    try:
        tz = get_timezone()
        if tz is None:
            now_dt = now()
            tz_name = now_dt.tzname() or "local"
        else:
            now_dt = datetime.now(tz)
            tz_name = str(tz)
    except Exception:
        logger.warning("hermes_time unavailable; falling back to system local time")
        now_dt = datetime.now().astimezone()
        tz_name = now_dt.tzname() or "local"
    return {"context": _build_context(now_dt, tz_name)}
