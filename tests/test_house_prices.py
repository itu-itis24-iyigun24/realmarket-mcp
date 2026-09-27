"""House price comparison (TCMB's KFE index), against fixture prices."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from realmarket_mcp import config, tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.inflation import CpiSeries
from realmarket_mcp.providers import cpi
from realmarket_mcp.providers.fixture import FixtureProvider

FIXTURES = Path(__file__).parent / "fixtures" / "basic"
STAMP = "2026-09-27T00:00:00Z"
CPI = CpiSeries("TR", "test", "CPI", STAMP, {(2023, 1): 100.0, (2024, 1): 150.0})


def index(values: dict[tuple[int, int], float]) -> CpiSeries:
    return CpiSeries("TR", "evds_house_price", "TP.KFE.TR", STAMP, values)


def test_compare_real_return_against_house_prices() -> None:
    # TTT: 100 on 2023-01-02, 200 on 2024-01-02. The index ends in December 2023.
    kfe = index({(2023, 1): 100.0, (2023, 6): 150.0, (2023, 12): 180.0})
    result = tools.compare_real_return(
        FixtureProvider(FIXTURES),
        lambda *_: CPI,
        "TTT",
        start="2023-01-01",
        end="2024-01-02",
        today=dt.date(2024, 2, 1),
        load_house=lambda *_: kfe,
    )
    data = result.data
    assert data["house_price_return"] == pytest.approx(0.8)
    assert data["house_price_window_end"] == "2023-12"  # published late: measured to there
    # The asset over the same months: 100 on 2023-01-02 -> 150, its last close by 2023-12-31.
    assert data["nominal_return_in_house_window"] == pytest.approx(0.5)
    assert data["beat_house_prices"] is False  # +50% against +80%, although TTT ends at +100%
    assert "evds_house_price" in {p.provider for p in result.provenance}
    assert any("rent" in note for note in result.notes)


def test_house_prices_unavailable_is_explained() -> None:
    def no_key(*_: object) -> CpiSeries:
        raise ToolError(ErrorCode.MISSING_API_KEY, "needs a key", "Set it.")

    result = tools.compare_real_return(
        FixtureProvider(FIXTURES),
        lambda *_: CPI,
        "TTT",
        start="2023-01-01",
        end="2024-01-02",
        today=dt.date(2024, 2, 1),
        load_house=no_key,
    )
    assert result.data["house_price_return"] is None
    assert "house_prices_unavailable" in {f.code for f in result.quality_flags}


def test_portfolio_replays_payments_into_housing() -> None:
    kfe = index({(2023, 1): 100.0, (2023, 12): 150.0})
    lots = [{"symbol": "TTT", "date": "2023-01-02", "amount": 1000}]
    result = tools.portfolio_real_return(
        FixtureProvider(FIXTURES),
        lambda *_: CPI,
        lots,
        compare_with=["HOUSE"],
        today=dt.date(2024, 1, 2),
        load_house=lambda *_: kfe,
    )
    (house,) = result.data["alternatives"]
    assert (house["alternative"], house["value_now"]) == ("HOUSE", 1500.0)
    assert house["valued_as_of"] == "2023-12-31"  # the last month the index covers


def test_evds_house_price_request() -> None:
    calls: list[str] = []

    def fetch(url: str, headers: object) -> bytes:
        calls.append(url)
        return b'{"items": [{"Tarih": "2026-7", "TP_KFE_TR10": "250.5"}]}'

    series = config.load_house_prices(
        "istanbul",
        dt.date(2026, 1, 1),
        dt.date(2026, 9, 1),
        retrieved_at=STAMP,
        env={cpi.EVDS_KEY_ENV: "k"},
        fetch=fetch,
    )
    assert "series=TP.KFE.TR10" in calls[0] and series.values == {(2026, 7): 250.5}
    with pytest.raises(ToolError) as raised:
        config.load_house_prices(
            "MARS",
            dt.date(2026, 1, 1),
            dt.date(2026, 9, 1),
            retrieved_at=STAMP,
            env={cpi.EVDS_KEY_ENV: "k"},
        )
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT
    with pytest.raises(ToolError) as raised:
        config.load_house_prices(
            "TR", dt.date(2026, 1, 1), dt.date(2026, 9, 1), retrieved_at=STAMP, env={}
        )
    assert raised.value.code is ErrorCode.MISSING_API_KEY
