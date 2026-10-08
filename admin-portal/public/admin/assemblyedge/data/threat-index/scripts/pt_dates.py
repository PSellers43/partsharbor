"""Pacific Time dates for MajorityIQ static bundles."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")


def today_pt() -> date:
    return datetime.now(PT).date()


def now_pt_iso() -> str:
    return datetime.now(PT).replace(microsecond=0).isoformat()
