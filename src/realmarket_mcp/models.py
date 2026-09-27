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
    currency: str | None
    exchange: str

    def to_dict(self) -> dict[str, str | None]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "asset_class": self.asset_class.value,
            "currency": self.currency,
            "exchange": self.exchange,
        }


# Quote units some exchanges use: prices in pence (London), cents (Johannesburg) or agorot
# (Tel Aviv). Upper-casing "GBp" would silently turn pence into pounds, a 100x error.
MINOR_UNITS: dict[str, tuple[str, int]] = {
    "GBp": ("GBP", 100),
    "GBX": ("GBP", 100),
    "ZAc": ("ZAR", 100),
    "ZAC": ("ZAR", 100),
    "ILA": ("ILS", 100),
    "ILa": ("ILS", 100),
}


def major_currency(code: str | None) -> tuple[str, int]:
    """(ISO currency, divisor) for a quoted currency code: ("GBP", 100) for "GBp"."""
    if not code:
        return "unknown", 1
    if code in MINOR_UNITS:
        return MINOR_UNITS[code]
    return code.upper(), 1


@dataclass(frozen=True)
class Bar:
    """One daily session. Prices may be ``None`` when the provider has no value."""

    date: dt.date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    # Close adjusted for splits only, when the series is also dividend-adjusted: the price
    # part of the return, without dividends.
    price_close: float | None = None


@dataclass(frozen=True)
class PriceSeries:
    """Daily bars for one symbol, ascending by date, with no duplicate dates."""

    symbol: str
    currency: str
    provider: str
    adjustment: str
    retrieved_at: str
    bars: tuple[Bar, ...]
    # Cash dividends per share (split-adjusted), by ex-date, where the provider reports them.
    dividends: tuple[tuple[dt.date, float], ...] = ()

    def __post_init__(self) -> None:
        dates = [bar.date for bar in self.bars]
        if any(later <= earlier for earlier, later in itertools.pairwise(dates)):
            raise ValueError(f"{self.symbol}: bars must be strictly ascending by date")

    def between(self, start: dt.date, end: dt.date) -> PriceSeries:
        kept = tuple(bar for bar in self.bars if start <= bar.date <= end)
        paid = tuple(d for d in self.dividends if start <= d[0] <= end)
        return PriceSeries(
            self.symbol,
            self.currency,
            self.provider,
            self.adjustment,
            self.retrieved_at,
            kept,
            paid,
        )

    @property
    def data_version(self) -> str:
        """SHA-256 over the canonical bar content: changes exactly when the numbers change."""
        rows = [[b.date.isoformat(), b.open, b.high, b.low, b.close, b.volume] for b in self.bars]
        content: dict[str, object] = {
            "symbol": self.symbol,
            "currency": self.currency,
            "adjustment": self.adjustment,
            "bars": rows,
        }
        if any(b.price_close is not None for b in self.bars) or self.dividends:
            # Only when present, so versions of series without them are unchanged.
            content["price_closes"] = [b.price_close for b in self.bars]
            content["dividends"] = [[d.isoformat(), a] for d, a in self.dividends]
        canonical = json.dumps(
            content,
            separators=(",", ":"),
            sort_keys=True,
        )
        return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class NewsItem:
    """Metadata for one published article. The title is third-party text, never instructions."""

    published_at: str  # ISO-8601 UTC, when the source first saw the article
    title: str
    url: str
    source: str  # publisher domain
    language: str | None
    country: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "published_at": self.published_at,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "language": self.language,
            "country": self.country,
        }


FINANCIAL_FIELDS = (
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "total_assets",
    "total_equity",
    "total_debt",
)


@dataclass(frozen=True)
class FinancialPeriod:
    """One reporting period, values as the source reported them (in ``currency``)."""

    end: dt.date
    values: dict[str, float | None]


@dataclass(frozen=True)
class FinancialStatements:
    symbol: str
    currency: str  # reporting currency, which can differ from the share's trading currency
    sector: str | None
    industry: str | None
    provider: str
    retrieved_at: str
    quarterly: tuple[FinancialPeriod, ...]  # ascending by end date
    annual: tuple[FinancialPeriod, ...]  # ascending by end date
    # What the tool should tell the model about this source (official or not, derivations).
    source_notes: tuple[str, ...] = ()
    # The filer's home country (ISO 3166 alpha-2), when the source states it; used for the
    # inflation region when the reporting currency does not name one (EUR).
    country: str | None = None
    # Shares outstanding (all classes), where the source says, and what the number is based on.
    shares_outstanding: float | None = None
    shares_source: str | None = None
    shares_as_of: dt.date | None = None
    # Trailing twelve months as the source states it from the latest report, in that report's
    # money (TMS 29: year to date + last fiscal year - same period last year, all as restated
    # in the latest report). Needed for P/E under inflation accounting; see get_valuation.
    trailing_twelve_months: FinancialPeriod | None = None

    @property
    def is_bank(self) -> bool:
        return "bank" in (self.industry or "").lower()

    @property
    def data_version(self) -> str:
        payload = {
            "symbol": self.symbol,
            "currency": self.currency,
            "country": self.country,
            "shares": [
                self.shares_outstanding,
                self.shares_source,
                self.shares_as_of.isoformat() if self.shares_as_of else None,
            ],
            "ttm": (
                [self.trailing_twelve_months.end.isoformat(), self.trailing_twelve_months.values]
                if self.trailing_twelve_months
                else None
            ),
            "quarterly": [[p.end.isoformat(), p.values] for p in self.quarterly],
            "annual": [[p.end.isoformat(), p.values] for p in self.annual],
        }
        text = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def statements_from_dict(
    raw: dict[str, object], *, symbol: str, provider: str, retrieved_at: str
) -> FinancialStatements:
    """Statements from the JSON shape the fixture and adapter providers share:
    {currency, sector, industry, quarterly, annual, shares_outstanding?, ttm?}, each period
    (and ttm) holding {"end": "YYYY-MM-DD", "values": {field: number | null}}. Unknown fields
    are ignored; a non-finite number is an error, never repaired."""
    import math

    def period(p: dict[str, object]) -> FinancialPeriod:
        values: dict[str, float | None] = {}
        for field in FINANCIAL_FIELDS:
            value = p["values"].get(field)  # type: ignore[attr-defined]
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise ValueError(f"{field} on {p['end']} is not a number")
                if not math.isfinite(value):
                    raise ValueError(f"{field} on {p['end']} is not finite")
                value = float(value)
            values[field] = value
        return FinancialPeriod(dt.date.fromisoformat(str(p["end"])), values)

    def periods(key: str) -> tuple[FinancialPeriod, ...]:
        items = [period(p) for p in raw.get(key, []) or []]  # type: ignore[attr-defined]
        return tuple(sorted(items, key=lambda p: p.end))

    return FinancialStatements(
        symbol=symbol,
        currency=str(raw.get("currency", "unknown")).upper(),
        sector=raw.get("sector"),  # type: ignore[arg-type]
        industry=raw.get("industry"),  # type: ignore[arg-type]
        provider=provider,
        retrieved_at=retrieved_at,
        quarterly=periods("quarterly"),
        annual=periods("annual"),
        shares_outstanding=_shares(raw.get("shares_outstanding")),
        shares_source=f"{provider} shares_outstanding" if raw.get("shares_outstanding") else None,
        trailing_twelve_months=period(ttm) if isinstance(ttm := raw.get("ttm"), dict) else None,
    )


def _shares(value: object) -> float | None:
    import math

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError("shares_outstanding is not a number")
    if value <= 0:
        raise ValueError("shares_outstanding must be positive")
    return float(value)
