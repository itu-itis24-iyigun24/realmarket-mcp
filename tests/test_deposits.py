"""TL deposit comparison: rolling deposit at TCMB's published weekly rates.

Live shape (verified 2026-09-27): EVDS `series=TP.TRY.MT02` returns
{"totalCount", "items": [{"Tarih": "18-09-2026", "YEARWEEK": "2026-38",
"TP_TRY_MT02": "44.02000000", "UNIXTIME": {...}}]}, one item per Friday.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from realmarket_mcp import config, tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.deposits import MAX_CARRY_DAYS, DepositRates, rates_from_rows
from realmarket_mcp.inflation import CpiSeries
from realmarket_mcp.providers import cpi
from realmarket_mcp.providers.fixture import FixtureProvider

FIXTURES = Path(__file__).parent / "fixtures" / "basic"
STAMP = "2026-09-27T00:00:00Z"


def rates(*points: tuple[dt.date, float]) -> DepositRates:
    return DepositRates("TRY", "evds_deposit", "TP.TRY.MT02", STAMP, tuple(points))


def test_growth_rolls_a_32_day_deposit_at_the_rate_in_force_at_each_opening() -> None:
    series = rates(
        (dt.date(2025, 1, 3), 36.5), (dt.date(2025, 1, 10), 73.0), (dt.date(2025, 1, 31), 73.0)
    )
    # Opened on 01-03 at 36.5% for 32 days (the 01-10 rate does not change an open deposit),
    # then renewed on 02-04 at 73% for the remaining 8 days.
    expected = (1 + 0.365 * 32 / 365) * (1 + 0.73 * 8 / 365)
    assert series.growth(dt.date(2025, 1, 3), dt.date(2025, 2, 12)) == pytest.approx(expected)
    assert series.growth(dt.date(2025, 1, 5), dt.date(2025, 1, 5)) == 1.0


def test_no_growth_outside_the_published_period() -> None:
    series = rates((dt.date(2025, 1, 3), 40.0))
    assert series.growth(dt.date(2025, 1, 2), dt.date(2025, 1, 6)) is None  # before the first rate
    late = dt.date(2025, 1, 3) + dt.timedelta(days=MAX_CARRY_DAYS + 1)
    assert series.growth(dt.date(2025, 1, 3), late) is None  # never extrapolated for long
    gap = rates((dt.date(2025, 1, 3), 40.0), (dt.date(2025, 6, 6), 40.0))  # months unpublished
    assert gap.growth(dt.date(2025, 1, 3), dt.date(2025, 6, 10)) is None


def test_rows_parse_and_reject_implausible_rates() -> None:
    parsed = rates_from_rows(
        [("10-01-2025", "45.5"), ("03-01-2025", "44.0"), ("17-01-2025", "")],
        currency="TRY", source="evds_deposit", series_id="TP.TRY.MT02", retrieved_at=STAMP,
    )  # fmt: skip
    assert parsed.observations == ((dt.date(2025, 1, 3), 44.0), (dt.date(2025, 1, 10), 45.5))
    with pytest.raises(ValueError):
        rates((dt.date(2025, 1, 3), float("nan")))


class Recorder:
    def __init__(self, body: object) -> None:
        self.body, self.calls = json.dumps(body).encode(), []  # type: ignore[var-annotated]

    def __call__(self, url: str, headers: Mapping[str, str]) -> bytes:
        self.calls.append((url, dict(headers)))
        return self.body


def test_evds_request_and_response() -> None:
    fetch = Recorder({"items": [{"Tarih": "18-09-2026", "TP_TRYTAS_MT02": "44.02000000"}]})
    env = {cpi.EVDS_KEY_ENV: "secret"}
    series = config.load_deposit_rates(
        "TRY", dt.date(2026, 9, 1), dt.date(2026, 9, 27), retrieved_at=STAMP, env=env, fetch=fetch
    )
    assert series.observations == ((dt.date(2026, 9, 18), 44.02),)
    assert series.series_id == "TP.TRYTAS.MT02"  # savings deposits of 1-3 months: the saver's
    url, headers = fetch.calls[0]
    assert "series=TP.TRYTAS.MT02" in url and "startDate=18-08-2026" in url  # rate at start
    assert headers == {"key": "secret"} and "secret" not in url


def test_periods_before_savings_rates_use_all_deposits_throughout() -> None:
    fetch = Recorder({"items": [{"Tarih": "07-01-2011", "TP_TRY_MT02": "7.50"}]})
    series = config.load_deposit_rates(
        "TRY", dt.date(2011, 1, 10), dt.date(2015, 1, 1), retrieved_at=STAMP,
        env={cpi.EVDS_KEY_ENV: "k"}, fetch=fetch,
    )  # fmt: skip
    assert series.series_id == "TP.TRY.MT02" and "series=TP.TRY.MT02&" in fetch.calls[0][0]


def test_evds_key_and_currency_are_required() -> None:
    with pytest.raises(ToolError) as raised:
        config.load_deposit_rates("TRY", dt.date(2026, 1, 1), dt.date(2026, 2, 1),
                                  retrieved_at=STAMP, env={})  # fmt: skip
    assert raised.value.code is ErrorCode.MISSING_API_KEY
    with pytest.raises(ToolError) as raised:
        config.load_deposit_rates("USD", dt.date(2026, 1, 1), dt.date(2026, 2, 1),
                                  retrieved_at=STAMP, env={cpi.EVDS_KEY_ENV: "k"})  # fmt: skip
    assert raised.value.code is ErrorCode.UNSUPPORTED


# TTT (TRY): 100 on 2023-01-02, 200 on 2024-01-02 (fixture). A flat 36.5% deposit rolled every
# 32 days over 365 days: 11 full terms and a 13-day remainder.
YEAR = (1 + 0.365 * 32 / 365) ** 11 * (1 + 0.365 * 13 / 365)
FLAT = rates(*((dt.date(2022, 12, 30) + dt.timedelta(weeks=w), 36.5) for w in range(53)))


def _deposit_loader(series: DepositRates) -> tools.DepositLoader:
    return lambda _c, _s, _e: series


def test_compare_real_return_adds_the_deposit_alternative() -> None:
    cpi_series = CpiSeries("TR", "test", "CPI", STAMP, {(2023, 1): 100.0, (2024, 1): 150.0})
    result = tools.compare_real_return(
        FixtureProvider(FIXTURES), lambda *_: cpi_series, "TTT", start="2023-01-01",
        end="2024-01-02", today=dt.date(2024, 2, 1), load_deposit=_deposit_loader(FLAT),
    )  # fmt: skip
    data = result.data
    deposit = YEAR - 1  # 2023-01-02 -> 2024-01-02
    assert data["deposit_return"] == pytest.approx(deposit, abs=1e-6)
    assert data["deposit_real_return"] == pytest.approx((1 + deposit) / 1.5 - 1, abs=1e-6)
    assert data["beat_deposit"] is True  # +100% against about +44%
    assert "evds_deposit" in {p.provider for p in result.provenance}
    assert any("stopaj" in n for n in result.notes)


def test_deposit_is_skipped_with_a_reason_when_unavailable() -> None:
    def no_key(*_: object) -> DepositRates:
        raise ToolError(ErrorCode.MISSING_API_KEY, "Deposit rates need a TCMB EVDS key.", "Set it.")

    cpi_series = CpiSeries("TR", "test", "CPI", STAMP, {(2023, 1): 100.0, (2024, 1): 150.0})
    result = tools.compare_real_return(
        FixtureProvider(FIXTURES), lambda *_: cpi_series, "TTT", start="2023-01-01",
        end="2024-01-02", today=dt.date(2024, 2, 1), load_deposit=no_key,
    )  # fmt: skip
    assert result.data["deposit_return"] is None and result.data["beat_deposit"] is None
    assert "deposit_unavailable" in {f.code for f in result.quality_flags}


def test_portfolio_replays_payments_into_a_deposit() -> None:
    lots = [{"symbol": "TTT", "date": "2023-01-02", "amount": 1000}]
    result = tools.portfolio_real_return(
        FixtureProvider(FIXTURES), lambda *_: CpiSeries("TR", "t", "C", STAMP, {(2023, 1): 1.0}),
        lots, compare_with=["DEPOSIT"], today=dt.date(2024, 1, 2),
        load_deposit=_deposit_loader(FLAT),
    )  # fmt: skip
    alternative = result.data["alternatives"][0]
    assert alternative["alternative"] == "DEPOSIT"
    assert alternative["value_now"] == pytest.approx(1000 * YEAR, abs=0.01)
    assert alternative["annualized_money_weighted"] == pytest.approx(
        YEAR ** (365.25 / 365) - 1, abs=1e-4
    )


def test_check_setup_reports_deposit_availability() -> None:
    assert config.describe_setup({})["deposit_rates"]["TRY"].startswith("unavailable")
    assert config.describe_setup({cpi.EVDS_KEY_ENV: "k"})["deposit_rates"]["TRY"] == "evds"
