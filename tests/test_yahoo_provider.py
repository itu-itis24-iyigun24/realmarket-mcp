from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.models import AssetClass
from realmarket_mcp.providers.yahoo import RateLimited, RawHistory, SymbolNotFound, YahooProvider

D = dt.date


class FakeBackend:
    def __init__(self, *, history: RawHistory | None = None, error: Exception | None = None):
        self._history = history
        self._error = error

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        if self._error:
            raise self._error
        return [
            {
                "symbol": "THYAO.IS",
                "longname": "Turk Hava Yollari",
                "quoteType": "EQUITY",
                "exchDisp": "Istanbul",
            },
            {"shortname": "no symbol, skipped"},
            {"symbol": "XU100.IS", "shortname": "BIST 100", "quoteType": "INDEX"},
        ]

    def history(self, symbol: str, start: dt.date, end_inclusive: dt.date) -> RawHistory:
        if self._error:
            raise self._error
        assert self._history is not None
        return self._history


def _provider(**kwargs: Any) -> YahooProvider:
    return YahooProvider(FakeBackend(**kwargs), retrieved_at="2024-02-01T00:00:00Z")


def test_search_maps_quotes_to_assets() -> None:
    assets = _provider().search("thy", 10)
    assert [a.symbol for a in assets] == ["THYAO.IS", "XU100.IS"]
    assert assets[0].asset_class is AssetClass.EQUITY
    assert assets[0].exchange == "Istanbul"
    assert assets[1].asset_class is AssetClass.INDEX
    assert assets[0].currency is None


def test_history_is_clipped_sorted_and_deduplicated() -> None:
    rows = [
        (D(2024, 1, 3), 2.0, 2.0, 2.0, 2.0, 10.0),
        (D(2024, 1, 2), 1.0, 1.0, 1.0, 1.0, 10.0),
        (D(2024, 1, 3), 3.0, 3.0, 3.0, 3.0, 10.0),  # duplicate session: last row wins
        (D(2024, 1, 9), 9.0, 9.0, 9.0, 9.0, 10.0),  # outside the requested range
    ]
    series = _provider(history=RawHistory("TRY", rows)).daily_bars(
        "THYAO.IS", D(2024, 1, 1), D(2024, 1, 5)
    )
    assert [(b.date, b.close) for b in series.bars] == [(D(2024, 1, 2), 1.0), (D(2024, 1, 3), 3.0)]
    assert series.currency == "TRY"
    assert series.adjustment == "split_and_dividend"
    assert series.provider == "yahoo"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (SymbolNotFound("x"), ErrorCode.UNKNOWN_SYMBOL),
        (RateLimited("x"), ErrorCode.RATE_LIMITED),
        (ConnectionError("x"), ErrorCode.PROVIDER_UNAVAILABLE),
    ],
)
def test_backend_failures_become_contract_errors(error: Exception, code: ErrorCode) -> None:
    with pytest.raises(ToolError) as raised:
        _provider(error=error).daily_bars("THYAO.IS", D(2024, 1, 1), D(2024, 1, 5))
    assert raised.value.code is code
    assert raised.value.hint


def test_unknown_symbol_hint_explains_yahoo_symbol_formats() -> None:
    with pytest.raises(ToolError) as raised:
        _provider(error=SymbolNotFound("x")).daily_bars("THYAO", D(2024, 1, 1), D(2024, 1, 5))
    assert ".IS" in raised.value.hint


def test_yfinance_adapter_reads_session_dates_and_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    pd = pytest.importorskip("pandas")
    yfinance = pytest.importorskip("yfinance")
    from realmarket_mcp.providers.yahoo import YfinanceBackend

    calls: dict[str, Any] = {}

    class FakeTicker:
        def __init__(self, symbol: str) -> None:
            calls["symbol"] = symbol
            self.history_metadata = {"currency": "TRY"}

        def history(self, **kwargs: Any) -> Any:
            calls.update(kwargs)
            index = pd.DatetimeIndex(["2024-01-02 00:00", "2024-01-03 00:00"], tz="Europe/Istanbul")
            return pd.DataFrame(
                {
                    "Open": [1.0, 2.0],
                    "High": [1.0, 2.0],
                    "Low": [1.0, 2.0],
                    "Close": [1.0, float("nan")],
                    "Volume": [5, 6],
                },
                index=index,
            )

    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)
    raw = YfinanceBackend().history("THYAO.IS", D(2024, 1, 1), D(2024, 1, 3))

    assert calls["end"] == "2024-01-04"  # yfinance's end is exclusive
    assert calls["auto_adjust"] is True
    assert raw.currency == "TRY"
    assert [r[0] for r in raw.rows] == [D(2024, 1, 2), D(2024, 1, 3)]
    assert raw.rows[1][4] is None  # NaN close becomes None, never NaN


def test_bars_from_the_retrieval_day_are_excluded_as_possibly_incomplete() -> None:
    rows = [
        (D(2024, 1, 31), 1.0, 1.0, 1.0, 1.0, 10.0),
        (D(2024, 2, 1), 2.0, 2.0, 2.0, 2.0, 10.0),  # retrieval day: session may be open
    ]
    series = _provider(history=RawHistory("TRY", rows)).daily_bars(
        "THYAO.IS", D(2024, 1, 1), D(2024, 2, 1)
    )
    assert [b.date for b in series.bars] == [D(2024, 1, 31)]
