"""Tool implementations: arguments in, contract envelope out. No MCP types in this module.

Each function here is what the tests target; ``server.py`` only registers and serializes them.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json

from realmarket_mcp import analytics, quality
from realmarket_mcp.contract import ErrorCode, Provenance, ToolError, ToolResult
from realmarket_mcp.models import PriceSeries
from realmarket_mcp.periods import Period, resolve
from realmarket_mcp.providers.base import PriceProvider

MAX_SEARCH_RESULTS = 25


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def _provenance(series: PriceSeries, start: dt.date, end: dt.date) -> Provenance:
    return Provenance(
        provider=series.provider,
        dataset="daily_bars",
        symbols=(series.symbol,),
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        retrieved_at=series.retrieved_at,
        data_version=series.data_version,
        adjustment=series.adjustment,
    )


def search_assets(
    provider: PriceProvider, query: str, limit: int, *, today: dt.date, retrieved_at: str
) -> ToolResult:
    query = query.strip()
    if not query:
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT,
            "query is empty.",
            "Pass a company name, index name or ticker, for example 'Turkish Airlines'.",
        )
    limit = max(1, min(limit, MAX_SEARCH_RESULTS))
    hits = provider.search(query, limit)
    results = [asset.to_dict() for asset in hits]
    digest = hashlib.sha256(json.dumps(results, sort_keys=True).encode()).hexdigest()
    return ToolResult(
        tool="search_assets",
        data={"query": query, "results": results},
        provenance=(
            Provenance(
                provider=provider.name,
                dataset="asset_search",
                symbols=tuple(asset.symbol for asset in hits),
                period_start=today.isoformat(),
                period_end=today.isoformat(),
                retrieved_at=retrieved_at,
                data_version="sha256:" + digest,
                adjustment="none",
            ),
        ),
        notes=() if hits else ("No match. Try the full company name or the exchange ticker.",),
    )


def get_price_summary(
    provider: PriceProvider,
    symbol: str,
    period: Period = "1y",
    start: str | None = None,
    end: str | None = None,
    *,
    today: dt.date,
) -> ToolResult:
    start_date, end_date = resolve(period, start, end, today=today)
    series = provider.daily_bars(symbol, start_date, end_date)
    flags = quality.check_series(series, requested_end=end_date)
    usable = [b for b in series.bars if b.close is not None and b.close > 0]
    if len(usable) < 2:
        raise ToolError(
            ErrorCode.NO_DATA_IN_RANGE,
            f"{symbol} has {len(usable)} usable daily bar(s) between {start_date} and {end_date}.",
            "Widen the period (for example period='5y' or 'max') "
            "or check the symbol's listing date.",
            {"symbol": symbol, "start": start_date.isoformat(), "end": end_date.isoformat()},
        )

    dates = [b.date for b in usable]
    closes = [b.close for b in usable if b.close is not None]
    total = analytics.total_return(closes[0], closes[-1])
    drawdown = analytics.max_drawdown(dates, closes)
    return ToolResult(
        tool="get_price_summary",
        data={
            "symbol": symbol,
            "currency": series.currency,
            "requested_start": start_date.isoformat(),
            "requested_end": end_date.isoformat(),
            "first_date": dates[0].isoformat(),
            "last_date": dates[-1].isoformat(),
            "sessions": len(usable),
            "first_close": _round(closes[0]),
            "last_close": _round(closes[-1]),
            "total_return": _round(total),
            "annualized_return": _round(analytics.annualized_return(total, dates[0], dates[-1])),
            "annualized_volatility": _round(analytics.annualized_volatility(closes)),
            "max_drawdown": _round(drawdown.depth) if drawdown else None,
            "max_drawdown_peak_date": drawdown.peak_date.isoformat() if drawdown else None,
            "max_drawdown_trough_date": drawdown.trough_date.isoformat() if drawdown else None,
        },
        provenance=(_provenance(series, dates[0], dates[-1]),),
        quality_flags=tuple(flags),
        notes=(
            "Ratios are fractions (0.12 = 12%). Returns are nominal, in the asset's currency.",
            "annualized_return is null for spans under 180 days.",
        ),
    )
