"""Runtime configuration, read from environment variables only."""

from __future__ import annotations

import datetime as dt
import os
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
    choice = os.environ.get(PROVIDER_ENV, "fixture").strip().lower()
    if choice == "fixture":
        root = os.environ.get(FIXTURE_DIR_ENV)
        if not root or not Path(root, "assets.json").exists():
            raise ToolError(
                ErrorCode.MISSING_API_KEY,
                "No price data source is configured.",
                f"Set {PROVIDER_ENV} to a supported provider in the MCP server's environment, "
                f"or set {FIXTURE_DIR_ENV} to a fixture directory for offline use.",
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
    for US), which is the most current; otherwise a keyless source (FRED's public CSV for US,
    the OECD for TR and other OECD members). Keyless OECD data can lag national releases.
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
        return cpi.fred_us_cpi_keyless(start, fetch=fetch, retrieved_at=retrieved_at)
    if region == "TR" and env.get(cpi.EVDS_KEY_ENV, "").strip():
        return cpi.evds_tr_cpi(
            start, end, env=env, fetch=fetch or cpi.http_fetch, retrieved_at=retrieved_at
        )
    if region in cpi.OECD_REGIONS:
        return cpi.oecd_cpi(region, start, fetch=fetch, retrieved_at=retrieved_at)
    raise ToolError(
        ErrorCode.UNSUPPORTED,
        f"No built-in CPI source for region {region!r}.",
        f"Use an OECD member code such as TR, US, DE or GB, or set REALMARKET_CPI_CSV_{region} "
        "to a monthly CPI CSV file (columns: month,cpi_index).",
        {"region": region},
    )


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
                f"Set {sec.CONTACT_ENV} to your e-mail address in the MCP server's environment "
                "(no key or sign-up needed).",
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
                f"For US companies set {sec.CONTACT_ENV} to your e-mail address (SEC EDGAR, "
                f"official and free); for other markets set {PROVIDER_ENV}=yahoo.",
            ) from None
        raise
    if not hasattr(provider, "financials"):
        raise ToolError(
            ErrorCode.UNSUPPORTED,
            f"The {provider.name} provider has no financial statements.",
            f"Set {PROVIDER_ENV}=yahoo, or {sec.CONTACT_ENV} for US companies.",
        )
    return cast(FinancialsProvider, provider)
