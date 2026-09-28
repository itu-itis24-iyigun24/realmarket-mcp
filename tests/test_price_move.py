"""explain_price_move against synthetic prices whose market sensitivity is known."""

from __future__ import annotations

import datetime as dt

import pytest

from realmarket_mcp import tools
from realmarket_mcp.contract import ErrorCode, Severity, ToolError
from realmarket_mcp.models import AssetClass, AssetRef, Bar, NewsItem, PriceSeries

DAYS = [dt.date(2026, 6, 1) + dt.timedelta(days=i) for i in range(70)]
INDEX_RETURNS = [0.01 * ((i * 7) % 5 - 2) / 2 for i in range(69)]  # a repeating pattern
INDEX_RETURNS[-1] = -0.02  # the last session: the market falls 2%
BETA = 1.5
STOCK_RETURNS = [BETA * r for r in INDEX_RETURNS]
STOCK_RETURNS[-1] = BETA * -0.02 - 0.01  # 1 point worse than the market explains


def _path(returns: list[float], start: float) -> list[float]:
    closes = [start]
    for r in returns:
        closes.append(closes[-1] * (1 + r))
    return closes


class Provider:
    name = "synthetic"
    gold_usd_symbol = "GOLD"

    def fx_symbol(self, base: str, quote: str) -> str:
        return base + quote

    def default_benchmark(self, symbol: str) -> str | None:
        return "IDX" if symbol == "STK" else None

    def search(self, query: str, limit: int) -> list[AssetRef]:
        return [AssetRef("STK", "Stock Company A.Ş.", AssetClass.EQUITY, "TRY", "TEST")]

    def daily_bars(self, symbol: str, start: dt.date, end: dt.date) -> PriceSeries:
        closes = _path(STOCK_RETURNS if symbol == "STK" else INDEX_RETURNS, 100.0)
        volumes = [1000.0] * 69 + [3000.0]
        bars = tuple(Bar(d, c, c, c, c, v) for d, c, v in zip(DAYS, closes, volumes, strict=True))
        return PriceSeries(symbol, "TRY", self.name, "none", "t", bars).between(start, end)


class News:
    name = "news"

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query, start, end, *, language, limit):  # type: ignore[no-untyped-def]
        self.queries.append(query)
        return [
            NewsItem(
                "2026-08-09T08:00:00Z",
                "Stock Company guidance cut",
                "https://x.y/1",
                "x.y",
                "en",
                None,
            )
        ]


def test_the_move_is_described_next_to_the_market_without_attribution() -> None:
    news = News()
    result = tools.explain_price_move(
        Provider(), "STK", today=DAYS[-1], load_news=lambda: news, retrieved_at="t"
    )
    data = result.data
    assert data["session"] == DAYS[-1].isoformat()
    assert data["move"] == pytest.approx(-0.04, abs=1e-6)
    assert data["benchmark"]["move"] == pytest.approx(-0.02, abs=1e-6)
    assert data["difference_from_benchmark"] == pytest.approx(-0.02, abs=1e-6)
    # Facts side by side only: no beta, no market or company share of the move.
    assert not {"market_part", "stock_specific_part"} & set(data)
    assert "beta" not in data["benchmark"]
    assert data["volume_ratio"] == pytest.approx(3.0)
    assert data["move_in_sigmas"] < -1
    assert data["news"][0]["title"] == "Stock Company guidance cut"
    assert news.queries == ["Stock Company"]  # legal suffix removed from the listed name
    assert any("do not apportion" in n.lower() for n in result.notes)
    assert data["cause"].startswith("Not determined")


def test_a_date_without_a_session_uses_the_one_before() -> None:
    later = DAYS[-1] + dt.timedelta(days=3)
    result = tools.explain_price_move(Provider(), "STK", None, today=later)
    assert result.data["session"] == DAYS[-1].isoformat()
    (flag,) = [f for f in result.quality_flags if f.code == "session_before_date"]
    # A warning the model must state: the latest session is not "today".
    assert flag.severity is Severity.WARNING
    assert "(today)" in flag.message and "do not call it today's move" in flag.message
    assert result.data["news"] == []  # no news source given
    assert "no_articles" not in {f.code for f in result.quality_flags}


def test_too_little_history_is_refused() -> None:
    with pytest.raises(ToolError) as raised:
        tools.explain_price_move(Provider(), "STK", DAYS[10].isoformat(), today=DAYS[-1])
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE


@pytest.mark.parametrize(
    ("listed", "query"),
    [
        ("Türk Hava Yollari Anonim Ortakligi", "Türk Hava Yollari"),
        ("TÜRK HAVA YOLLARI ANONİM ORTAKLIĞI", "TÜRK HAVA YOLLARI"),
        ("Türkiye Petrol Rafinerileri A.S.", "Türkiye Petrol Rafinerileri"),
        ("BİM Birleşik Mağazalar A.Ş.", "BİM Birleşik Mağazalar"),
        ("Apple Inc.", "Apple"),
        ("ASML Holding N.V.", "ASML Holding"),
    ],
)
def test_news_query_drops_the_legal_form(listed: str, query: str) -> None:
    assert tools._company_query(listed) == query
