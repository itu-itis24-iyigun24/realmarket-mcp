"""Turn a tool's period arguments into a concrete, inclusive date range."""

from __future__ import annotations

import calendar
import datetime as dt
from typing import Literal

from realmarket_mcp.contract import ErrorCode, ToolError

Period = Literal["1m", "3m", "6m", "ytd", "1y", "3y", "5y", "10y", "max"]

EARLIEST = dt.date(1900, 1, 1)
_MONTHS = {"1m": 1, "3m": 3, "6m": 6, "1y": 12, "3y": 36, "5y": 60, "10y": 120}


def _months_before(day: dt.date, months: int) -> dt.date:
    year, month_index = divmod(day.year * 12 + day.month - 1 - months, 12)
    month = month_index + 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def parse_date(value: str, name: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT,
            f"{name}={value!r} is not a valid date.",
            f"Pass {name} as an ISO-8601 date, for example '2024-01-31'.",
            {name: value},
        ) from None


def resolve(
    period: Period, start: str | None, end: str | None, *, today: dt.date
) -> tuple[dt.date, dt.date]:
    """Explicit ``start`` wins over ``period``; ``end`` defaults to ``today``."""
    end_date = parse_date(end, "end") if end else today
    if end_date > today:
        end_date = today
    if start:
        start_date = parse_date(start, "start")
    elif period == "max":
        start_date = EARLIEST
    elif period == "ytd":
        start_date = dt.date(end_date.year, 1, 1)
    else:
        start_date = _months_before(end_date, _MONTHS[period])
    if start_date >= end_date:
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT,
            f"start {start_date} is not before end {end_date}.",
            "Use a start date earlier than the end date, or omit start and pass a period.",
            {"start": start_date.isoformat(), "end": end_date.isoformat()},
        )
    return start_date, end_date
