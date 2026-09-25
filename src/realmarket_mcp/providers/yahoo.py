"""Yahoo Finance prices via the ``yfinance`` package (optional extra: ``realmarket-mcp[yahoo]``).

Opt-in only (``REALMARKET_PRICE_PROVIDER=yahoo``). This is an unofficial interface: Yahoo's
terms restrict automated access, the endpoints change without notice, and some histories
contain known errors. Each user decides whether to use it; results say it came from here.

The ``yfinance`` calls live in :class:`YfinanceBackend`. :class:`YahooProvider` only maps the
backend's plain rows onto the shared models and contract errors, so it is tested offline with
a fake backend.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.models import (
    AssetClass,
    AssetRef,
    Bar,
    FinancialPeriod,
    FinancialStatements,
    PriceSeries,
)

INSTALL_HINT = 'Install the optional dependency: pip install "realmarket-mcp[yahoo]".'

_QUOTE_TYPES = {
    "EQUITY": AssetClass.EQUITY,
    "INDEX": AssetClass.INDEX,
    "CURRENCY": AssetClass.FX,
    "FUTURE": AssetClass.COMMODITY,
    "ETF": AssetClass.FUND,
    "MUTUALFUND": AssetClass.FUND,
    "CRYPTOCURRENCY": AssetClass.CRYPTO,
}


class SymbolNotFound(Exception):
    pass


class RateLimited(Exception):
    pass


@dataclass(frozen=True)
class RawHistory:
    currency: str | None
    rows: Sequence[
        tuple[dt.date, float | None, float | None, float | None, float | None, float | None]
    ]


# Yahoo row labels for each normalized field, first match wins.
FINANCIAL_ROWS = {
    "revenue": ("Total Revenue", "Operating Revenue"),
    "gross_profit": ("Gross Profit",),
    "operating_income": ("Operating Income",),
    "net_income": ("Net Income Common Stockholders", "Net Income"),
    "total_assets": ("Total Assets",),
    "total_equity": ("Stockholders Equity", "Common Stock Equity"),
    "total_debt": ("Total Debt",),
}

Rows = list[tuple[dt.date, dict[str, float | None]]]


@dataclass(frozen=True)
class RawFinancials:
    currency: str | None
    sector: str | None
    industry: str | None
    quarterly: Rows
    annual: Rows


class YahooBackend(Protocol):
    def search(self, query: str, limit: int) -> list[dict[str, Any]]: ...

    def history(self, symbol: str, start: dt.date, end_inclusive: dt.date) -> RawHistory: ...

    def financials(self, symbol: str) -> RawFinancials: ...


def _clean(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


class YfinanceBackend:
    """The only code in this project that imports ``yfinance``."""

    def __init__(self) -> None:
        try:
            import yfinance
        except ImportError:
            raise ToolError(
                ErrorCode.UNSUPPORTED,
                "The Yahoo provider is selected but yfinance is not installed.",
                INSTALL_HINT,
            ) from None
        self._yf = yfinance

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        try:
            found = self._yf.Search(query, max_results=limit, news_count=0, lists_count=0)
        except Exception as exc:
            raise _translate(exc) from exc
        return list(found.quotes)

    def history(self, symbol: str, start: dt.date, end_inclusive: dt.date) -> RawHistory:
        ticker = self._yf.Ticker(symbol)
        try:
            frame = ticker.history(
                start=start.isoformat(),
                end=(end_inclusive + dt.timedelta(days=1)).isoformat(),  # yfinance end is exclusive
                interval="1d",
                auto_adjust=True,
                actions=False,
                raise_errors=True,
            )
            currency = (ticker.history_metadata or {}).get("currency")
        except Exception as exc:
            raise _translate(exc) from exc
        rows = [
            (
                index.date(),  # the exchange-local session date
                _clean(row.get("Open")),
                _clean(row.get("High")),
                _clean(row.get("Low")),
                _clean(row.get("Close")),
                _clean(row.get("Volume")),
            )
            for index, row in frame.iterrows()
        ]
        return RawHistory(currency=currency, rows=rows)

    def financials(self, symbol: str) -> RawFinancials:
        ticker = self._yf.Ticker(symbol)
        try:
            quarterly = _frame_rows(ticker.quarterly_income_stmt, ticker.quarterly_balance_sheet)
            annual = _frame_rows(ticker.income_stmt, ticker.balance_sheet)
            info = ticker.info or {}
        except Exception as exc:
            raise _translate(exc) from exc
        return RawFinancials(
            currency=info.get("financialCurrency"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            quarterly=quarterly,
            annual=annual,
        )


def _frame_rows(*frames: Any) -> Rows:
    """Merge statement frames (columns are period ends) into {period end: normalized values}."""
    merged: dict[dt.date, dict[str, float | None]] = {}
    for frame in frames:
        if frame is None or getattr(frame, "empty", True):
            continue
        for column in frame.columns:
            end = column.date()
            values = merged.setdefault(end, {})
            for field, labels in FINANCIAL_ROWS.items():
                if values.get(field) is not None:
                    continue
                for label in labels:
                    if label in frame.index:
                        values[field] = _clean(frame.loc[label, column])
                        break
    return sorted(merged.items())


def _translate(exc: Exception) -> Exception:
    name = type(exc).__name__
    if name == "YFRateLimitError":
        return RateLimited(str(exc))
    if name in {"YFPricesMissingError", "YFTickerMissingError", "YFTzMissingError"}:
        return SymbolNotFound(str(exc))
    return exc


class YahooProvider:
    name = "yahoo"
    adjustment = "split_and_dividend"
    gold_usd_symbol = "GC=F"  # COMEX gold futures, continuous front month

    @staticmethod
    def fx_symbol(base: str, quote: str) -> str:
        return f"{base}{quote}=X"

    @staticmethod
    def default_benchmark(symbol: str) -> str | None:
        if symbol.upper().endswith(".IS"):
            return "XU100.IS"  # BIST 100
        return None

    def __init__(self, backend: YahooBackend | None = None, *, retrieved_at: str) -> None:
        self._backend = backend if backend is not None else YfinanceBackend()
        self._retrieved_at = retrieved_at

    def search(self, query: str, limit: int) -> list[AssetRef]:
        quotes = self._call(lambda: self._backend.search(query, limit), symbol=None)
        assets = []
        for quote in quotes:
            symbol = quote.get("symbol")
            if not symbol:
                continue
            assets.append(
                AssetRef(
                    symbol=symbol,
                    name=quote.get("longname") or quote.get("shortname") or symbol,
                    asset_class=_QUOTE_TYPES.get(str(quote.get("quoteType")), AssetClass.OTHER),
                    currency=None,  # Yahoo search does not report it; price tools do
                    exchange=quote.get("exchDisp") or quote.get("exchange") or "",
                )
            )
        return assets[:limit]

    def daily_bars(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries:
        raw = self._call(lambda: self._backend.history(symbol, start, end), symbol=symbol)
        # A bar dated on or after the retrieval day may be an in-progress session: exclude it.
        cutoff = min(end, dt.date.fromisoformat(self._retrieved_at[:10]) - dt.timedelta(days=1))
        by_date = {}
        for date, open_, high, low, close, volume in raw.rows:
            if start <= date <= cutoff:
                by_date[date] = Bar(date, open_, high, low, close, volume)  # last row per date wins
        return PriceSeries(
            symbol=symbol,
            currency=raw.currency or "unknown",
            provider=self.name,
            adjustment=self.adjustment,
            retrieved_at=self._retrieved_at,
            bars=tuple(by_date[d] for d in sorted(by_date)),
        )

    def financials(self, symbol: str) -> FinancialStatements:
        raw: RawFinancials = self._call(lambda: self._backend.financials(symbol), symbol=symbol)
        if not raw.quarterly and not raw.annual:
            raise ToolError(
                ErrorCode.NO_DATA_IN_RANGE,
                f"Yahoo Finance has no financial statements for {symbol}.",
                "Funds, indices, currencies and some small companies have none; check the symbol.",
                {"symbol": symbol},
            )
        return FinancialStatements(
            symbol=symbol,
            currency=(raw.currency or "unknown").upper(),
            sector=raw.sector,
            industry=raw.industry,
            provider=self.name,
            retrieved_at=self._retrieved_at,
            quarterly=tuple(FinancialPeriod(end, values) for end, values in raw.quarterly),
            annual=tuple(FinancialPeriod(end, values) for end, values in raw.annual),
        )

    def _call(self, fetch: Any, *, symbol: str | None) -> Any:
        try:
            return fetch()
        except ToolError:
            raise
        except SymbolNotFound:
            raise ToolError(
                ErrorCode.UNKNOWN_SYMBOL,
                f"Yahoo Finance has no data for symbol {symbol!r}.",
                "Call search_assets and use a returned symbol. Borsa Istanbul symbols end in "
                "'.IS' (e.g. 'THYAO.IS'); FX pairs look like 'USDTRY=X'; gold futures 'GC=F'.",
                {"symbol": symbol},
            ) from None
        except RateLimited:
            raise ToolError(
                ErrorCode.RATE_LIMITED,
                "Yahoo Finance rate limit reached.",
                "Wait a minute before calling again, and request fewer symbols per call.",
            ) from None
        except Exception as exc:
            raise ToolError(
                ErrorCode.PROVIDER_UNAVAILABLE,
                f"Yahoo Finance request failed ({type(exc).__name__}).",
                "Retry once shortly. If it keeps failing, Yahoo may have changed its interface: "
                'upgrade with pip install -U "realmarket-mcp[yahoo]".',
            ) from None
