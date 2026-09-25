"""Runtime configuration, read from environment variables only."""

from __future__ import annotations

import datetime as dt
import os
import time
from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from typing import cast

from realmarket_mcp import inflation
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.models import FinancialStatements
from realmarket_mcp.providers import cpi, sec
from realmarket_mcp.providers.base import FinancialsProvider, NewsProvider, PriceProvider

PROVIDER_ENV = "REALMARKET_PRICE_PROVIDER"
FIXTURE_DIR_ENV = "REALMARKET_FIXTURE_DIR"
NEWS_PROVIDER_ENV = "REALMARKET_NEWS_PROVIDER"
# The plugin and extension checkbox; REALMARKET_PRICE_PROVIDER, when set, takes precedence.
USE_YAHOO_ENV = "REALMARKET_USE_YAHOO"
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def price_provider_choice(env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    explicit = env.get(PROVIDER_ENV, "").strip().lower()
    if explicit:
        return explicit
    return "yahoo" if env.get(USE_YAHOO_ENV, "").strip().lower() in TRUE_VALUES else "fixture"


# Names of settings the host passed empty or unsubstituted, removed at startup (for check_setup).
dropped_at_startup: list[str] = []


def describe_setup(env: Mapping[str, str] | None = None) -> dict[str, object]:
    """What the server will use, from its environment. Reports whether each setting is present,
    never its value, so the result is safe to show and paste."""
    env = os.environ if env is None else env
    price = price_provider_choice(env)
    yahoo = price == "yahoo"
    contact = sec.contact_from(env) is not None
    evds = bool(env.get(cpi.EVDS_KEY_ENV, "").strip())
    fred = bool(env.get(cpi.FRED_KEY_ENV, "").strip())
    csv_regions = sorted(
        name.removeprefix("REALMARKET_CPI_CSV_")
        for name, value in env.items()
        if name.startswith("REALMARKET_CPI_CSV_") and value.strip()
    )
    news = env.get(NEWS_PROVIDER_ENV, "gdelt").strip().lower() or "gdelt"
    missing: list[str] = []
    if not yahoo:
        missing.append(
            "Prices are off: tick 'Use Yahoo Finance' in the plugin or extension settings "
            f"(or set {PROVIDER_ENV}=yahoo), then restart the app."
        )
    if not contact:
        fallback = (
            "US financial statements come from Yahoo (unofficial) instead"
            if yahoo
            else "US financial statements are unavailable"
        )
        missing.append(
            f"{fallback}: fill in 'E-mail for SEC EDGAR' ({sec.CONTACT_ENV}) to use the "
            "companies' official SEC filings, then restart the app."
        )
    if not evds and "TR" not in csv_regions:
        missing.append(
            "Turkish inflation (only) comes from the OECD, which lags TÜİK by months; add a TCMB "
            f"EVDS key ({cpi.EVDS_KEY_ENV}) for current data. US and other OECD members' "
            "inflation from the OECD is current."
        )
    return {
        "price_data": {
            "provider": price,
            "enabled": yahoo or (price == "fixture" and bool(env.get(FIXTURE_DIR_ENV, "").strip())),
        },
        "financial_statements": {
            "us_companies": "sec_edgar" if contact else ("yahoo" if yahoo else "unavailable"),
            "other_markets": "yahoo" if yahoo else "unavailable",
            "sec_contact_set": contact,
        },
        "inflation": {
            "TR": "csv" if "TR" in csv_regions else ("evds" if evds else "oecd"),
            "US": "csv" if "US" in csv_regions else ("fred" if fred else "oecd"),
            "other_oecd_members": "oecd",
            "evds_key_set": evds,
            "fred_key_set": fred,
            "csv_regions": csv_regions,
        },
        "news": news,
        "settings_ignored_at_startup": list(dropped_at_startup),
        "missing": missing,
    }


def drop_unset_values(env: MutableMapping[str, str]) -> list[str]:
    """Remove ``REALMARKET_*`` variables a host left empty or unsubstituted.

    Plugin and extension hosts fill the server's environment from user settings; a setting the
    user skipped can arrive as ``""`` or as a literal ``${user_config.name}``. Both mean "not
    set", and treating them as values would, for example, send a placeholder as an e-mail.
    """
    dropped = [
        name
        for name, value in env.items()
        if name.startswith("REALMARKET_") and (not value.strip() or value.strip().startswith("${"))
    ]
    for name in dropped:
        del env[name]
    return dropped


def load_price_provider(*, retrieved_at: str) -> PriceProvider:
    """Build the configured price provider. Called per request so config errors reach the model."""
    choice = price_provider_choice()
    if choice == "fixture":
        root = os.environ.get(FIXTURE_DIR_ENV)
        if not root or not Path(root, "assets.json").exists():
            raise ToolError(
                ErrorCode.MISSING_API_KEY,
                "No price data source is configured.",
                "Ask the user to enable a price provider: in the realmarket plugin or extension "
                "settings, tick 'Use Yahoo Finance' and restart the app; in a plain MCP "
                f"configuration, set {PROVIDER_ENV}=yahoo (or {FIXTURE_DIR_ENV} for offline "
                "test data).",
                {"provider": choice},
            )
        from realmarket_mcp.providers.fixture import FixtureProvider

        return FixtureProvider(Path(root), retrieved_at=retrieved_at)
    if choice == "yahoo":
        from realmarket_mcp.providers.yahoo import YahooProvider

        return YahooProvider(retrieved_at=retrieved_at)
    raise ToolError(
        ErrorCode.UNSUPPORTED,
        f"Unknown price provider {choice!r}.",
        f"Set {PROVIDER_ENV} to one of: yahoo, fixture.",
        {"provider": choice},
    )


CURRENCY_REGIONS = {"TRY": "TR", "USD": "US", "GBP": "GB"}
SUPPORTED_REGIONS = tuple(sorted(cpi.OECD_REGIONS))


def default_region(currency: str) -> str | None:
    return CURRENCY_REGIONS.get(currency.upper())


def load_cpi(
    region: str,
    start: dt.date,
    end: dt.date,
    *,
    retrieved_at: str,
    env: Mapping[str, str] | None = None,
    fetch: cpi.Fetch | None = None,
) -> inflation.CpiSeries:
    """Pick a monthly CPI source for ``region``.

    Order: the user's CSV; the official keyed API when its key is set (TCMB EVDS for TR, FRED
    for US), which is the most current; otherwise the OECD's public API (CC BY 4.0), with FRED's
    public CSV as the US fallback when the OECD is unreachable or rate-limited. Keyless OECD
    data can lag national releases (Türkiye's series ends 2025-12 as of 2026-09).
    """
    env = os.environ if env is None else env
    region = region.upper()
    csv_path = env.get(f"REALMARKET_CPI_CSV_{region}")
    if csv_path:
        return inflation.load_csv(Path(csv_path), region=region, retrieved_at=retrieved_at)
    if region == "US":
        if env.get(cpi.FRED_KEY_ENV, "").strip():
            return cpi.fred_us_cpi(
                start, env=env, fetch=fetch or cpi.http_fetch, retrieved_at=retrieved_at
            )
        try:
            return _oecd(region, start, fetch=fetch, retrieved_at=retrieved_at)
        except ToolError as error:
            if not error.retryable:
                raise
            # The same BLS series; FRED's download licence covers personal use.
            return cpi.fred_us_cpi_keyless(start, fetch=fetch, retrieved_at=retrieved_at)
    if region == "TR" and env.get(cpi.EVDS_KEY_ENV, "").strip():
        return cpi.evds_tr_cpi(
            start, end, env=env, fetch=fetch or cpi.http_fetch, retrieved_at=retrieved_at
        )
    if region in cpi.OECD_REGIONS:
        return _oecd(region, start, fetch=fetch, retrieved_at=retrieved_at)
    raise ToolError(
        ErrorCode.UNSUPPORTED,
        f"No built-in CPI source for region {region!r}.",
        f"Use an OECD member code such as TR, US, DE or GB, or set REALMARKET_CPI_CSV_{region} "
        "to a monthly CPI CSV file (columns: month,cpi_index).",
        {"region": region},
    )


# The OECD's anonymous API allows 60 downloads per hour per IP, so each region's series is
# fetched once (from OECD_CACHE_FROM) and reused for OECD_CACHE_SECONDS. The cached series keeps
# its original retrieval time, so provenance stays truthful.
OECD_CACHE_SECONDS = 6 * 3600
OECD_CACHE_FROM = dt.date(1990, 1, 1)
_oecd_cache: dict[str, tuple[float, inflation.CpiSeries]] = {}


def _oecd(
    region: str, start: dt.date, *, fetch: cpi.Fetch | None, retrieved_at: str
) -> inflation.CpiSeries:
    if fetch is not None:  # an injected fetch (tests) is never cached
        return cpi.oecd_cpi(region, start, fetch=fetch, retrieved_at=retrieved_at)
    cached = _oecd_cache.get(region)
    fresh = cached and time.monotonic() - cached[0] < OECD_CACHE_SECONDS
    if cached and fresh and cached[1].first_month <= inflation.month_of(start):
        return cached[1]
    series = cpi.oecd_cpi(region, min(start, OECD_CACHE_FROM), retrieved_at=retrieved_at)
    _oecd_cache[region] = (time.monotonic(), series)
    return series


def load_news_provider() -> NewsProvider:
    """GDELT is free and keyless, so it is the default; set the variable to 'none' to disable."""
    choice = os.environ.get(NEWS_PROVIDER_ENV, "gdelt").strip().lower()
    if choice == "gdelt":
        from realmarket_mcp.providers.gdelt import GdeltNewsProvider

        return GdeltNewsProvider()
    raise ToolError(
        ErrorCode.UNSUPPORTED,
        "News search is disabled." if choice == "none" else f"Unknown news provider {choice!r}.",
        f"Set {NEWS_PROVIDER_ENV}=gdelt in the MCP server's environment to enable news search.",
        {"provider": choice},
    )


FINANCIALS_PROVIDER_ENV = "REALMARKET_FINANCIALS_PROVIDER"


def load_financials_provider(
    symbol: str, *, retrieved_at: str, env: Mapping[str, str] | None = None
) -> FinancialsProvider:
    """``auto`` (default): SEC EDGAR for US tickers and CIKs when a contact e-mail is set (it
    is official and needs no key), otherwise the price provider's statements. ``sec`` or
    ``price`` force one source."""
    env = os.environ if env is None else env
    choice = env.get(FINANCIALS_PROVIDER_ENV, "auto").strip().lower()
    if choice not in {"auto", "sec", "price"}:
        raise ToolError(
            ErrorCode.UNSUPPORTED,
            f"Unknown financials provider {choice!r}.",
            f"Set {FINANCIALS_PROVIDER_ENV} to one of: auto, sec, price.",
        )
    contact = sec.contact_from(env)
    us_symbol = sec.looks_like_us_symbol(symbol)
    if choice == "sec" or (choice == "auto" and us_symbol and contact):
        if not contact:
            raise ToolError(
                ErrorCode.MISSING_API_KEY,
                "SEC EDGAR needs a contact e-mail address.",
                "Ask the user to fill in 'E-mail for SEC EDGAR' in the plugin or extension "
                f"settings ({sec.CONTACT_ENV}); no key or sign-up is needed.",
            )
        edgar = sec.SecEdgarProvider(contact, retrieved_at=retrieved_at)
        if choice == "sec":
            return edgar
        return _WithFallback(edgar, lambda: _price_financials(retrieved_at))
    return _price_financials(retrieved_at, us_symbol=us_symbol and choice == "auto")


class _WithFallback:
    """SEC first; for what the SEC cannot cover (IFRS filers such as TSM, tickers it does not
    list) the configured price provider's statements, if there is one."""

    def __init__(self, primary: FinancialsProvider, fallback: Callable[[], FinancialsProvider]):
        self.name = primary.name
        self._primary, self._fallback = primary, fallback

    def financials(self, symbol: str) -> FinancialStatements:
        try:
            return self._primary.financials(symbol)
        except ToolError as error:
            if error.code not in {ErrorCode.NO_DATA_IN_RANGE, ErrorCode.UNKNOWN_SYMBOL}:
                raise
            try:
                secondary = self._fallback()
            except ToolError:
                raise error from None
            return secondary.financials(symbol)


def _price_financials(retrieved_at: str, *, us_symbol: bool = False) -> FinancialsProvider:
    try:
        provider = load_price_provider(retrieved_at=retrieved_at)
    except ToolError as error:
        if us_symbol:
            raise ToolError(
                error.code,
                "No source for financial statements is configured.",
                "Ask the user to fill in a setting: for US companies 'E-mail for SEC EDGAR' "
                f"({sec.CONTACT_ENV}; official and free), for other markets tick 'Use Yahoo "
                f"Finance' ({USE_YAHOO_ENV}); then restart the app.",
            ) from None
        raise
    if not hasattr(provider, "financials"):
        raise ToolError(
            ErrorCode.UNSUPPORTED,
            f"The {provider.name} provider has no financial statements.",
            f"Set {PROVIDER_ENV}=yahoo, or {sec.CONTACT_ENV} for US companies.",
        )
    return cast(FinancialsProvider, provider)
