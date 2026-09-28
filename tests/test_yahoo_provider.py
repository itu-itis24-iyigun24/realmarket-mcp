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
            index = pd.DatetimeIndex(
                ["2024-01-02 00:00", "2024-01-03 00:00", "2024-01-04 00:00"], tz="Europe/Istanbul"
            )
            return pd.DataFrame(
                {
                    "Open": [10.0, 9.5, 2.0],
                    "High": [12.0, 9.5, 2.0],
                    "Low": [8.0, 9.5, 2.0],
                    "Close": [10.0, 9.5, float("nan")],
                    "Adj Close": [1.0, 1.0, 1.0],  # ignored: computed from the dividends
                    "Volume": [5, 6, 7],
                    "Dividends": [0.0, 0.5, 0.0],
                },
                index=index,
            )

    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)
    raw = YfinanceBackend().history("THYAO.IS", D(2024, 1, 1), D(2024, 1, 3))

    assert calls["end"] == "2024-01-04"  # yfinance's end is exclusive
    assert calls["auto_adjust"] is False and calls["actions"] is True
    assert raw.currency == "TRY"
    assert [r[0] for r in raw.rows] == [D(2024, 1, 2), D(2024, 1, 3), D(2024, 1, 4)]
    # The 0.5 dividend on 2024-01-03 scales earlier prices by 1 - 0.5 / 10 = 0.95.
    assert raw.rows[0][1:5] == pytest.approx((9.5, 11.4, 7.6, 9.5))
    assert raw.rows[1][4] == 9.5  # the ex-date itself is not adjusted
    assert raw.rows[2][4] is None  # NaN close becomes None, never NaN
    assert raw.price_closes == {D(2024, 1, 2): 10.0, D(2024, 1, 3): 9.5, D(2024, 1, 4): None}
    assert list(raw.dividends) == [(D(2024, 1, 3), 0.5)]


def test_bars_from_the_retrieval_day_are_excluded_as_possibly_incomplete() -> None:
    rows = [
        (D(2024, 1, 31), 1.0, 1.0, 1.0, 1.0, 10.0),
        (D(2024, 2, 1), 2.0, 2.0, 2.0, 2.0, 10.0),  # retrieval day: session may be open
    ]
    series = _provider(history=RawHistory("TRY", rows)).daily_bars(
        "THYAO.IS", D(2024, 1, 1), D(2024, 2, 1)
    )
    assert [b.date for b in series.bars] == [D(2024, 1, 31)]


def test_statement_frames_are_merged_by_period_with_row_fallbacks() -> None:
    pd = pytest.importorskip("pandas")
    from realmarket_mcp.providers.yahoo import _frame_rows

    ends = [pd.Timestamp("2026-06-30"), pd.Timestamp("2026-03-31")]
    income = pd.DataFrame(
        {ends[0]: [100.0, float("nan")], ends[1]: [90.0, 5.0]},
        index=["Total Revenue", "Net Income"],
    )
    balance = pd.DataFrame({ends[0]: [1000.0]}, index=["Total Assets"])
    rows = dict(_frame_rows(income, balance))
    assert list(rows) == [D(2026, 3, 31), D(2026, 6, 30)]
    assert rows[D(2026, 6, 30)]["revenue"] == 100.0
    assert rows[D(2026, 6, 30)]["net_income"] is None  # NaN never leaks
    assert rows[D(2026, 6, 30)]["total_assets"] == 1000.0
    assert rows[D(2026, 3, 31)]["net_income"] == 5.0


def test_pence_quotes_become_pounds() -> None:
    rows = [(D(2024, 1, 2), 250.0, 260.0, 240.0, 255.0, 1000.0)]
    series = _provider(history=RawHistory("GBp", rows)).daily_bars(
        "SHEL.L", D(2024, 1, 1), D(2024, 1, 5)
    )
    assert series.currency == "GBP"
    bar = series.bars[0]
    assert (bar.open, bar.close, bar.volume) == (2.5, 2.55, 1000.0)  # volume is not a price


def test_price_summary_splits_the_return_into_price_and_dividends() -> None:
    from realmarket_mcp import tools

    # A 10 TL dividend on 2024-01-04: the adjusted closes scale the earlier prices by 0.9.
    rows = [
        (D(2024, 1, 2), 90.0, 90.0, 90.0, 90.0, 1.0),
        (D(2024, 1, 3), 99.0, 99.0, 99.0, 99.0, 1.0),
        (D(2024, 1, 4), 100.0, 100.0, 100.0, 100.0, 1.0),
    ]
    raw = RawHistory(
        "TRY",
        rows,
        {D(2024, 1, 2): 100.0, D(2024, 1, 3): 110.0, D(2024, 1, 4): 100.0},
        [(D(2024, 1, 4), 10.0)],
    )
    provider = _provider(history=raw)
    data = tools.get_price_summary(
        provider, "TUPRS.IS", start="2024-01-01", end="2024-01-05", today=D(2024, 2, 1)
    ).data
    assert data["total_return"] == pytest.approx(100 / 90 - 1, abs=1e-6)
    assert data["price_return"] == 0.0  # 100 -> 100 in price alone
    assert (data["first_close"], data["first_price"], data["last_price"]) == (90.0, 100.0, 100.0)
    assert data["dividend_return"] == pytest.approx(100 / 90 - 1, abs=1e-6)
    assert (data["dividends_per_share"], data["dividend_payments"]) == (10.0, 1)
    assert data["dividend_yield_trailing_12m"] == 0.1  # 10 TL over the last price of 100
    series = provider.daily_bars("TUPRS.IS", D(2024, 1, 1), D(2024, 1, 5))
    assert series.dividends == ((D(2024, 1, 4), 10.0),)


def test_dividend_adjustment_is_computed_not_taken_from_yahoo() -> None:
    from realmarket_mcp.providers.yahoo import _dividend_factors

    # BP.L-like, in pence: a 8.32p dividend on a 568p close scales earlier prices by 0.98535.
    # Yahoo's own Adj Close treated it as pounds (factor 0.99985), losing the dividend.
    factors = _dividend_factors([570.0, 568.0, 560.0, 565.0], [0.0, 0.0, 8.32, 0.0])
    assert factors == pytest.approx([1 - 8.32 / 568, 1 - 8.32 / 568, 1.0, 1.0])
    assert _dividend_factors([None, 100.0], [0.0, 5.0]) == [1.0, 1.0]  # no previous close


class PeersBackend(FakeBackend):
    def __init__(self, raw: Any) -> None:
        super().__init__()
        self._raw = raw

    def peers(self, symbol: str, level: str = "industry") -> Any:
        return self._raw


def test_industry_peers_map_screener_rows() -> None:
    from realmarket_mcp.providers.yahoo import RawPeers

    raw = RawPeers(
        "Steel",
        "tr",
        [
            {"symbol": "EREGL.IS", "shortName": "EREGLI", "priceToBook": 0.79, "marketCap": 9.0},
            {"symbol": "KRDMD.IS", "shortName": "KARDEMIR (D)", "priceToBook": float("nan")},
            {"shortName": "no symbol, skipped"},
        ],
    )
    group = YahooProvider(PeersBackend(raw), retrieved_at="2024-02-01T00:00:00Z").industry_peers(
        "EREGL.IS"
    )
    assert (group.industry, group.market) == ("Steel", "tr")
    assert [(p.symbol, p.price_to_book, p.market_cap) for p in group.peers] == [
        ("EREGL.IS", 0.79, 9.0),
        ("KRDMD.IS", None, None),
    ]
    assert group.data_version.startswith("sha256:")


def test_industry_peers_need_an_industry() -> None:
    from realmarket_mcp.providers.yahoo import RawPeers

    yahoo = YahooProvider(PeersBackend(RawPeers(None, None, ())), retrieved_at="2024-02-01T00:00Z")
    with pytest.raises(ToolError) as info:
        yahoo.industry_peers("FUND")
    assert info.value.code is ErrorCode.NO_DATA_IN_RANGE


def test_gold_ticker_is_refused_as_it_is_a_mining_share() -> None:
    with pytest.raises(ToolError) as info:
        _provider().daily_bars("GOLD", D(2024, 1, 2), D(2024, 1, 9))
    assert info.value.code is ErrorCode.INVALID_ARGUMENT
    assert "GC=F" in info.value.hint
