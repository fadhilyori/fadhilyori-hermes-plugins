from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

def _build_context(now: datetime, tz_name: str) -> str:
    offset = now.strftime("%z")
    return (
        f"{now.strftime('%Y-%m-%dT%H:%M')}{offset[:3]}:{offset[3:]} "
        f"{now.strftime('%a')} {tz_name}"
    )


def inject_context(**kwargs) -> dict:
    try:
        from tzlocal import get_localzone

        tz_name = str(get_localzone())
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
    except ImportError:
        logger.warning("tzlocal is not installed, ")
        now = datetime.now().astimezone()
        tz_name = now.tzname() or ""

    return {"context": _build_context(now, tz_name)}
