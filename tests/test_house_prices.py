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
    house = result.data["house_prices"]
    assert house["house_price_return"] == pytest.approx(0.8)
    assert (house["from_month"], house["to_month"]) == ("2023-01", "2023-12")  # published late
    # The asset over the same months: 100 on 2023-01-02 -> 150, its last close by 2023-12-31.
    assert house["asset_return_same_months"] == pytest.approx(0.5)
    assert house["asset_beat_house_prices"] is False  # +50% against +80%; TTT ends at +100%
    assert house["house_price_real_return"] is None  # this CPI has no December 2023 figure
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
    assert result.data["house_prices"] is None
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


def test_an_empty_evds_series_says_so() -> None:
    def fetch(url: str, headers: object) -> bytes:
        return b'{"items": [{"Tarih": "2007-1", "TP_KFE_TR": null}]}'

    with pytest.raises(ToolError) as raised:
        config.load_house_prices(
            "TR",
            dt.date(2006, 1, 1),
            dt.date(2007, 12, 1),
            retrieved_at=STAMP,
            env={cpi.EVDS_KEY_ENV: "k"},
            fetch=fetch,
        )
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE and "later" in raised.value.hint


def test_turkish_notes_only_for_tl_assets() -> None:
    usd = tools.compare_real_return(
        FixtureProvider(FIXTURES),
        lambda *_: CPI,
        "BBB",
        start="2024-01-01",
        end="2024-01-26",
        today=dt.date(2024, 2, 1),
        inflation_region="TR",
    )
    assert not any("minimum wage" in n or "house price" in n for n in usd.notes)


def test_house_price_real_return_uses_cpi_over_the_same_months() -> None:
    kfe = index({(2023, 1): 100.0, (2023, 12): 180.0})
    cpi_series = CpiSeries("TR", "t", "C", STAMP, {(2023, 1): 100.0, (2023, 12): 200.0})
    result = tools.compare_real_return(
        FixtureProvider(FIXTURES),
        lambda *_: cpi_series,
        "TTT",
        start="2023-01-01",
        end="2024-01-02",
        today=dt.date(2024, 2, 1),
        load_house=lambda *_: kfe,
    )
    # Houses +80% while prices doubled: a 10% real loss, whatever the nominal gain.
    assert result.data["house_prices"]["house_price_real_return"] == pytest.approx(-0.1)
    assert any("(reel -%10,0)" in f for f in result.facts)


def test_an_amount_turns_the_figures_into_money() -> None:
    result = tools.compare_real_return(
        FixtureProvider(FIXTURES),
        lambda *_: CPI,
        "TTT",
        start="2023-01-01",
        end="2024-01-02",
        today=dt.date(2024, 2, 1),
        amount=1000,
    )
    # TTT 100 -> 200: 1,000 TL became 2,000 TL.
    assert any(
        f.startswith("Yatırılan 1.000,00 TL 2 Ocak 2024 itibarıyla 2.000,00 TL")
        for f in result.facts
    )
    # Each alternative in money too, so the answer never multiplies a percentage itself.
    assert any(
        "altına yatırılsaydı" in f and "(1.000,00 TL → 1.666,67 TL)" in f for f in result.facts
    )
    assert any("asgari ücret" in f and "(1.000,00 TL → 1.998,65 TL)" in f for f in result.facts)
    # The dollar figure names its asset: Haiku read "dolar cinsinden getiri" as the dollar's.
    assert (
        "TTT, dolar cinsinden ölçüldüğünde 2 Ocak 2023 – 2 Ocak 2024 arasında +%33,3 getirdi."
        in result.facts
    )
    with pytest.raises(ToolError):
        tools.compare_real_return(
            FixtureProvider(FIXTURES), lambda *_: CPI, "TTT", start="2023-01-01",
            today=dt.date(2024, 2, 1), amount=-5,
        )  # fmt: skip
