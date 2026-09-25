"""The provider interface. Providers are the only modules allowed to use the network.

A provider raises :class:`~realmarket_mcp.contract.ToolError` for every failure it can name
(unknown symbol, no data, missing key, rate limit, outage) so the message reaches the model
with an actionable hint.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol

from realmarket_mcp.models import AssetRef, FinancialStatements, NewsItem, PriceSeries


class PriceProvider(Protocol):
    name: str
    gold_usd_symbol: str  # gold priced in US dollars per troy ounce

    def fx_symbol(self, base: str, quote: str) -> str:
        """Symbol whose price is units of ``quote`` per one ``base`` (e.g. TRY per USD)."""
        ...

    def default_benchmark(self, symbol: str) -> str | None:
        """The broad market index this provider would compare ``symbol`` against, if known."""
        ...

    def search(self, query: str, limit: int) -> list[AssetRef]: ...

    def daily_bars(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries: ...


class NewsProvider(Protocol):
    name: str

    def search(
        self,
        query: str,
        start: dt.datetime,
        end: dt.datetime,
        *,
        language: str | None,
        limit: int,
    ) -> list[NewsItem]: ...


class FinancialsProvider(Protocol):
    name: str

    def financials(self, symbol: str) -> FinancialStatements: ...
