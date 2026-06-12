from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import request


def local_today():
    """The current date where the visitor is, based on the IANA timezone
    the browser stores in the `tz` cookie. Falls back to the server's
    (UTC) date when the cookie is missing or invalid."""
    tz_name = request.cookies.get("tz", "")
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)).date().isoformat()
        except Exception:
            pass
    return date.today().isoformat()
