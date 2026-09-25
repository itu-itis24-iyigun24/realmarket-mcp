"""Normalized market-data types shared by providers, analytics and tools."""

from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import json
from dataclasses import dataclass
from enum import StrEnum


class AssetClass(StrEnum):
    EQUITY = "equity"
    INDEX = "index"
    FX = "fx"
    COMMODITY = "commodity"
    FUND = "fund"
    CRYPTO = "crypto"
    OTHER = "other"


@dataclass(frozen=True)
class AssetRef:
    """A resolvable asset, as returned by ``search_assets``."""

    symbol: str
    name: str
    asset_class: AssetClass
    currency: str
    exchange: str

    def to_dict(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "asset_class": self.asset_class.value,
            "currency": self.currency,
            "exchange": self.exchange,
        }


@dataclass(frozen=True)
class Bar:
    """One daily session. Prices may be ``None`` when the provider has no value."""

    date: dt.date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None


@dataclass(frozen=True)
class PriceSeries:
    """Daily bars for one symbol, ascending by date, with no duplicate dates."""

    symbol: str
    currency: str
    provider: str
    adjustment: str
    retrieved_at: str
    bars: tuple[Bar, ...]

    def __post_init__(self) -> None:
        dates = [bar.date for bar in self.bars]
        if any(later <= earlier for earlier, later in itertools.pairwise(dates)):
            raise ValueError(f"{self.symbol}: bars must be strictly ascending by date")

    def between(self, start: dt.date, end: dt.date) -> PriceSeries:
        kept = tuple(bar for bar in self.bars if start <= bar.date <= end)
        return PriceSeries(
            self.symbol, self.currency, self.provider, self.adjustment, self.retrieved_at, kept
        )

    @property
    def data_version(self) -> str:
        """SHA-256 over the canonical bar content: changes exactly when the numbers change."""
        rows = [[b.date.isoformat(), b.open, b.high, b.low, b.close, b.volume] for b in self.bars]
        canonical = json.dumps(
            {
                "symbol": self.symbol,
                "currency": self.currency,
                "adjustment": self.adjustment,
                "bars": rows,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
