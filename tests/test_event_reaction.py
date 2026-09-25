from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from realmarket_mcp import tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.providers.fixture import FixtureProvider

TODAY = dt.date(2024, 3, 20)
HEADER = "date,open,high,low,close,volume\n"
# Event on Sunday 2024-03-10: base is the Friday 03-08 close, session 1 is Monday 03-11.
ASSET = {
    "2024-03-01": 100,
    "2024-03-04": 95,
    "2024-03-05": 96,
    "2024-03-06": 97,
    "2024-03-07": 98,
    "2024-03-08": 100,
    "2024-03-11": 110,
    "2024-03-12": 105,
    "2024-03-13": 108,
    "2024-03-14": 112,
    "2024-03-15": 120,
}
INDEX = {
    "2024-03-01": 1000,
    "2024-03-04": 1000,
    "2024-03-05": 1000,
    "2024-03-06": 1000,
    "2024-03-07": 1000,
    "2024-03-08": 1000,
    "2024-03-11": 1010,
    "2024-03-12": 1000,
    "2024-03-13": 1020,
    "2024-03-14": 1030,
    "2024-03-15": 1050,
}


def approx(value: float) -> object:
    return pytest.approx(value, abs=1e-6)


def _csv(rows: dict[str, int]) -> str:
    return HEADER + "".join(f"{d},{c},{c},{c},{c},1000\n" for d, c in rows.items())


@pytest.fixture
def provider(tmp_path: Path) -> FixtureProvider:
    (tmp_path / "bars").mkdir()
    listing = [
        {"symbol": s, "name": s, "asset_class": c, "currency": "TRY", "exchange": "X"}
        for s, c in (("EVT", "equity"), ("IDX", "index"), ("SOLO", "equity"))
    ]
    (tmp_path / "assets.json").write_text(json.dumps(listing))
    (tmp_path / "bars" / "EVT.csv").write_text(_csv(ASSET))
    (tmp_path / "bars" / "IDX.csv").write_text(_csv(INDEX))
    (tmp_path / "bars" / "SOLO.csv").write_text(_csv(ASSET))
    return FixtureProvider(tmp_path)


def test_reaction_windows_and_excess_returns(provider: FixtureProvider) -> None:
    result = tools.get_event_reaction(provider, "EVT", "2024-03-10", today=TODAY)
    data = result.data
    assert data["base_date"] == "2024-03-08" and data["benchmark"] == "IDX"
    one, five, twenty = data["reaction"]

    assert one["date"] == "2024-03-11"
    assert one["return"] == approx(0.10)
    assert one["benchmark_return"] == approx(0.01)
    assert one["excess_return"] == approx(1.10 / 1.01 - 1)

    assert five["date"] == "2024-03-15"
    assert five["return"] == approx(0.20)
    assert five["excess_return"] == approx(1.20 / 1.05 - 1)

    assert twenty["return"] is None  # not enough sessions yet
    assert "window_incomplete" in {f.code for f in result.quality_flags}


def test_event_on_a_trading_day_counts_that_day_as_session_one(provider: FixtureProvider) -> None:
    result = tools.get_event_reaction(provider, "EVT", "2024-03-12", windows=[1], today=TODAY)
    assert result.data["base_date"] == "2024-03-11"
    assert result.data["reaction"][0]["return"] == approx(105 / 110 - 1)


def test_pre_event_drift_covers_the_five_sessions_before(provider: FixtureProvider) -> None:
    drift = tools.get_event_reaction(provider, "EVT", "2024-03-10", today=TODAY).data[
        "pre_event_drift"
    ]
    assert drift["from"] == "2024-03-01"
    assert drift["return"] == approx(0.0)  # 100 -> 100


def test_explicit_benchmark_overrides_the_default(provider: FixtureProvider) -> None:
    result = tools.get_event_reaction(
        provider, "EVT", "2024-03-10", benchmark="SOLO", windows=[1], today=TODAY
    )
    assert result.data["benchmark"] == "SOLO"
    assert result.data["reaction"][0]["excess_return"] == approx(0.0)


def test_missing_benchmark_degrades_to_absolute_returns(provider: FixtureProvider) -> None:
    result = tools.get_event_reaction(
        provider, "EVT", "2024-03-10", benchmark="NOPE", windows=[1], today=TODAY
    )
    assert result.data["benchmark"] is None
    assert result.data["reaction"][0]["return"] == approx(0.10)
    assert result.data["reaction"][0]["excess_return"] is None
    assert "benchmark_unavailable" in {f.code for f in result.quality_flags}


@pytest.mark.parametrize(
    ("event", "windows", "code"),
    [
        ("2024-04-01", [1], ErrorCode.INVALID_ARGUMENT),  # after today
        ("10/03/2024", [1], ErrorCode.INVALID_ARGUMENT),  # not ISO
        ("2024-03-10", [0, 500], ErrorCode.INVALID_ARGUMENT),  # no valid window
        ("2024-03-01", [1], ErrorCode.NO_DATA_IN_RANGE),  # no close before the event
    ],
)
def test_invalid_requests(
    provider: FixtureProvider, event: str, windows: list[int], code: ErrorCode
) -> None:
    with pytest.raises(ToolError) as raised:
        tools.get_event_reaction(provider, "EVT", event, windows=windows, today=TODAY)
    assert raised.value.code is code
