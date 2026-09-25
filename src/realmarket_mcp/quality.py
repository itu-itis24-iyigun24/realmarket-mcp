"""Data-quality checks. They flag problems; they never modify the data."""

from __future__ import annotations

import datetime as dt
import itertools
import math

from realmarket_mcp.contract import QualityFlag, Severity
from realmarket_mcp.models import PriceSeries

GAP_CALENDAR_DAYS = 10
SEAM_ABS_LOG_MOVE = 0.5  # |ln(close_t / close_t-1)| above this: ~ -39% / +65% in one session
STALE_CALENDAR_DAYS = 7


def _usable_close(close: float | None) -> bool:
    return close is not None and math.isfinite(close) and close > 0


def check_series(series: PriceSeries, *, requested_end: dt.date | None = None) -> list[QualityFlag]:
    flags: list[QualityFlag] = []
    bars = series.bars
    if not bars:
        return [QualityFlag("no_bars", Severity.CRITICAL, f"{series.symbol}: no bars in period")]

    missing_close = [b.date.isoformat() for b in bars if not _usable_close(b.close)]
    if missing_close:
        flags.append(
            QualityFlag(
                "missing_close",
                Severity.WARNING,
                f"{series.symbol}: {len(missing_close)} bar(s) without a usable close were skipped",
                tuple(missing_close[:20]),
            )
        )

    placeholder = [
        b.date.isoformat()
        for b in bars
        if b.volume == 0 and b.close is not None and b.open == b.high == b.low == b.close
    ]
    if placeholder:
        flags.append(
            QualityFlag(
                "placeholder_bars",
                Severity.INFO,  # padded holidays repeat a price; they do not change returns
                f"{series.symbol}: {len(placeholder)} zero-volume flat bar(s), "
                "typically holidays padded by the provider; they do not affect the figures",
                tuple(placeholder[:20]),
            )
        )

    usable = [b for b in bars if _usable_close(b.close)]
    for prev, cur in itertools.pairwise(usable):
        gap = (cur.date - prev.date).days
        if gap > GAP_CALENDAR_DAYS:
            flags.append(
                QualityFlag(
                    "gap",
                    Severity.WARNING,
                    f"{series.symbol}: no usable bars for {gap} calendar days",
                    (prev.date.isoformat(), cur.date.isoformat()),
                )
            )
        assert prev.close is not None and cur.close is not None
        move = math.log(cur.close / prev.close)
        if abs(move) > SEAM_ABS_LOG_MOVE:
            flags.append(
                QualityFlag(
                    "suspicious_move",
                    Severity.CRITICAL,
                    f"{series.symbol}: close moved {math.exp(move) - 1:+.1%} in one session; "
                    "possibly an unadjusted split, redenomination or provider error",
                    (prev.date.isoformat(), cur.date.isoformat()),
                )
            )

    if requested_end is not None and usable:
        lag = (requested_end - usable[-1].date).days
        if lag > STALE_CALENDAR_DAYS:
            flags.append(
                QualityFlag(
                    "stale",
                    Severity.WARNING,
                    f"{series.symbol}: latest usable bar is {lag} days before the requested end",
                    (usable[-1].date.isoformat(),),
                )
            )
    return flags
