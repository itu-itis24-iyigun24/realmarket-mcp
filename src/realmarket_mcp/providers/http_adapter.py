"""Bring your own data: prices, search and statements from an HTTP adapter the operator runs.

A firm that holds licensed market data (an exchange feed, a data vendor) puts a thin adapter in
front of it that answers the JSON endpoints below; realmarket then uses it in place of
Yahoo, and every calculation, flag and provenance rule applies unchanged. The adapter can be
written in any language and usually runs on the firm's own network. Contract version 1 —
docs/adapter-api.md is the full specification, with an example adapter.

    GET {base}/meta
        {"api_version": 1, "name": "acme-feed", "attribution": "Source: ...",
         "gold_usd_symbol": "XAUUSD", "fx_symbol": "{base}{quote}",
         "benchmarks": {"TRY": "XU100"}}
    GET {base}/search?q=<text>&limit=<n>
        {"assets": [{"symbol", "name", "asset_class", "currency", "exchange"}]}
    GET {base}/bars?symbol=<s>&start=YYYY-MM-DD&end=YYYY-MM-DD
        {"symbol", "currency", "adjustment",
         "bars": [{"date", "open", "high", "low", "close", "volume", "price_close"?}],
         "dividends"?: [{"date", "amount"}], "splits"?: [{"date", "ratio"}]}
                                                                           404: unknown symbol
    GET {base}/financials?symbol=<s>                                          optional; 404: none
        {"currency", "sector", "industry",
         "quarterly": [{"end": "YYYY-MM-DD", "values": {field: number | null}}], "annual": [...]}
    GET {base}/peers?symbol=<s>&level=industry|sector                       optional; 404: none
        {"industry", "group", "market", "definition",
         "peers": [{"symbol", "name", "price_to_book", "market_cap"?, "currency"?,
                    "financial_currency"?}]}
    GET {base}/news?q=<text>&start=<ISO>&end=<ISO>&limit=<n>[&language=tr]  optional; 404: none
        {"articles": [{"published_at": "YYYY-MM-DDTHH:MM:SSZ", "title", "url", "source",
                       "language", "country"}]}

Configuration: REALMARKET_PRICE_PROVIDER=http, REALMARKET_HTTP_URL=<base>, and optionally
REALMARKET_HTTP_TOKEN, sent as "Authorization: Bearer <token>" and never echoed.
Responses are validated strictly; a malformed answer is an error, never repaired.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import time
import urllib.parse
from collections.abc import Callable, Mapping
from typing import Any

from realmarket_mcp.contract import ErrorCode, ToolError, register_attribution
from realmarket_mcp.models import (
    MINOR_UNITS,
    AssetClass,
    AssetRef,
    Bar,
    FinancialStatements,
    IndustryPeers,
    NewsItem,
    PeerMultiple,
    PriceSeries,
    statements_from_dict,
)
from realmarket_mcp.providers import http

Fetch = Callable[[str, Mapping[str, str]], bytes]

URL_ENV = "REALMARKET_HTTP_URL"
TOKEN_ENV = "REALMARKET_HTTP_TOKEN"
API_VERSION = 1
META_CACHE_SECONDS = 3600
SOURCE = "the data adapter"

_meta_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _bad(detail: str) -> ToolError:
    return ToolError(
        ErrorCode.PROVIDER_UNAVAILABLE,
        f"The data adapter returned an invalid response ({detail}).",
        "The adapter does not follow the realmarket adapter API v1 (docs/adapter-api.md); "
        "report it to whoever runs the adapter.",
    )


def _number(value: Any, what: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise _bad(f"{what} is not a finite number")
    return float(value)


def _positive(value: Any, what: str) -> float:
    number = _number(value, what)
    if number is None or number <= 0:
        raise _bad(f"{what} must be a positive number")
    return number


class HttpAdapterProvider:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        retrieved_at: str,
        fetch: Fetch | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._retrieved_at = retrieved_at
        self._fetch = fetch or self._default_fetch
        meta = self._meta()
        # Namespaced, so an adapter can never pose as a built-in source ("yahoo", "sec_edgar").
        self.name = f"adapter:{meta['name']}"
        self.gold_usd_symbol = str(meta["gold_usd_symbol"])
        self._fx_pattern = str(meta["fx_symbol"])
        self._benchmarks = {str(k).upper(): str(v) for k, v in meta.get("benchmarks", {}).items()}
        if meta.get("attribution"):
            register_attribution(self.name, str(meta["attribution"]))

    # --- transport -------------------------------------------------------------------------

    @staticmethod
    def _default_fetch(url: str, headers: Mapping[str, str]) -> bytes:
        not_found = ToolError(ErrorCode.NO_DATA_IN_RANGE, "Not found.", "Check the symbol.")
        return http.get(url, headers, source=SOURCE, not_found=not_found)

    def _get(self, path: str, params: Mapping[str, str | int] | None = None) -> Any:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        body = self._fetch(f"{self._base}{path}{query}", self._headers)
        try:
            return json.loads(body)
        except (UnicodeDecodeError, ValueError):
            raise _bad("not JSON") from None

    def _meta(self) -> dict[str, Any]:
        cached = _meta_cache.get(self._base)
        if cached and time.monotonic() - cached[0] < META_CACHE_SECONDS:
            return cached[1]
        meta = self._get("/meta")
        if not isinstance(meta, dict) or meta.get("api_version") != API_VERSION:
            raise _bad(f"/meta must report api_version {API_VERSION}")
        for key in ("name", "gold_usd_symbol", "fx_symbol"):
            if not isinstance(meta.get(key), str) or not meta[key]:
                raise _bad(f"/meta has no {key}")
        if "{base}" not in meta["fx_symbol"] or "{quote}" not in meta["fx_symbol"]:
            raise _bad("/meta fx_symbol must contain {base} and {quote}")
        _meta_cache[self._base] = (time.monotonic(), meta)
        return meta

    # --- PriceProvider -------------------------------------------------------------------------

    def fx_symbol(self, base: str, quote: str) -> str:
        return self._fx_pattern.replace("{base}", base).replace("{quote}", quote)

    def default_benchmark(self, symbol: str) -> str | None:
        try:
            currency = self._asset_currency(symbol)
        except ToolError:
            return None
        benchmark = self._benchmarks.get((currency or "").upper())
        return None if benchmark == symbol else benchmark

    def _asset_currency(self, symbol: str) -> str | None:
        for asset in self.search(symbol, 5):
            if asset.symbol == symbol:
                return asset.currency
        return None

    def search(self, query: str, limit: int) -> list[AssetRef]:
        payload = self._get("/search", {"q": query, "limit": limit})
        try:
            return [
                AssetRef(
                    symbol=str(a["symbol"]),
                    name=str(a["name"]),
                    asset_class=AssetClass(a["asset_class"]),
                    currency=str(a["currency"]).upper() if a.get("currency") else None,
                    exchange=str(a.get("exchange") or ""),
                )
                for a in payload["assets"]
            ][:limit]
        except (KeyError, TypeError, ValueError) as exc:
            raise _bad(f"/search: {type(exc).__name__}") from None

    def daily_bars(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries:
        try:
            payload = self._get(
                "/bars", {"symbol": symbol, "start": start.isoformat(), "end": end.isoformat()}
            )
        except ToolError as error:
            if error.code is ErrorCode.NO_DATA_IN_RANGE:  # the adapter's 404
                raise ToolError(
                    ErrorCode.UNKNOWN_SYMBOL,
                    f"The data adapter does not know {symbol!r}.",
                    "Call search_assets and use one of the returned symbols.",
                    {"symbol": symbol},
                ) from None
            raise
        try:
            if payload["symbol"] != symbol:
                raise _bad(f"/bars answered for {payload['symbol']!r}, not {symbol!r}")
            if payload["currency"] in MINOR_UNITS:
                raise _bad("/bars currency must be the major unit (GBP, not pence)")
            currency = str(payload["currency"]).upper()
            adjustment = str(payload["adjustment"])
            if len(currency) != 3 or not adjustment:
                raise _bad("/bars needs a 3-letter currency and an adjustment policy")
            bars = tuple(
                Bar(
                    date=dt.date.fromisoformat(str(b["date"])),
                    open=_number(b.get("open"), "open"),
                    high=_number(b.get("high"), "high"),
                    low=_number(b.get("low"), "low"),
                    close=_number(b.get("close"), "close"),
                    volume=_number(b.get("volume"), "volume"),
                    price_close=_number(b.get("price_close"), "price_close"),
                )
                for b in payload["bars"]
            )
            dividends = tuple(
                (dt.date.fromisoformat(str(d["date"])), _positive(d.get("amount"), "dividend"))
                for d in payload.get("dividends") or ()
            )
            splits = tuple(
                (dt.date.fromisoformat(str(d["date"])), _positive(d.get("ratio"), "split ratio"))
                for d in payload.get("splits") or ()
            )
            series = PriceSeries(
                symbol, currency, self.name, adjustment, self._retrieved_at, bars, dividends, splits
            )
        except ToolError:
            raise
        except (KeyError, TypeError, ValueError) as exc:  # incl. unsorted or duplicate dates
            raise _bad(f"/bars: {exc}") from None
        return series.between(start, end)

    # --- FinancialsProvider -------------------------------------------------------------------

    def financials(self, symbol: str) -> FinancialStatements:
        try:
            payload = self._get("/financials", {"symbol": symbol})
        except ToolError as error:
            if error.code is ErrorCode.NO_DATA_IN_RANGE:
                raise ToolError(
                    ErrorCode.NO_DATA_IN_RANGE,
                    f"The data adapter has no financial statements for {symbol}.",
                    "Funds, indices and currencies have none; some adapters serve prices only.",
                    {"symbol": symbol},
                ) from None
            raise
        try:
            return statements_from_dict(
                payload, symbol=symbol, provider=self.name, retrieved_at=self._retrieved_at
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _bad(f"/financials: {exc}") from None

    def industry_peers(self, symbol: str, *, broader: bool = False) -> IndustryPeers:
        """The companies the adapter groups with ``symbol`` (its industry, or with ``broader``
        its sector), each with the adapter's price-to-book, for get_valuation's comparison."""
        level = "sector" if broader else "industry"
        try:
            payload = self._get("/peers", {"symbol": symbol, "level": level})
        except ToolError as error:
            if error.code is ErrorCode.NO_DATA_IN_RANGE:
                raise ToolError(
                    ErrorCode.NO_DATA_IN_RANGE,
                    f"The data adapter gives no {level} peer list for {symbol}.",
                    "Peers come from the adapter's optional /peers endpoint (docs/adapter-api.md).",
                    {"symbol": symbol},
                ) from None
            raise
        try:
            peers = tuple(
                PeerMultiple(
                    symbol=str(p["symbol"]),
                    name=str(p.get("name") or p["symbol"]),
                    price_to_book=_number(p.get("price_to_book"), "price_to_book"),
                    market_cap=_number(p.get("market_cap"), "market_cap"),
                    currency=str(p["currency"]).upper() if p.get("currency") else None,
                    financial_currency=(
                        str(p["financial_currency"]).upper()
                        if p.get("financial_currency")
                        else None
                    ),
                )
                for p in payload["peers"]
            )
            return IndustryPeers(
                symbol=symbol,
                industry=str(payload["industry"]),
                group=str(payload.get("group") or payload["industry"]),
                level=level,
                market=str(payload["market"]),
                provider=self.name,
                retrieved_at=self._retrieved_at,
                definition=str(payload["definition"]),
                peers=peers,
            )
        except ToolError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise _bad(f"/peers: {exc}") from None


class HttpAdapterNewsProvider:
    """News and disclosures from the same adapter (e.g. the firm's KAP or Foreks news feed)."""

    def __init__(self, adapter: HttpAdapterProvider) -> None:
        self._adapter = adapter
        self.name = adapter.name

    def search(
        self,
        query: str,
        start: dt.datetime,
        end: dt.datetime,
        *,
        language: str | None,
        limit: int,
    ) -> list[NewsItem]:
        params: dict[str, str | int] = {
            "q": query,
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit": limit,
        }
        if language:
            params["language"] = language
        try:
            payload = self._adapter._get("/news", params)
        except ToolError as error:
            if error.code is ErrorCode.NO_DATA_IN_RANGE:
                raise ToolError(
                    ErrorCode.UNSUPPORTED,
                    "The data adapter does not serve news.",
                    "News comes from the adapter's optional /news endpoint (docs/adapter-api.md);"
                    " ask whoever runs the adapter, or set REALMARKET_NEWS_PROVIDER=gdelt.",
                ) from None
            raise
        try:
            items = []
            for a in payload["articles"]:
                published = dt.datetime.strptime(str(a["published_at"]), "%Y-%m-%dT%H:%M:%SZ")
                title, url = str(a["title"]).strip(), str(a["url"])
                if not title or not url.startswith(("https://", "http://")):
                    raise ValueError("an article needs a title and an http(s) url")
                items.append(
                    NewsItem(
                        published_at=published.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        title=title,
                        url=url,
                        source=str(a.get("source") or ""),
                        language=a.get("language"),
                        country=a.get("country"),
                    )
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise _bad(f"/news: {exc}") from None
        naive_start, naive_end = start.replace(tzinfo=None), end.replace(tzinfo=None)
        kept = [
            n
            for n in items
            if naive_start
            <= dt.datetime.strptime(n.published_at, "%Y-%m-%dT%H:%M:%SZ")
            <= naive_end
        ]
        return sorted(kept, key=lambda n: n.published_at, reverse=True)[:limit]
