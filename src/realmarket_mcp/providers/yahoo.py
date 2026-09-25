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
from realmarket_mcp.models import AssetClass, AssetRef, Bar, PriceSeries

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


class YahooBackend(Protocol):
    def search(self, query: str, limit: int) -> list[dict[str, Any]]: ...

    def history(self, symbol: str, start: dt.date, end_inclusive: dt.date) -> RawHistory: ...


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
        by_date = {}
        for date, open_, high, low, close, volume in raw.rows:
            if start <= date <= end:
                by_date[date] = Bar(date, open_, high, low, close, volume)  # last row per date wins
        return PriceSeries(
            symbol=symbol,
            currency=raw.currency or "unknown",
            provider=self.name,
            adjustment=self.adjustment,
            retrieved_at=self._retrieved_at,
            bars=tuple(by_date[d] for d in sorted(by_date)),
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
