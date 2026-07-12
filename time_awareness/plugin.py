from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from tzlocal import get_localzone


def _build_context(now: datetime, tz_name: str) -> str:
    offset = now.strftime("%z")
    return (
        f"{now.strftime('%Y-%m-%dT%H:%M')}{offset[:3]}:{offset[3:]} "
        f"{now.strftime('%a')} {tz_name}"
    )


def inject_context(**kwargs) -> dict:
    try:
        tz_name = str(get_localzone())
        tz = ZoneInfo(tz_name)
    except Exception:
        tz_name = "UTC"
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    return {"context": _build_context(now, tz_name)}
