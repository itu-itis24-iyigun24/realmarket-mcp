from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from realmarket_mcp import periods, tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.providers.fixture import FixtureProvider

FIXTURES = Path(__file__).parent / "fixtures" / "basic"
TODAY = dt.date(2024, 1, 10)


@pytest.fixture
def provider() -> FixtureProvider:
    return FixtureProvider(FIXTURES)


def test_search_ranks_exact_symbol_first(provider: FixtureProvider) -> None:
    result = tools.search_assets(provider, "aaa", 10, today=TODAY, retrieved_at="t")
    assert [r["symbol"] for r in result.data["results"]] == ["AAA"]


def test_search_matches_names(provider: FixtureProvider) -> None:
    result = tools.search_assets(provider, "bank", 10, today=TODAY, retrieved_at="t")
    assert result.data["results"][0]["currency"] == "USD"


def test_search_rejects_an_empty_query(provider: FixtureProvider) -> None:
    with pytest.raises(ToolError) as raised:
        tools.search_assets(provider, "  ", 10, today=TODAY, retrieved_at="t")
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


def test_price_summary_figures(provider: FixtureProvider) -> None:
    result = tools.get_price_summary(provider, "AAA", "1m", today=TODAY)
    data = result.data
    assert data["total_return"] == pytest.approx(0.2)
    assert data["max_drawdown"] == pytest.approx(-0.1)
    assert data["max_drawdown_peak_date"] == "2024-01-03"
    assert data["sessions"] == 5
    assert data["annualized_return"] is None  # span too short to annualize
    assert data["currency"] == "TRY"
    assert result.provenance[0].data_version.startswith("sha256:")
    assert result.quality_flags == ()


def test_price_summary_explicit_start_overrides_period(provider: FixtureProvider) -> None:
    result = tools.get_price_summary(provider, "AAA", "max", start="2024-01-04", today=TODAY)
    assert result.data["first_close"] == 99.0
    assert result.data["total_return"] == pytest.approx(120 / 99 - 1, abs=1e-6)


def test_price_summary_surfaces_quality_problems(provider: FixtureProvider) -> None:
    result = tools.get_price_summary(
        provider, "BBB", "1m", end="2024-01-26", today=dt.date(2024, 2, 1)
    )
    codes = {flag.code for flag in result.quality_flags}
    assert codes == {"placeholder_bars", "missing_close", "gap", "suspicious_move"}


def test_unknown_symbol_points_to_search(provider: FixtureProvider) -> None:
    with pytest.raises(ToolError) as raised:
        tools.get_price_summary(provider, "IDX", "1y", today=TODAY)
    assert raised.value.code is ErrorCode.UNKNOWN_SYMBOL
    assert "search_assets" in raised.value.hint


def test_empty_range_is_no_data(provider: FixtureProvider) -> None:
    with pytest.raises(ToolError) as raised:
        tools.get_price_summary(provider, "AAA", "1y", end="2023-06-01", today=TODAY)
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE


def test_result_is_deterministic(provider: FixtureProvider) -> None:
    first = tools.get_price_summary(provider, "AAA", "1m", today=TODAY).to_dict()
    second = tools.get_price_summary(provider, "AAA", "1m", today=TODAY).to_dict()
    assert first == second


@pytest.mark.parametrize(
    ("period", "expected_start"),
    [
        ("1m", dt.date(2024, 2, 29)),  # from 2024-03-31: clamped to the month's last day
        ("1y", dt.date(2023, 3, 31)),
        ("ytd", dt.date(2024, 1, 1)),
    ],
)
def test_periods_resolve_relative_to_end(period: periods.Period, expected_start: dt.date) -> None:
    start, end = periods.resolve(period, None, None, today=dt.date(2024, 3, 31))
    assert (start, end) == (expected_start, dt.date(2024, 3, 31))


def test_future_end_is_capped_at_today() -> None:
    _, end = periods.resolve("1m", None, "2030-01-01", today=TODAY)
    assert end == TODAY


def test_bad_dates_are_invalid_arguments() -> None:
    with pytest.raises(ToolError) as raised:
        periods.resolve("1y", "31/01/2024", None, today=TODAY)
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


def test_nan_closes_are_reported_as_missing(tmp_path: Path) -> None:
    (tmp_path / "bars").mkdir()
    (tmp_path / "assets.json").write_text(
        '[{"symbol": "N", "name": "N", "asset_class": "equity", "currency": "TRY",'
        ' "exchange": "X"}]'
    )
    (tmp_path / "bars" / "N.csv").write_text(
        "date,open,high,low,close,volume\n2024-01-02,1,1,1,1,1\n2024-01-03,1,1,1,nan,1\n"
        "2024-01-04,2,2,2,2,1\n"
    )
    result = tools.get_price_summary(FixtureProvider(tmp_path), "N", "1m", today=TODAY)
    assert "missing_close" in {f.code for f in result.quality_flags}
    assert result.data["sessions"] == 2
