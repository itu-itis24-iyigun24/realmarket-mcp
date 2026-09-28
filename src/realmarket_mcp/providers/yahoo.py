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
from collections.abc import Mapping, Sequence
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
    major_currency,
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
    ]  # prices adjusted for splits and dividends
    price_closes: Mapping[dt.date, float | None] | None = None  # split-adjusted only
    dividends: Sequence[tuple[dt.date, float]] = ()
    splits: Sequence[tuple[dt.date, float]] = ()


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
    shares: float | None = None  # sharesOutstanding: the quoted share class
    implied_shares: float | None = None  # impliedSharesOutstanding: all classes


class YahooBackend(Protocol):
    def search(self, query: str, limit: int) -> list[dict[str, Any]]: ...

    def history(self, symbol: str, start: dt.date, end_inclusive: dt.date) -> RawHistory: ...

    def financials(self, symbol: str) -> RawFinancials: ...


def _clean(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _dividend_factors(closes: Sequence[float | None], dividends: Sequence[float]) -> list[float]:
    """Total-return adjustment per bar: each cash dividend scales every earlier price by
    ``1 - dividend / previous close``, the standard back-adjustment. Computed here rather than
    taken from Yahoo's Adj Close, which is wrong for pence-quoted shares (it treats a dividend
    in pence as pounds: BP.L's 2025-08-14 factor was 0.99985 instead of 0.98519). Dividend and
    close are in the same unit, so the ratio is unit-free."""
    factors = [1.0] * len(closes)
    running = 1.0
    previous_close: list[float | None] = [None, *closes[:-1]]
    for index in range(len(closes) - 1, -1, -1):
        factors[index] = running
        dividend, before = dividends[index], previous_close[index]
        if dividend and before and dividend < before:
            running *= 1.0 - dividend / before
    return factors


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
                auto_adjust=False,  # adjusted here, so the split-only close is kept too
                actions=True,
                raise_errors=True,
            )
            currency = (ticker.history_metadata or {}).get("currency")
        except Exception as exc:
            raise _translate(exc) from exc
        raw = [
            (
                index.date(),  # the exchange-local session date
                _clean(row.get("Open")),
                _clean(row.get("High")),
                _clean(row.get("Low")),
                _clean(row.get("Close")),  # adjusted for splits only
                _clean(row.get("Volume")),
                _clean(row.get("Dividends")) or 0.0,
            )
            for index, row in frame.iterrows()
        ]
        factors = _dividend_factors([r[4] for r in raw], [r[6] for r in raw])

        def scaled(value: float | None, factor: float) -> float | None:
            return None if value is None else value * factor

        rows = [
            (day, *(scaled(v, f) for v in (open_, high, low, close)), volume)
            for (day, open_, high, low, close, volume, _), f in zip(raw, factors, strict=True)
        ]
        price_closes = {r[0]: r[4] for r in raw}
        dividends = [(r[0], r[6]) for r in raw if r[6]]
        splits = [
            (index.date(), ratio)
            for index, row in frame.iterrows()
            if (ratio := _clean(row.get("Stock Splits"))) and ratio > 0 and ratio != 1.0
        ]
        return RawHistory(currency, rows, price_closes, dividends, splits)

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
            shares=_clean(info.get("sharesOutstanding")),
            implied_shares=_clean(info.get("impliedSharesOutstanding")),
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


def _all_share_classes(raw: RawFinancials) -> tuple[float | None, str | None]:
    """Yahoo's sharesOutstanding counts the quoted class only (Alphabet GOOGL: 5.87bn of
    12.23bn on 2026-09-27); impliedSharesOutstanding counts every class. Prefer the latter."""
    if raw.implied_shares and raw.implied_shares > 0:
        if raw.shares and abs(raw.implied_shares / raw.shares - 1) > 0.01:
            return raw.implied_shares, (
                "yahoo impliedSharesOutstanding (all share classes; the quoted class alone is "
                f"{raw.shares:,.0f})"
            )
        return raw.implied_shares, "yahoo impliedSharesOutstanding"
    if raw.shares and raw.shares > 0:
        return raw.shares, "yahoo sharesOutstanding (may cover only the quoted share class)"
    return None, None


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
        currency, unit = major_currency(raw.currency)  # pence -> pounds, etc.

        def major(value: float | None) -> float | None:
            return None if value is None else value / unit

        by_date = {}
        for date, open_, high, low, close, volume in raw.rows:
            if start <= date <= cutoff:  # last row per date wins
                prices = (major(open_), major(high), major(low), major(close))
                split_only = major((raw.price_closes or {}).get(date))
                by_date[date] = Bar(date, *prices, volume, split_only)
        return PriceSeries(
            symbol=symbol,
            currency=currency,
            provider=self.name,
            adjustment=self.adjustment,
            retrieved_at=self._retrieved_at,
            bars=tuple(by_date[d] for d in sorted(by_date)),
            dividends=tuple(
                (d, a / unit) for d, a in raw.dividends if start <= d <= cutoff and d in by_date
            ),
            splits=tuple((d, r) for d, r in raw.splits if start <= d <= cutoff),
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
        shares, source = _all_share_classes(raw)
        currency, unit = major_currency(raw.currency)

        def major(rows: Rows) -> tuple[FinancialPeriod, ...]:
            return tuple(
                FinancialPeriod(end, {k: None if v is None else v / unit for k, v in vals.items()})
                for end, vals in rows
            )

        return FinancialStatements(
            symbol=symbol,
            currency=currency,
            sector=raw.sector,
            industry=raw.industry,
            provider=self.name,
            retrieved_at=self._retrieved_at,
            quarterly=major(raw.quarterly),
            annual=major(raw.annual),
            shares_outstanding=shares,
            shares_source=source,
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
