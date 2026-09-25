from __future__ import annotations

import datetime as dt
import math

import pytest

from realmarket_mcp import analytics

D = dt.date


def test_total_return_is_simple_return() -> None:
    assert analytics.total_return(100.0, 120.0) == pytest.approx(0.2)


def test_annualized_return_compounds_over_calendar_time() -> None:
    # +21% over two calendar years (2020-01-01 -> 2022-01-01) is about +10% a year.
    result = analytics.annualized_return(0.21, D(2020, 1, 1), D(2022, 1, 1))
    assert result == pytest.approx(0.1, abs=1e-3)


def test_annualized_return_is_withheld_for_short_spans() -> None:
    assert analytics.annualized_return(0.05, D(2024, 1, 1), D(2024, 3, 1)) is None


def test_volatility_of_constant_growth_is_zero() -> None:
    closes = [100.0 * 1.01**i for i in range(10)]
    vol = analytics.annualized_volatility(closes)
    assert vol is not None and vol == pytest.approx(0.0, abs=1e-12)


def test_volatility_matches_hand_computation() -> None:
    closes = [100.0, 110.0, 99.0]
    logs = [math.log(1.1), math.log(0.9)]
    mean = sum(logs) / 2
    expected = math.sqrt(sum((x - mean) ** 2 for x in logs) / 1) * math.sqrt(252)
    assert analytics.annualized_volatility(closes) == pytest.approx(expected)


def test_max_drawdown_finds_peak_and_trough() -> None:
    dates = [D(2024, 1, d) for d in (2, 3, 4, 5, 8)]
    drawdown = analytics.max_drawdown(dates, [100.0, 110.0, 99.0, 105.0, 120.0])
    assert drawdown is not None
    assert drawdown.depth == pytest.approx(-0.1)
    assert (drawdown.peak_date, drawdown.trough_date) == (D(2024, 1, 3), D(2024, 1, 4))


def test_max_drawdown_is_zero_for_a_rising_series() -> None:
    dates = [D(2024, 1, d) for d in (2, 3)]
    drawdown = analytics.max_drawdown(dates, [1.0, 2.0])
    assert drawdown is not None and drawdown.depth == 0.0


def test_real_return_uses_the_fisher_relation_not_subtraction() -> None:
    # +50% nominal against 40% inflation is +7.14% real, not +10%.
    assert analytics.real_return(0.5, 0.4) == pytest.approx(1.5 / 1.4 - 1)
