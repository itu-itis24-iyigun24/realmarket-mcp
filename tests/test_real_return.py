from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from realmarket_mcp import tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.inflation import CpiSeries
from realmarket_mcp.providers.fixture import FixtureProvider


def approx(value: float) -> object:
    return pytest.approx(value, abs=1e-6)  # outputs are rounded to 6 decimals


FIXTURES = Path(__file__).parent / "fixtures" / "basic"
TODAY = dt.date(2024, 2, 1)


def _cpi(values: dict[tuple[int, int], float], region: str = "TR") -> tools.CpiLoader:
    series = CpiSeries(region, "test", "TEST.CPI", "2024-02-01T00:00:00Z", values)
    return lambda _region, _start, _end: series


@pytest.fixture
def provider() -> FixtureProvider:
    return FixtureProvider(FIXTURES)


def _run(provider: FixtureProvider, cpi: tools.CpiLoader, **kwargs: object) -> tools.ToolResult:
    args: dict[str, object] = {"start": "2023-01-01", "end": "2024-01-02", **kwargs}
    return tools.compare_real_return(provider, cpi, "TTT", today=TODAY, **args)  # type: ignore[arg-type]


def test_real_usd_and_gold_returns_match_hand_computation(provider: FixtureProvider) -> None:
    result = _run(provider, _cpi({(2023, 1): 100.0, (2024, 1): 160.0}))
    data = result.data

    assert data["nominal_return"] == approx(1.0)  # 100 -> 200
    assert data["cumulative_inflation"] == approx(0.6)  # CPI 100 -> 160
    assert data["real_return"] == approx(0.25)  # 2.0 / 1.6 - 1, not 1.0 - 0.6
    assert data["real_return_positive"] is True
    assert data["usd_return"] == approx(200 / 30 / (100 / 20) - 1)  # USDTRY 20 -> 30
    assert data["gold_return"] == approx((200 / 30 / 2000) / (100 / 20 / 1800) - 1)
    # Gold itself in TL: 1800 USD/oz x 20 -> 2000 x 30, and per gram (31.1035 g/oz).
    assert data["gold_return_in_currency"] == approx(2000 * 30 / (1800 * 20) - 1)
    assert data["beat_gold"] is True  # +100% against +66.7%
    assert data["gram_gold_try_start"] == round(1800 * 20 / 31.1034768, 2)
    assert data["gram_gold_try_end"] == round(2000 * 30 / 31.1034768, 2)
    # Measuring the holding in gold and measuring gold in TL are the same comparison.
    assert (1 + data["nominal_return"]) / (1 + data["gold_return_in_currency"]) - 1 == approx(
        data["gold_return"]
    )
    assert data["inflation_region"] == "TR"  # defaulted from the TRY price currency

    datasets = {p.dataset for p in result.provenance}
    assert "monthly_cpi:TEST.CPI" in datasets
    assert {s for p in result.provenance for s in p.symbols} >= {"TTT", "USDTRY", "GOLD", "TR"}


def test_unpublished_months_truncate_the_real_window(provider: FixtureProvider) -> None:
    result = _run(provider, _cpi({(2023, 1): 100.0, (2023, 6): 130.0, (2023, 12): 150.0}))
    data = result.data

    assert data["inflation_window_end"] == "2023-06-30"  # last bar inside the CPI coverage
    assert data["nominal_return_in_inflation_window"] == approx(0.5)
    assert data["real_return"] == approx(1.5 / 1.3 - 1)
    assert data["nominal_return"] == approx(1.0)  # the full window is still reported
    assert "inflation_window_truncated" in {f.code for f in result.quality_flags}


def test_missing_start_month_gives_no_real_return(provider: FixtureProvider) -> None:
    result = _run(provider, _cpi({(2023, 6): 130.0, (2024, 1): 160.0}))
    assert result.data["real_return"] is None
    assert result.data["real_return_positive"] is None
    assert "inflation_unavailable" in {f.code for f in result.quality_flags}


def test_region_currency_mismatch_is_flagged(provider: FixtureProvider) -> None:
    result = _run(provider, _cpi({(2023, 1): 100.0, (2024, 1): 104.0}, "US"), inflation_region="US")
    assert "currency_region_mismatch" in {f.code for f in result.quality_flags}


def test_missing_reference_series_degrades_to_null_not_failure(tmp_path: Path) -> None:
    (tmp_path / "bars").mkdir()
    (tmp_path / "assets.json").write_text(
        '[{"symbol": "TTT", "name": "T", "asset_class": "equity", "currency": "TRY",'
        ' "exchange": "X"}]'
    )
    (tmp_path / "bars" / "TTT.csv").write_text((FIXTURES / "bars" / "TTT.csv").read_text())
    result = _run(FixtureProvider(tmp_path), _cpi({(2023, 1): 100.0, (2024, 1): 160.0}))
    assert result.data["real_return"] == approx(0.25)
    assert result.data["usd_return"] is None and result.data["gold_return"] is None
    assert "usd_unavailable" in {f.code for f in result.quality_flags}


def test_unknown_currency_requires_an_explicit_region(tmp_path: Path) -> None:
    (tmp_path / "bars").mkdir()
    (tmp_path / "assets.json").write_text(
        '[{"symbol": "EEE", "name": "E", "asset_class": "equity", "currency": "EUR",'
        ' "exchange": "X"}]'
    )
    (tmp_path / "bars" / "EEE.csv").write_text(
        "date,open,high,low,close,volume\n2024-01-02,1,1,1,1,1\n2024-01-03,2,2,2,2,1\n"
    )
    with pytest.raises(ToolError) as raised:
        tools.compare_real_return(
            FixtureProvider(tmp_path),
            _cpi({(2024, 1): 1.0}),
            "EEE",
            "1m",
            today=dt.date(2024, 1, 10),
        )
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT
    assert "inflation_region" in raised.value.hint


def test_compare_assets_uses_one_common_window(provider: FixtureProvider) -> None:
    result = tools.compare_assets(
        provider, ["AAA", "TTT", "AAA"], start="2024-01-01", end="2024-01-10", today=TODAY
    )
    assert (result.data["window_start"], result.data["window_end"]) == ("2024-01-02", "2024-01-08")
    returns = {row["symbol"]: row["metrics"]["total_return"] for row in result.data["assets"]}
    assert returns == {"AAA": approx(0.2), "TTT": approx(0.1)}


def test_compare_assets_needs_at_least_two_symbols(provider: FixtureProvider) -> None:
    with pytest.raises(ToolError) as raised:
        tools.compare_assets(provider, ["AAA"], today=TODAY)
    assert raised.value.code is ErrorCode.INVALID_ARGUMENT


def test_check_data_quality_verdict(provider: FixtureProvider) -> None:
    result = tools.check_data_quality(
        provider, "BBB", start="2024-01-01", end="2024-01-26", today=TODAY
    )
    assert result.data["verdict"] == "unreliable"  # the +300% one-session move is critical
    assert result.data["flag_counts"]["critical"] == 1
    assert result.data["bars"] == 5 and result.data["usable_bars"] == 4


def _write(root: Path, assets: list[tuple[str, str]], bars: dict[str, str]) -> FixtureProvider:
    (root / "bars").mkdir(exist_ok=True)
    listing = [
        {"symbol": s, "name": s, "asset_class": "equity", "currency": c, "exchange": "X"}
        for s, c in assets
    ]
    (root / "assets.json").write_text(json.dumps(listing))
    for symbol, rows in bars.items():
        (root / "bars" / f"{symbol}.csv").write_text("date,open,high,low,close,volume\n" + rows)
    return FixtureProvider(root)


def test_window_within_one_month_gives_no_real_return(provider: FixtureProvider) -> None:
    # 2024-01-02 -> 2024-01-08: one CPI month only, so inflation cannot be measured.
    result = _run(
        provider, _cpi({(2023, 12): 100.0, (2024, 1): 103.0}), start="2024-01-02", end="2024-01-08"
    )
    assert result.data["real_return"] is None
    assert result.data["cumulative_inflation"] is None
    assert "inflation_window_too_short" in {f.code for f in result.quality_flags}


def test_hole_in_cpi_names_the_missing_end_month(provider: FixtureProvider) -> None:
    result = _run(provider, _cpi({(2023, 1): 100.0, (2023, 12): 150.0, (2024, 2): 170.0}))
    flag = next(f for f in result.quality_flags if f.code == "inflation_unavailable")
    assert flag.affected == ("2024-01",)


def test_compare_assets_uses_the_same_base_date_across_holiday_calendars(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        [("A", "TRY"), ("B", "TRY")],
        {
            "A": "2024-01-02,10,10,10,10,1\n2024-01-04,11,11,11,11,1\n2024-01-05,12,12,12,12,1\n",
            "B": "2024-01-03,20,20,20,20,1\n2024-01-04,21,21,21,21,1\n2024-01-05,22,22,22,22,1\n",
        },
    )
    result = tools.compare_assets(p, ["A", "B"], start="2024-01-01", end="2024-01-05", today=TODAY)
    metrics = {row["symbol"]: row["metrics"] for row in result.data["assets"]}
    assert result.data["window_start"] == "2024-01-03"
    # A has no 01-03 bar: its base is its 01-02 close (as of the common start), not 01-04.
    assert metrics["A"]["first_close"] == 10.0
    assert metrics["A"]["total_return"] == approx(0.2)
    assert metrics["B"]["total_return"] == approx(0.1)


def test_compare_assets_refuses_non_overlapping_histories(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        [("A", "TRY"), ("B", "TRY")],
        {
            "A": "2023-01-02,1,1,1,1,1\n2023-01-03,1,1,1,1,1\n",
            "B": "2024-01-02,1,1,1,1,1\n2024-01-03,1,1,1,1,1\n",
        },
    )
    with pytest.raises(ToolError) as raised:
        tools.compare_assets(p, ["A", "B"], period="max", today=TODAY)
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE


def test_reference_in_the_wrong_currency_is_not_used(tmp_path: Path) -> None:
    ttt = (FIXTURES / "bars" / "TTT.csv").read_text().split("\n", 1)[1]
    p = _write(
        tmp_path,
        [("TTT", "TRY"), ("USDTRY", "EUR")],
        {"TTT": ttt, "USDTRY": "2022-12-30,20,20,20,20,\n2024-01-02,30,30,30,30,\n"},
    )
    result = _run(p, _cpi({(2023, 1): 100.0, (2024, 1): 160.0}))
    assert result.data["usd_return"] is None
    assert "usd_unavailable" in {f.code for f in result.quality_flags}


def test_compare_assets_measures_mixed_currencies_in_one(tmp_path: Path) -> None:
    """A share in lira and one in dollars are not the same measure: Haiku named gold (USD)
    the winner over KCHOL (TRY) from their own-currency returns. They are converted to one
    currency (TRY by default) and ranked there. USDTRY 30 -> 33."""
    p = _write(
        tmp_path,
        [("TRS", "TRY"), ("USS", "USD"), ("USDTRY", "TRY")],
        {
            "TRS": "2024-01-02,100,100,100,100,1\n2024-01-08,120,120,120,120,1\n",
            "USS": "2024-01-02,10,10,10,10,1\n2024-01-08,11,11,11,11,1\n",
            "USDTRY": "2024-01-02,30,30,30,30,1\n2024-01-08,33,33,33,33,1\n",
        },
    )
    result = tools.compare_assets(p, ["TRS", "USS"], start="2024-01-02", today=TODAY)
    rows = {r["symbol"]: r for r in result.data["assets"]}
    assert result.data["common_currency"] == "TRY"
    # USS +10% in dollars, the dollar +10% in lira: +21% in lira, ahead of TRS's +20%.
    assert rows["USS"]["return_in_common_currency"] == approx(0.21)
    assert rows["TRS"]["return_in_common_currency"] == approx(0.2)
    assert "Toplam getiriye göre sıralama (TL cinsinden): USS +%21,0, TRS +%20,0." in result.facts
    assert any("USS TL cinsinden +%21,0" in f for f in result.facts)

    in_usd = tools.compare_assets(
        p, ["TRS", "USS"], start="2024-01-02", today=TODAY, currency="USD"
    )
    rows = {r["symbol"]: r for r in in_usd.data["assets"]}
    assert rows["TRS"]["return_in_common_currency"] == approx(1.2 / 1.1 - 1)


def test_compare_assets_does_not_rank_currencies_it_cannot_convert(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        [("TRS", "TRY"), ("USS", "USD")],
        {
            "TRS": "2024-01-02,100,100,100,100,1\n2024-01-08,120,120,120,120,1\n",
            "USS": "2024-01-02,10,10,10,10,1\n2024-01-08,11,11,11,11,1\n",
        },
    )
    result = tools.compare_assets(p, ["TRS", "USS"], start="2024-01-02", today=TODAY)
    assert result.data["common_currency"] is None
    assert not any(f.startswith("Toplam getiriye göre sıralama") for f in result.facts)
    assert any("sıralama yapılmadı" in f for f in result.facts)
    assert "mixed_currencies" in {f.code for f in result.quality_flags}
