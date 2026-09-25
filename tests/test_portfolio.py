from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from realmarket_mcp import tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.inflation import CpiSeries
from realmarket_mcp.providers.fixture import FixtureProvider

FIXTURES = Path(__file__).parent / "fixtures" / "basic"
TODAY = dt.date(2024, 1, 2)
# TTT (TRY): 100 on 2023-01-02, 150 on 2023-06-30, 200 on 2024-01-02.
# USDTRY: 20 until 2024-01-02, then 30.  GOLD (USD/oz): 1800, then 2000 on 2024-01-02.
LOTS = [
    {"symbol": "TTT", "date": "2023-01-02", "amount": 1000},  # 10 units
    {"symbol": "TTT", "date": "2023-06-30", "amount": 1500},  # 10 units
]


def approx(value: float) -> object:
    return pytest.approx(value, abs=1e-6)


def _cpi(values: dict[tuple[int, int], float]) -> tools.CpiLoader:
    series = CpiSeries("TR", "test", "TEST.CPI", "t", values)
    return lambda _r, _s, _e: series


def _no_cpi(_region: str, _start: dt.date, _end: dt.date) -> CpiSeries:
    raise ToolError(ErrorCode.MISSING_API_KEY, "No CPI source.", "Set a key.")


@pytest.fixture
def provider() -> FixtureProvider:
    return FixtureProvider(FIXTURES)


def test_value_return_and_real_return(provider: FixtureProvider) -> None:
    cpi = _cpi({(2023, 1): 100.0, (2023, 6): 130.0, (2024, 1): 160.0})
    data = tools.portfolio_real_return(provider, cpi, LOTS, today=TODAY).data

    assert data["currency"] == "TRY"
    assert (data["invested"], data["value_now"]) == (2500.0, 4000.0)
    assert data["return"] == approx(0.6)
    # Each payment in today's money: 1000 * 160/100 + 1500 * 160/130.
    invested_real = 1000 * 1.6 + 1500 * 160 / 130
    assert data["invested_in_todays_money"] == pytest.approx(invested_real, abs=0.01)
    assert data["real_return"] == approx(4000 / invested_real - 1)
    assert data["cumulative_inflation_since_first_purchase"] == approx(0.6)
    assert [lot["value_now"] for lot in data["lots"]] == [2000.0, 2000.0]


def test_alternatives_replay_the_same_payments(provider: FixtureProvider) -> None:
    result = tools.portfolio_real_return(provider, _no_cpi, LOTS, today=TODAY)
    alternatives = {a["alternative"]: a for a in result.data["alternatives"]}

    # USD: 1000/20 + 1500/20 = 125 dollars, worth 125 * 30 TRY today.
    assert alternatives["USD"]["value_now"] == 3750.0
    # Gold: the same dollars buy 125/1800 oz, worth 2000 USD/oz * 30 TRY/USD today.
    assert alternatives["GOLD"]["value_now"] == pytest.approx(125 / 1800 * 2000 * 30, abs=0.01)
    # USDTRY has no bar near 2023-06-30, so that conversion is flagged as stale.
    assert "stale_price" in {f.code for f in result.quality_flags}


def test_missing_cpi_keeps_everything_else(provider: FixtureProvider) -> None:
    result = tools.portfolio_real_return(provider, _no_cpi, LOTS, today=TODAY)
    assert result.data["real_return"] is None
    assert result.data["value_now"] == 4000.0
    assert "inflation_unavailable" in {f.code for f in result.quality_flags}


def test_foreign_asset_is_converted_both_ways(provider: FixtureProvider) -> None:
    lots = [{"symbol": "GOLD", "date": "2023-01-02", "amount": 1000}]
    data = tools.portfolio_real_return(
        provider, _no_cpi, lots, currency="TRY", compare_with=[], today=TODAY
    ).data
    # 1000 TRY -> 50 USD -> 50/1800 oz -> today 2000 USD/oz * 30 TRY/USD.
    assert data["value_now"] == pytest.approx(50 / 1800 * 2000 * 30, abs=0.01)


def test_xirr_matches_a_hand_computed_rate() -> None:
    flows = [(dt.date(2020, 1, 1), -100.0), (dt.date(2022, 1, 1), 121.0)]
    years = (dt.date(2022, 1, 1) - dt.date(2020, 1, 1)).days / 365.25
    assert tools.xirr(flows) == pytest.approx(1.21 ** (1 / years) - 1, abs=1e-9)
    assert tools.xirr([(dt.date(2020, 1, 1), -100.0)]) is None


@pytest.mark.parametrize(
    "lots",
    [
        [],
        [{"symbol": "TTT", "date": "2023-01-02", "amount": -5}],
        [{"symbol": "TTT", "date": "2030-01-01", "amount": 5}],
        [{"symbol": "TTT", "date": "02/01/2023", "amount": 5}],
    ],
)
def test_invalid_lots_are_rejected(
    provider: FixtureProvider, lots: list[dict[str, object]]
) -> None:
    with pytest.raises(ToolError) as raised:
        tools.portfolio_real_return(provider, _no_cpi, lots, today=TODAY)
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT
