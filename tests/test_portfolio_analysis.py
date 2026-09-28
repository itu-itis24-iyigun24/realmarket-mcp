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
LATER = dt.date(2025, 1, 10)  # a year on: an annual rate over 8 days overflows


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
    assert totals["total_return_on_purchases"] == pytest.approx(1815 / 2510, abs=1e-6)
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


def test_a_trade_on_a_closed_day_happens_at_the_next_session() -> None:
    """Saturday 6 January 2024: the order fills on Monday the 8th at 220, not at Friday's 180,
    a price from before the date the user gave (fixture TTT)."""
    result = run([tx("buy", "2024-01-06", quantity=1)])
    assert result.data["holdings"][0]["cost_basis"] == 220
    assert any(
        f.startswith("Borsanın kapalı olduğu bir güne yazılan işlem") and "8 Ocak 2024" in f
        for f in result.facts
    )


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


def test_a_month_alone_uses_its_first_session() -> None:
    result = run([tx("buy", "2023-06", quantity=4)])
    assert result.data["holdings"][0]["cost_basis"] == 600  # the 2023-06-30 close, 150
    flag = next(f for f in result.quality_flags if f.code == "date_assumed")
    assert "buy TTT on 2023-06-30" in flag.message


class AsciiSearchProvider(FixtureProvider):
    """A source that, like Yahoo, finds 'Turk' but not 'Türk'."""

    def search(self, query: str, limit: int) -> Any:
        return (
            []
            if query != query.encode("ascii", "ignore").decode()
            else super().search(query, limit)
        )


def test_search_retries_without_turkish_letters() -> None:
    result = tools.search_assets(
        AsciiSearchProvider(FIXTURES), "Alpha A\u0131rlines", 5, today=TODAY, retrieved_at="x"
    )
    assert [r["symbol"] for r in result.data["results"]] == ["AAA"]


def test_comparison_covers_each_holdings_own_period() -> None:
    result = tools.analyze_portfolio(
        FixtureProvider(FIXTURES),
        [tx("buy", "2024-01-02", quantity=1)],
        compare_with="AAA",
        today=LATER,
    )
    # TTT 200 -> 220 from 2024-01-02 to the last session; AAA 100 -> 120 on the same days.
    assert result.data["holdings"][0]["comparison"] == {
        "with": "AAA",
        "from": "2024-01-02",
        "to": "2024-01-08",
        "holding_price_return": pytest.approx(0.1),
        "comparison_return": pytest.approx(0.2),
        "difference": pytest.approx(-0.1),
    }
    # The account's cash flows replayed in AAA: 200 TL buys 2 units at 100, worth 240 at 120.
    account = result.data["account_comparison"]
    assert account["from"] == "2024-01-02" and account["to"] == "2024-01-08"
    ours = tools.xirr([(dt.date(2024, 1, 2), -200.0), (LATER, 220.0)])
    theirs = tools.xirr([(dt.date(2024, 1, 2), -200.0), (LATER, 240.0)])
    assert account["money_weighted_return_annualized"] == pytest.approx(ours, abs=1e-5)
    assert account["comparison_money_weighted_return_annualized"] == pytest.approx(theirs, abs=1e-5)
    assert account["difference"] < 0


def test_a_sold_out_holding_is_compared_up_to_the_sale() -> None:
    result = tools.analyze_portfolio(
        FixtureProvider(FIXTURES),
        [
            tx("buy", "2024-01-02", quantity=1),
            tx("sell", "2024-01-05", quantity=1),
            tx("dividend", "2024-01-08", amount=1),  # paid after the sale: not the end
        ],
        compare_with="AAA",
        today=TODAY,
    )
    comparison = result.data["holdings"][0]["comparison"]
    assert (comparison["to"], comparison["holding_price_return"]) == ("2024-01-05", -0.1)
    assert comparison["comparison_return"] == pytest.approx(0.05)


def test_no_comparison_unless_asked() -> None:
    result = run([tx("buy", "2024-01-02", quantity=1)])
    assert "comparison" not in result.data["holdings"][0]


class LateSplitProvider(FixtureProvider):
    """TTT with a 2:1 split on 2023-07-20, weeks after the month's start."""

    def daily_bars(self, symbol: str, start: dt.date, end: dt.date) -> Any:
        series = super().daily_bars(symbol, start, end)
        return dataclasses.replace(series, splits=((dt.date(2023, 7, 20), 2.0),))


def test_a_bonus_given_as_a_month_is_the_split_in_that_month() -> None:
    result = tools.analyze_portfolio(
        LateSplitProvider(FIXTURES),
        [tx("buy", "2023-01-02", quantity=10, price=100), tx("bonus", "2023-07", quantity=10)],
        today=TODAY,
    )
    # Recorded once by the customer, not applied a second time: 20 shares, not 40.
    assert result.data["holdings"][0]["quantity"] == 20
    assert "split_applied" not in {f.code for f in result.quality_flags}
