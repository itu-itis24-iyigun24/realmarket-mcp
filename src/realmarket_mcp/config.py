"""Runtime configuration, read from environment variables only."""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Mapping
from pathlib import Path

from realmarket_mcp import inflation
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.providers import cpi
from realmarket_mcp.providers.base import PriceProvider

PROVIDER_ENV = "REALMARKET_PRICE_PROVIDER"
FIXTURE_DIR_ENV = "REALMARKET_FIXTURE_DIR"


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


CURRENCY_REGIONS = {"TRY": "TR", "USD": "US"}
SUPPORTED_REGIONS = ("TR", "US")


def default_region(currency: str) -> str | None:
    return CURRENCY_REGIONS.get(currency.upper())


def load_cpi(
    region: str,
    start: dt.date,
    end: dt.date,
    *,
    retrieved_at: str,
    env: Mapping[str, str] | None = None,
    fetch: cpi.Fetch = cpi.http_fetch,
) -> inflation.CpiSeries:
    """A user CSV wins over an API, so anyone can bring their own series for any region."""
    env = os.environ if env is None else env
    region = region.upper()
    csv_path = env.get(f"REALMARKET_CPI_CSV_{region}")
    if csv_path:
        return inflation.load_csv(Path(csv_path), region=region, retrieved_at=retrieved_at)
    if region == "US":
        return cpi.fred_us_cpi(start, env=env, fetch=fetch, retrieved_at=retrieved_at)
    if region == "TR":
        return cpi.evds_tr_cpi(start, end, env=env, fetch=fetch, retrieved_at=retrieved_at)
    raise ToolError(
        ErrorCode.UNSUPPORTED,
        f"No built-in CPI source for region {region!r}.",
        f"Use one of {', '.join(SUPPORTED_REGIONS)}, or set REALMARKET_CPI_CSV_{region} to a "
        "monthly CPI CSV file (columns: month,cpi_index).",
        {"region": region},
    )
