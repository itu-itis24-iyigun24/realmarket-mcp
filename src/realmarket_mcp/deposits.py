"""Turkish lira deposit returns from the central bank's published deposit rates.

The comparison a Turkish saver actually faces is not "stock vs index" but "stock vs keeping the
money in a deposit account". TCMB publishes, every Friday, the weighted average annual interest
rate banks paid on new TL deposits in that week, by maturity (EVDS data group `bie_mt100h`,
verified 2026-09-27). This module models the common product: a 32-day deposit opened at the rate
most recently published, earning simple interest for its term (ACT/365), and renewed at maturity
— principal plus interest — at the rate then in force. A final partial term earns pro rata.

Two simplifications, both stated in every result that uses it: the rate is **gross** — the
withholding tax on deposit interest (stopaj), whose rate has changed many times, is not
deducted — and a real account earns its own bank's rate, which can differ from the average.
"""

from __future__ import annotations

import bisect
import datetime as dt
import hashlib
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass

# Rates are published weekly, about a week after the week they describe. A rate is carried
# forward at most this long; beyond it the series is treated as ended (never extrapolated).
MAX_CARRY_DAYS = 21
TERM_DAYS = 32  # the usual shortest TL deposit term


@dataclass(frozen=True)
class DepositRates:
    currency: str
    source: str
    series_id: str
    retrieved_at: str
    observations: tuple[tuple[dt.date, float], ...]  # (week date, annual rate in percent)

    def __post_init__(self) -> None:
        if not self.observations:
            raise ValueError("a deposit rate series needs at least one observation")
        for day, rate in self.observations:
            if not math.isfinite(rate) or not 0 <= rate < 1000:
                raise ValueError(f"implausible deposit rate {rate} on {day}")

    @property
    def first_date(self) -> dt.date:
        return self.observations[0][0]

    @property
    def covered_until(self) -> dt.date:
        return self.observations[-1][0] + dt.timedelta(days=MAX_CARRY_DAYS)

    @property
    def data_version(self) -> str:
        payload = [[d.isoformat(), r] for d, r in self.observations]
        text = json.dumps([self.series_id, payload], separators=(",", ":"))
        return "sha256:" + hashlib.sha256(text.encode()).hexdigest()

    def growth(
        self,
        start: dt.date,
        end: dt.date,
        withholding: Callable[[dt.date], float | None] | None = None,
    ) -> float | None:
        """Value of 1 unit deposited on ``start`` and held to ``end`` (interest from the day
        after ``start`` through ``end``), or None when the series does not cover the span.
        ``withholding(opening_day)`` gives the tax rate (a fraction) deducted from each term's
        interest; None from it means the rate is not known, so no net figure."""
        if end <= start:
            return 1.0
        if start < self.first_date or end > self.covered_until:
            return None
        dates = [d for d, _ in self.observations]
        value = 1.0
        day = start
        while day < end:
            published, rate = self.observations[bisect.bisect_right(dates, day) - 1]
            if (day - published).days > MAX_CARRY_DAYS:  # a gap inside the series
                return None
            # the rate is fixed at opening for the whole term
            days = min(TERM_DAYS, (end - day).days)
            tax = 0.0 if withholding is None else withholding(day)
            if tax is None:
                return None
            value *= 1.0 + rate / 100.0 * days / 365.0 * (1.0 - tax)
            day += dt.timedelta(days=days)
        return value


DepositLoader = Callable[[str, dt.date, dt.date], DepositRates]


def rates_from_rows(
    rows: Iterable[tuple[str, str]],
    *,
    currency: str,
    source: str,
    series_id: str,
    retrieved_at: str,
) -> DepositRates:
    """Rows of (dd-mm-yyyy, percent); empty values are skipped, never filled."""
    observations = []
    for day, value in rows:
        if not str(value).strip():
            continue
        parsed = dt.datetime.strptime(day, "%d-%m-%Y").date()
        observations.append((parsed, float(value)))
    observations.sort()
    return DepositRates(currency, source, series_id, retrieved_at, tuple(observations))
