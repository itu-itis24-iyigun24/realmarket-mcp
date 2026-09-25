"""Pure metric functions. No I/O, no provider knowledge; every figure is hand-checkable.

Conventions (also published in the methodology resource):

* Returns are simple returns on the provider's (adjusted) close: ``last / first - 1``.
* Annualized return compounds over calendar time: ``(1 + r) ** (365.25 / days) - 1``.
* Volatility is the sample standard deviation of daily log returns times ``sqrt(252)``.
* Max drawdown is the largest peak-to-trough fall of the close, as a negative fraction.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

TRADING_DAYS_PER_YEAR = 252
DAYS_PER_YEAR = 365.25
# Below this span an annualized figure mostly extrapolates noise, so it is withheld.
MIN_DAYS_TO_ANNUALIZE = 180


@dataclass(frozen=True)
class Drawdown:
    depth: float
    peak_date: dt.date
    trough_date: dt.date


def total_return(first: float, last: float) -> float:
    if first <= 0:
        raise ValueError("first price must be positive")
    return last / first - 1.0


def annualized_return(total: float, start: dt.date, end: dt.date) -> float | None:
    days = (end - start).days
    if days < MIN_DAYS_TO_ANNUALIZE or total <= -1.0:
        return None
    return float((1.0 + total) ** (DAYS_PER_YEAR / days) - 1.0)


def annualized_volatility(closes: Sequence[float]) -> float | None:
    if len(closes) < 3:
        return None
    logs = [math.log(b / a) for a, b in itertools.pairwise(closes)]
    mean = math.fsum(logs) / len(logs)
    variance = math.fsum((x - mean) ** 2 for x in logs) / (len(logs) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS_PER_YEAR)


def max_drawdown(dates: Sequence[dt.date], closes: Sequence[float]) -> Drawdown | None:
    if len(closes) < 2:
        return None
    peak_value, peak_date = closes[0], dates[0]
    worst = Drawdown(0.0, dates[0], dates[0])
    for date, close in zip(dates, closes, strict=True):
        if close > peak_value:
            peak_value, peak_date = close, date
        depth = close / peak_value - 1.0
        if depth < worst.depth:
            worst = Drawdown(depth, peak_date, date)
    return worst


def real_return(nominal: float, inflation: float) -> float:
    """Fisher relation: deflate a nominal return by cumulative inflation over the same period."""
    if inflation <= -1.0:
        raise ValueError("cumulative inflation must be greater than -100%")
    return (1.0 + nominal) / (1.0 + inflation) - 1.0
