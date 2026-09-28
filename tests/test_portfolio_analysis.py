"""analyze_portfolio: an account's buys, sells, bonus issues and dividends, hand-checked.

Fixture TTT (TRY) closes: 100 on 2023-01-02, 150 on 2023-06-30, 200 on 2024-01-02, 180 on
2024-01-05, 220 on 2024-01-08.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path
from typing import Any

import pytest

from realmarket_mcp import tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.providers.fixture import FixtureProvider

FIXTURES = Path(__file__).parent / "fixtures" / "basic"
TODAY = dt.date(2024, 1, 10)


def tx(kind: str, day: str, **values: Any) -> dict[str, Any]:
    return {"type": kind, "symbol": "TTT", "date": day, **values}


def run(transactions: list[dict[str, Any]]) -> tools.ToolResult:
    return tools.analyze_portfolio(FixtureProvider(FIXTURES), transactions, today=TODAY)


def test_buys_sells_and_dividends_by_average_cost() -> None:
    result = run(
        [
            tx("buy", "2023-01-02", quantity=10, price=100, fee=5),  # cost 1005
            tx("buy", "2023-06-30", quantity=10, price=150, fee=5),  # cost 1505, avg 125.5
            tx("sell", "2024-01-02", quantity=5, price=200, fee=5),  # 995 - 627.5 = 367.5
            tx("dividend", "2024-01-05", amount=30),
        ]
    )
    (holding,) = result.data["holdings"]
    assert holding["quantity"] == 15
    assert holding["average_cost"] == pytest.approx(125.5)
    assert holding["realized_pnl"] == 367.5
    assert holding["market_value"] == 3300  # 15 x 220
    assert holding["unrealized_pnl"] == 3300 - 1882.5
    assert holding["dividends_received"] == 30
    assert holding["total_pnl"] == 367.5 + 1417.5 + 30
    assert holding["total_return_on_purchases"] == pytest.approx(1815 / 2510, abs=1e-6)
    totals = result.data["totals"]
    assert (totals["purchases"], totals["sale_proceeds"]) == (2510, 995)
    assert totals["total_pnl"] == 1815
    assert totals["money_weighted_return_annualized"] > 0
    assert result.data["concentration"]["largest"] == {"symbol": "TTT", "weight": 1.0}


def test_bonus_issue_adds_shares_at_no_cost() -> None:
    result = run(
        [
            tx("buy", "2023-01-02", quantity=10, price=100),
            tx("bonus", "2023-06-30", quantity=10),  # 1:1 bedelsiz
        ]
    )
    (holding,) = result.data["holdings"]
    assert (holding["quantity"], holding["average_cost"]) == (20, 50)
    assert holding["unrealized_pnl"] == 20 * 220 - 1000


def test_missing_price_uses_the_close_and_says_so() -> None:
    result = run([tx("buy", "2023-06-30", quantity=4)])
    assert result.data["holdings"][0]["cost_basis"] == 600  # 4 x 150
    assert "price_assumed" in {f.code for f in result.quality_flags}


def test_selling_more_than_held_is_refused() -> None:
    with pytest.raises(ToolError) as raised:
        run([tx("buy", "2023-01-02", quantity=1, price=100), tx("sell", "2024-01-02", quantity=2)])
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT
    assert "only 1 are held" in raised.value.message


def test_closed_positions_keep_their_realized_result() -> None:
    result = run(
        [
            tx("buy", "2023-01-02", quantity=10, price=100),
            tx("sell", "2023-06-30", quantity=10, price=150),
        ]
    )
    (holding,) = result.data["holdings"]
    assert (holding["quantity"], holding["market_value"], holding["realized_pnl"]) == (0, 0, 500)
    assert result.data["concentration"]["open_holdings"] == 0
    assert result.data["best"] == {"symbol": "TTT", "total_return_on_purchases": 0.5}


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "swap", "symbol": "TTT", "date": "2023-01-02"},
        {"type": "buy", "symbol": "TTT", "date": "2023-01-02"},
        {"type": "dividend", "symbol": "TTT", "date": "2023-01-02"},
        {"type": "buy", "symbol": "TTT", "date": "2030-01-02", "quantity": 1},
        {"type": "buy", "symbol": "TTT", "date": "2023-01-02", "quantity": -1},
    ],
)
def test_malformed_transactions_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(ToolError) as raised:
        run([bad])
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


class SplitProvider(FixtureProvider):
    """TTT with a 1:1 bonus issue on 2023-06-30: the fixture closes are split-adjusted, so the
    price actually traded before that day was twice the listed close."""

    def daily_bars(self, symbol: str, start: dt.date, end: dt.date) -> Any:
        series = super().daily_bars(symbol, start, end)
        return dataclasses.replace(series, splits=((dt.date(2023, 6, 30), 2.0),))


def test_a_reported_bonus_issue_is_applied_when_not_recorded() -> None:
    provider = SplitProvider(FIXTURES)
    result = tools.analyze_portfolio(provider, [tx("buy", "2023-01-02", quantity=10)], today=TODAY)
    (holding,) = result.data["holdings"]
    # Bought 10 at 200 (100 x 2, as traded then); 20 shares after the bonus, worth 220 each.
    assert (holding["cost_basis"], holding["quantity"]) == (2000, 20)
    assert holding["market_value"] == 4400
    assert "split_applied" in {f.code for f in result.quality_flags}


def test_a_recorded_bonus_is_not_applied_twice() -> None:
    provider = SplitProvider(FIXTURES)
    result = tools.analyze_portfolio(
        provider,
        [tx("buy", "2023-01-02", quantity=10, price=200), tx("bonus", "2023-07-03", quantity=10)],
        today=TODAY,
    )
    assert result.data["holdings"][0]["quantity"] == 20
    assert "split_applied" not in {f.code for f in result.quality_flags}
