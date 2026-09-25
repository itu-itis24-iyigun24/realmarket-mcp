"""A provider that reads local files. Used by the test suite and for offline demos.

Layout::

    <root>/assets.json        [{"symbol", "name", "asset_class", "currency", "exchange"}, ...]
    <root>/bars/<SYMBOL>.csv  date,open,high,low,close,volume   (empty cell = missing)
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.models import AssetClass, AssetRef, Bar, PriceSeries


def _number(cell: str) -> float | None:
    return float(cell) if cell.strip() else None


class FixtureProvider:
    name = "fixture"

    def __init__(self, root: Path, *, retrieved_at: str = "1970-01-01T00:00:00Z") -> None:
        self._root = root
        self._retrieved_at = retrieved_at
        raw = json.loads((root / "assets.json").read_text(encoding="utf-8"))
        self._assets = {
            item["symbol"]: AssetRef(
                symbol=item["symbol"],
                name=item["name"],
                asset_class=AssetClass(item["asset_class"]),
                currency=item["currency"],
                exchange=item["exchange"],
            )
            for item in raw
        }

    def search(self, query: str, limit: int) -> list[AssetRef]:
        needle = query.casefold().strip()
        hits = [
            asset
            for asset in self._assets.values()
            if needle in asset.symbol.casefold() or needle in asset.name.casefold()
        ]
        hits.sort(key=lambda a: (a.symbol.casefold() != needle, a.symbol))
        return hits[:limit]

    def daily_bars(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries:
        asset = self._assets.get(symbol)
        path = self._root / "bars" / f"{symbol}.csv"
        if asset is None or not path.exists():
            raise ToolError(
                ErrorCode.UNKNOWN_SYMBOL,
                f"No asset with symbol {symbol!r}.",
                "Call search_assets with the asset's name and use one of the returned symbols.",
                {"symbol": symbol},
            )
        with path.open(encoding="utf-8", newline="") as handle:
            bars = tuple(
                Bar(
                    date=dt.date.fromisoformat(row["date"]),
                    open=_number(row["open"]),
                    high=_number(row["high"]),
                    low=_number(row["low"]),
                    close=_number(row["close"]),
                    volume=_number(row["volume"]),
                )
                for row in csv.DictReader(handle)
            )
        series = PriceSeries(
            symbol=symbol,
            currency=asset.currency,
            provider=self.name,
            adjustment="as_recorded",
            retrieved_at=self._retrieved_at,
            bars=bars,
        )
        return series.between(start, end)
