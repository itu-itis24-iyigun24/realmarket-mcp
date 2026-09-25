"""Runtime configuration, read from environment variables only."""

from __future__ import annotations

import os
from pathlib import Path

from realmarket_mcp.contract import ErrorCode, ToolError
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
