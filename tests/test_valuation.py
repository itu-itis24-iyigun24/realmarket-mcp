"""get_valuation: market value and price multiples, with currency and TMS 29 handling.

Fixture prices (tests/fixtures/basic): TTT (TRY) last closes 220 on 2024-01-08; USDTRY is 30
from 2024-01-02. Statements are written per test into a temporary fixture directory.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from realmarket_mcp import tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.inflation import CpiSeries
from realmarket_mcp.models import FinancialStatements
from realmarket_mcp.providers.fixture import FixtureProvider

FIXTURES = Path(__file__).parent / "fixtures" / "basic"
TODAY = dt.date(2024, 1, 10)
QUARTER_ENDS = ("2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31")


def approx(value: float) -> Any:
    return pytest.approx(value, abs=1e-6)


def _no_cpi(*_: object) -> CpiSeries:
    raise ToolError(ErrorCode.MISSING_API_KEY, "no CPI", "set one")


def provider(tmp_path: Path, statements: dict[str, Any]) -> FixtureProvider:
    root = tmp_path / "fx"
    shutil.copytree(FIXTURES, root)
    (root / "financials").mkdir(exist_ok=True)
    (root / "financials" / "TTT.json").write_text(json.dumps(statements))
    return FixtureProvider(root)


def quarters(net: tuple[float, ...], revenue: float = 250.0, **last: float) -> list[dict[str, Any]]:
    rows = [
        {"end": e, "values": {"net_income": n, "revenue": revenue}}
        for e, n in zip(QUARTER_ENDS, net, strict=True)
    ]
    rows[-1]["values"].update(last)
    return rows


def run(p: FixtureProvider, cpi: tools.CpiLoader = _no_cpi, **kwargs: Any) -> tools.ToolResult:
    return tools.get_valuation(p, p, cpi, "TTT", today=TODAY, **kwargs)


def test_multiples_from_four_quarters(tmp_path: Path) -> None:
    st = {"currency": "USD", "industry": "Textiles", "shares_outstanding": 1000,
          "quarterly": quarters((10, 20, 30, 40), total_equity=2000)}  # fmt: skip
    data = run(provider(tmp_path, st)).data
    # Market value 220 TRY x 1000 = 220,000 TRY; statements in USD at 30 TRY per USD.
    assert data["market_cap"] == 220_000
    assert data["fx_to_trading_currency"] == approx(30.0)
    assert data["price_to_earnings"] == approx(220_000 / (100 * 30))
    assert data["price_to_book"] == approx(220_000 / (2000 * 30))
    assert data["price_to_sales"] == approx(220_000 / (1000 * 30))
    assert data["earnings_basis"] == "trailing_four_quarters"


def test_tms29_uses_the_reported_trailing_twelve_months(tmp_path: Path) -> None:
    year = {"end": "2023-12-31", "values": {"net_income": 40, "revenue": 900}}
    st = {"currency": "TRY", "industry": "Retail", "shares_outstanding": 1000,
          "quarterly": quarters((10, 10, 10, 10), total_equity=5000), "annual": [year],
          "ttm": {"end": "2023-12-31", "values": {"net_income": 50, "revenue": 1000}}}  # fmt: skip
    cpi = CpiSeries("TR", "t", "C", "t", {(2023, 12): 100.0, (2024, 1): 110.0})
    data = run(provider(tmp_path, st), lambda *_: cpi).data
    # The source's trailing figure, never a sum of its quarters; brought to January 2024 money.
    assert data["earnings_basis"] == "trailing_twelve_months_reported"
    assert data["restated_to_money_of"] == "2024-01"
    assert data["earnings"] == approx(55.0)
    assert data["price_to_earnings"] == approx(220_000 / 55)
    assert data["price_to_sales"] == approx(220_000 / 1100)
    assert data["price_to_book"] == approx(220_000 / 5500)
    old = CpiSeries("TR", "t", "C", "t", {(2023, 6): 90.0, (2023, 9): 100.0})
    late = run(provider(tmp_path / "b", st), lambda *_: old)
    assert "cpi_behind_price" in {f.code for f in late.quality_flags}


def test_tms29_without_a_reported_trailing_figure_gives_no_pe(tmp_path: Path) -> None:
    year = {"end": "2023-12-31", "values": {"net_income": 40, "revenue": 900}}
    st = {"currency": "TRY", "industry": "Retail", "shares_outstanding": 1000,
          "quarterly": quarters((10, 10, 10, 10), total_equity=5000), "annual": [year]}  # fmt: skip
    cpi = CpiSeries("TR", "t", "C", "t", {(2023, 12): 100.0, (2024, 1): 110.0})
    result = run(provider(tmp_path, st), lambda *_: cpi)
    data = result.data
    assert (data["price_to_earnings"], data["price_to_sales"], data["earnings_basis"]) == (
        None,
        None,
        None,
    )
    assert "TMS 29" in data["not_meaningful"]["pe"]
    assert data["price_to_book"] == approx(220_000 / 5500)  # P/B is still given
    assert "no_tms29_trailing_earnings" in {f.code for f in result.quality_flags}
    no_cpi = run(provider(tmp_path / "b", st))
    assert "inflation_unavailable" in {f.code for f in no_cpi.quality_flags}
    assert no_cpi.data["price_to_book"] == approx(220_000 / 5000)


def test_losses_and_missing_quarters(tmp_path: Path) -> None:
    gap = quarters((10, 20, 30, 40))
    del gap[1]  # a missing quarter: fall back to the fiscal year
    year = {"end": "2023-12-31", "values": {"net_income": -5, "revenue": 900}}
    st = {"currency": "TRY", "industry": "Banks", "shares_outstanding": 1000, "quarterly": gap,
          "annual": [year]}  # fmt: skip
    data = run(provider(tmp_path, st)).data
    assert data["earnings_basis"] == "latest_fiscal_year"
    assert data["price_to_earnings"] is None
    assert "not meaningful" in data["not_meaningful"]["pe"]
    assert data["price_to_sales"] == approx(220_000 / 900)


def _shares_from(count: float | None, as_of: dt.date | None = None) -> tools.SharesLookup:
    def lookup(quote: str) -> FinancialStatements:
        return FinancialStatements(quote, "TRY", None, None, "other-feed", "2024-01-10T00:00:00Z",
                                   (), (), shares_outstanding=count, shares_source="other feed",
                                   shares_as_of=as_of)  # fmt: skip

    return lookup


def test_share_count_sources(tmp_path: Path) -> None:
    st = {"currency": "TRY", "industry": "Banks", "quarterly": quarters((1, 1, 1, 1))}
    p = provider(tmp_path, st)
    with pytest.raises(ToolError) as raised:
        run(p)
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE
    result = run(p, shares_lookup=_shares_from(500.0, dt.date(2024, 1, 5)))
    assert result.data["market_cap"] == 110_000
    assert result.data["shares_as_of"] == "2024-01-05"
    assert "shares_from_other_source" in {f.code for f in result.quality_flags}
    shares_prov = [pv for pv in result.provenance if pv.dataset == "shares_outstanding"]
    assert [(pv.provider, pv.period_end) for pv in shares_prov] == [("other-feed", "2024-01-05")]


def test_share_counts_are_cross_checked(tmp_path: Path) -> None:
    st = {"currency": "TRY", "industry": "Banks", "shares_outstanding": 1000,
          "quarterly": quarters((1, 1, 1, 1))}  # fmt: skip
    p = provider(tmp_path, st)
    close = run(p, shares_lookup=_shares_from(1030.0))
    assert "shares_mismatch" not in {f.code for f in close.quality_flags}
    far = run(p, shares_lookup=_shares_from(8000.0))  # e.g. an ADR ratio, or an old count
    assert "shares_mismatch" in {f.code for f in far.quality_flags}
    assert far.data["market_cap"] == 220_000  # the statements' own count is used


def test_one_quarter_window_and_stale_price(tmp_path: Path) -> None:
    rows = quarters((10, 20, 30, 40))
    del rows[-1]["values"]["revenue"]  # latest quarter has earnings but no sales
    st = {"currency": "USD", "industry": "Banks", "shares_outstanding": 1000, "quarterly": rows}
    p = provider(tmp_path, st)
    data = run(p).data
    assert data["periods_used"] == list(QUARTER_ENDS)
    assert data["sales"] is None and "sales" in data["not_meaningful"]["ps"]
    late = tools.get_valuation(p, p, _no_cpi, "TTT", today=dt.date(2024, 1, 20))
    assert "stale_price" in {f.code for f in late.quality_flags}


def test_missing_quarter_falls_back_to_the_fiscal_year_with_a_flag(tmp_path: Path) -> None:
    rows = quarters((10, 20, 30, 40))
    del rows[1]
    year = {"end": "2023-12-31", "values": {"net_income": 50, "revenue": 900}}
    st = {"currency": "USD", "industry": "Retail", "shares_outstanding": 1000,
          "quarterly": rows, "annual": [year]}  # fmt: skip
    result = run(provider(tmp_path, st))
    assert "fiscal_year_basis" in {f.code for f in result.quality_flags}
    assert result.data["earnings_basis"] == "latest_fiscal_year"


def test_stale_statements_and_lei_symbols(tmp_path: Path) -> None:
    year = {"end": "2022-12-31", "values": {"net_income": 5, "revenue": 50}}
    st = {"currency": "TRY", "industry": "Banks", "shares_outstanding": 10, "annual": [year]}
    result = run(provider(tmp_path, st))
    assert "stale_statements" in {f.code for f in result.quality_flags}
    with pytest.raises(ToolError) as raised:
        tools.get_valuation(
            FixtureProvider(FIXTURES), FixtureProvider(FIXTURES), _no_cpi,
            "724500Y6DUVHQD6OXN27", today=TODAY,
        )  # fmt: skip
    assert "price_symbol" in raised.value.hint
