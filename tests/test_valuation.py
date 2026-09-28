"""get_valuation: market value and price multiples, with currency and TMS 29 handling.

Fixture prices (tests/fixtures/basic): TTT (TRY) last closes 220 on 2024-01-08; USDTRY is 30
from 2024-01-02. Statements are written per test into a temporary fixture directory.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from realmarket_mcp import tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.inflation import CpiSeries
from realmarket_mcp.models import FinancialStatements, IndustryPeers, PeerMultiple
from realmarket_mcp.providers.fixture import FixtureProvider

FIXTURES = Path(__file__).parent / "fixtures" / "basic"
TODAY = dt.date(2024, 1, 10)
QUARTER_ENDS = ("2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31")


def approx(value: float) -> Any:
    return pytest.approx(value, abs=1e-6)


def _no_cpi(*_: object) -> CpiSeries:
    raise ToolError(ErrorCode.MISSING_API_KEY, "no CPI", "set one")


def provider(tmp_path: Path, statements: dict[str, Any]) -> FixtureProvider:
    root = tmp_path / "fx"
    shutil.copytree(FIXTURES, root)
    (root / "financials").mkdir(exist_ok=True)
    (root / "financials" / "TTT.json").write_text(json.dumps(statements))
    return FixtureProvider(root)


def quarters(net: tuple[float, ...], revenue: float = 250.0, **last: float) -> list[dict[str, Any]]:
    rows = [
        {"end": e, "values": {"net_income": n, "revenue": revenue}}
        for e, n in zip(QUARTER_ENDS, net, strict=True)
    ]
    rows[-1]["values"].update(last)
    return rows


def run(p: FixtureProvider, cpi: tools.CpiLoader = _no_cpi, **kwargs: Any) -> tools.ToolResult:
    return tools.get_valuation(p, p, cpi, "TTT", today=TODAY, **kwargs)


def test_multiples_from_four_quarters(tmp_path: Path) -> None:
    st = {"currency": "USD", "industry": "Textiles", "shares_outstanding": 1000,
          "quarterly": quarters((10, 20, 30, 40), total_equity=2000)}  # fmt: skip
    data = run(provider(tmp_path, st)).data
    # Market value 220 TRY x 1000 = 220,000 TRY; statements in USD at 30 TRY per USD.
    assert data["market_cap"] == 220_000
    assert data["fx_to_trading_currency"] == approx(30.0)
    assert data["price_to_earnings"] == approx(220_000 / (100 * 30))
    assert data["price_to_book"] == approx(220_000 / (2000 * 30))
    assert data["price_to_sales"] == approx(220_000 / (1000 * 30))
    assert data["earnings_basis"] == "trailing_four_quarters"
    facts = run(provider(tmp_path / "f", st)).facts
    assert "F/K 73,33: piyasa değeri, net kârın (100,00 USD) 73,33 katı." in facts
    assert any(f.startswith("PD/DD 3,67: piyasa değeri, özsermayenin (2.000,00 USD") for f in facts)
    assert "F/S 7,33: piyasa değeri, satışların (1.000,00 USD) 7,33 katı." in facts
    above = "PD/DD 1'in üstünde: piyasa değeri özsermayeden yüksek."
    assert any(f.startswith(above) for f in facts)
    assert any("bu hisse için böyle bir kıyas bu araçlarda yok" in f for f in facts)
    assert any("30,0000 kuruyla TRY cinsine" in f for f in facts)


def test_tms29_uses_the_reported_trailing_twelve_months(tmp_path: Path) -> None:
    year = {"end": "2023-12-31", "values": {"net_income": 40, "revenue": 900}}
    st = {"currency": "TRY", "industry": "Retail", "shares_outstanding": 1000,
          "quarterly": quarters((10, 10, 10, 10), total_equity=5000), "annual": [year],
          "ttm": {"end": "2023-12-31", "values": {"net_income": 50, "revenue": 1000}}}  # fmt: skip
    cpi = CpiSeries("TR", "t", "C", "t", {(2023, 12): 100.0, (2024, 1): 110.0})
    data = run(provider(tmp_path, st), lambda *_: cpi).data
    # The source's trailing figure, never a sum of its quarters; brought to January 2024 money.
    assert data["earnings_basis"] == "trailing_twelve_months_reported"
    assert data["restated_to_money_of"] == "2024-01"
    assert any(
        "TMS 29) göre Ocak 2024 parasıyla" in f
        for f in run(provider(tmp_path / "f", st), lambda *_: cpi).facts
    )
    assert data["earnings"] == approx(55.0)
    assert data["price_to_earnings"] == approx(220_000 / 55)
    assert data["price_to_sales"] == approx(220_000 / 1100)
    assert data["price_to_book"] == approx(220_000 / 5500)
    old = CpiSeries("TR", "t", "C", "t", {(2023, 6): 90.0, (2023, 9): 100.0})
    late = run(provider(tmp_path / "b", st), lambda *_: old)
    assert "cpi_behind_price" in {f.code for f in late.quality_flags}


def test_tms29_without_a_reported_trailing_figure_gives_no_pe(tmp_path: Path) -> None:
    year = {"end": "2023-12-31", "values": {"net_income": 40, "revenue": 900}}
    st = {"currency": "TRY", "industry": "Retail", "shares_outstanding": 1000,
          "quarterly": quarters((10, 10, 10, 10), total_equity=5000), "annual": [year]}  # fmt: skip
    cpi = CpiSeries("TR", "t", "C", "t", {(2023, 12): 100.0, (2024, 1): 110.0})
    result = run(provider(tmp_path, st), lambda *_: cpi)
    data = result.data
    assert (data["price_to_earnings"], data["price_to_sales"], data["earnings_basis"]) == (
        None,
        None,
        None,
    )
    assert "TMS 29" in data["not_meaningful"]["pe"]
    assert "F/K bu veriyle hesaplanamıyor: kaynak gereken rakamı vermiyor." in result.facts
    assert data["price_to_book"] == approx(220_000 / 5500)  # P/B is still given
    assert "no_tms29_trailing_earnings" in {f.code for f in result.quality_flags}
    no_cpi = run(provider(tmp_path / "b", st))
    assert "inflation_unavailable" in {f.code for f in no_cpi.quality_flags}
    assert no_cpi.data["price_to_book"] == approx(220_000 / 5000)


def test_losses_and_missing_quarters(tmp_path: Path) -> None:
    gap = quarters((10, 20, 30, 40))
    del gap[1]  # a missing quarter: fall back to the fiscal year
    year = {"end": "2023-12-31", "values": {"net_income": -5, "revenue": 900}}
    st = {"currency": "TRY", "industry": "Banks", "shares_outstanding": 1000, "quarterly": gap,
          "annual": [year]}  # fmt: skip
    data = run(provider(tmp_path, st)).data
    assert data["earnings_basis"] == "latest_fiscal_year"
    assert data["price_to_earnings"] is None
    assert "not meaningful" in data["not_meaningful"]["pe"]
    assert data["price_to_sales"] == approx(220_000 / 900)


def _shares_from(count: float | None, as_of: dt.date | None = None) -> tools.SharesLookup:
    def lookup(quote: str) -> FinancialStatements:
        return FinancialStatements(quote, "TRY", None, None, "other-feed", "2024-01-10T00:00:00Z",
                                   (), (), shares_outstanding=count, shares_source="other feed",
                                   shares_as_of=as_of)  # fmt: skip

    return lookup


def test_share_count_sources(tmp_path: Path) -> None:
    st = {"currency": "TRY", "industry": "Banks", "quarterly": quarters((1, 1, 1, 1))}
    p = provider(tmp_path, st)
    with pytest.raises(ToolError) as raised:
        run(p)
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE
    result = run(p, shares_lookup=_shares_from(500.0, dt.date(2024, 1, 5)))
    assert result.data["market_cap"] == 110_000
    assert result.data["shares_as_of"] == "2024-01-05"
    assert "shares_from_other_source" in {f.code for f in result.quality_flags}
    shares_prov = [pv for pv in result.provenance if pv.dataset == "shares_outstanding"]
    assert [(pv.provider, pv.period_end) for pv in shares_prov] == [("other-feed", "2024-01-05")]


def test_share_counts_are_cross_checked(tmp_path: Path) -> None:
    st = {"currency": "TRY", "industry": "Banks", "shares_outstanding": 1000,
          "quarterly": quarters((1, 1, 1, 1))}  # fmt: skip
    p = provider(tmp_path, st)
    close = run(p, shares_lookup=_shares_from(1030.0))
    assert "shares_mismatch" not in {f.code for f in close.quality_flags}
    far = run(p, shares_lookup=_shares_from(8000.0))  # e.g. an ADR ratio, or an old count
    assert "shares_mismatch" in {f.code for f in far.quality_flags}
    assert far.data["market_cap"] == 220_000  # the statements' own count is used


def test_one_quarter_window_and_stale_price(tmp_path: Path) -> None:
    rows = quarters((10, 20, 30, 40))
    del rows[-1]["values"]["revenue"]  # latest quarter has earnings but no sales
    st = {"currency": "USD", "industry": "Banks", "shares_outstanding": 1000, "quarterly": rows}
    p = provider(tmp_path, st)
    data = run(p).data
    assert data["periods_used"] == list(QUARTER_ENDS)
    assert data["sales"] is None and "sales" in data["not_meaningful"]["ps"]
    late = tools.get_valuation(p, p, _no_cpi, "TTT", today=dt.date(2024, 1, 20))
    assert "stale_price" in {f.code for f in late.quality_flags}


def test_missing_quarter_falls_back_to_the_fiscal_year_with_a_flag(tmp_path: Path) -> None:
    rows = quarters((10, 20, 30, 40))
    del rows[1]
    year = {"end": "2023-12-31", "values": {"net_income": 50, "revenue": 900}}
    st = {"currency": "USD", "industry": "Retail", "shares_outstanding": 1000,
          "quarterly": rows, "annual": [year]}  # fmt: skip
    result = run(provider(tmp_path, st))
    assert "fiscal_year_basis" in {f.code for f in result.quality_flags}
    assert result.data["earnings_basis"] == "latest_fiscal_year"


def test_stale_statements_and_lei_symbols(tmp_path: Path) -> None:
    year = {"end": "2022-12-31", "values": {"net_income": 5, "revenue": 50}}
    st = {"currency": "TRY", "industry": "Banks", "shares_outstanding": 10, "annual": [year]}
    result = run(provider(tmp_path, st))
    assert "stale_statements" in {f.code for f in result.quality_flags}
    with pytest.raises(ToolError) as raised:
        tools.get_valuation(
            FixtureProvider(FIXTURES), FixtureProvider(FIXTURES), _no_cpi,
            "724500Y6DUVHQD6OXN27", today=TODAY,
        )  # fmt: skip
    assert "price_symbol" in raised.value.hint


class PeersProvider(FixtureProvider):
    """The fixture prices plus an industry list, as a source with a screener gives it."""

    def __init__(
        self,
        root: Path,
        peers: list[tuple[str, str, float | None, float]],
        sector: list[tuple[str, str, float | None, float]] | None = None,
    ) -> None:
        super().__init__(root)
        self._peers, self._sector = peers, sector

    def industry_peers(self, symbol: str, *, broader: bool = False) -> IndustryPeers:
        if broader and self._sector is None:
            raise ToolError(ErrorCode.NO_DATA_IN_RANGE, "no sector", "none")
        return IndustryPeers(
            symbol=symbol,
            industry="Steel",
            group="Basic Materials" if broader else "Steel",
            level="sector" if broader else "industry",
            market="tr",
            provider="fixture",
            retrieved_at="2024-01-10T00:00:00Z",
            definition="fixture price-to-book",
            peers=tuple(
                PeerMultiple(s, n, pb, cap)
                for s, n, pb, cap in (self._sector if broader and self._sector else self._peers)
            ),
        )


STATEMENTS = {"currency": "TRY", "industry": "Steel", "shares_outstanding": 1000,
              "quarterly": quarters((10, 20, 30, 40), total_equity=200_000)}  # fmt: skip
# Market value 220 x 1000 = 220,000 over equity 200,000: P/B 1.1, as the peer lists give it.


def _peers_provider(
    tmp_path: Path,
    peers: list[tuple[str, str, float | None, float]],
    sector: list[tuple[str, str, float | None, float]] | None = None,
) -> Any:
    root = provider(tmp_path, STATEMENTS)._root
    return PeersProvider(root, peers, sector)


def test_price_to_book_is_ranked_within_its_industry(tmp_path: Path) -> None:
    peers = [
        ("TTT", "TTT CELIK", 1.1, 50.0),
        ("AAA", "AAA", 0.5, 1.0),
        ("BBB", "BBB", 0.9, 1.0),
        ("CCC", "CCC", 1.5, 1.0),
        ("DDD", "DDD", 2.0, 1.0),
        ("KRDMA", "KARDEMIR (A)", 0.4, 1.0),  # one company in three share classes counts once,
        ("KRDMB", "KARDEMIR (B)", 0.8, 3.0),  # by its largest class
        ("KRDMD", "KARDEMIR (D)", 0.6, 2.0),
        ("EEE", "EEE", None, 1.0),  # no ratio: left out
        ("FFF", "FFF", -0.3, 1.0),  # negative book value: left out
    ]
    p = _peers_provider(tmp_path, peers)
    result = tools.get_valuation(p, p, _no_cpi, "TTT", today=TODAY)
    comparison = result.data["industry_comparison"]
    # Others: 0.5, 0.8 (Kardemir), 0.9, 1.5, 2.0; the company itself is not its own peer.
    assert comparison["peer_symbols"] == ["AAA", "BBB", "CCC", "DDD", "KRDMB"]
    assert comparison["peer_median_price_to_book"] == approx(0.9)
    assert (comparison["peers_lower"], comparison["peers_higher"]) == (3, 2)
    assert comparison["price_to_book"] == approx(1.1)
    fact = next(f for f in result.facts if f.startswith("Sektör kıyası ("))
    assert (
        "TTT 1,10; sektörde TTT dışındaki 5 şirketin ortancası (sıralamada ortadaki değer) 0,90"
        in fact
    )
    counts = "PD/DD'si TTT hissesine göre daha düşük olan 3, daha yüksek olan 2 şirket var."
    assert f"Bu 5 şirketten {counts}" in fact
    assert any(f.startswith("Sektör kıyası yalnızca PD/DD'yi sıralar") for f in result.facts)
    assert any(p.dataset == "industry_peers" for p in result.provenance)
    assert result.facts[0].startswith("Bu sonuç TTT hissesinin ucuz ya da pahalı olduğunu")


def test_no_industry_comparison_is_flagged_not_invented(tmp_path: Path) -> None:
    plain = provider(tmp_path / "a", STATEMENTS)  # a source with no peer list
    result = tools.get_valuation(plain, plain, _no_cpi, "TTT", today=TODAY)
    assert result.data["industry_comparison"] is None
    assert "no_industry_comparison" in {f.code for f in result.quality_flags}
    assert any("bu hisse için böyle bir kıyas bu araçlarda yok" in f for f in result.facts)
    few = [("TTT", "TTT", 1.1, 1.0), ("AAA", "AAA", 0.5, 1.0), ("BBB", "BBB", 0.9, 1.0)]
    p = _peers_provider(tmp_path / "b", few)
    result = tools.get_valuation(p, p, _no_cpi, "TTT", today=TODAY)
    assert result.data["industry_comparison"] is None
    assert any("Only 2 other companies" in f.message for f in result.quality_flags)


def test_a_small_industry_widens_to_the_sector(tmp_path: Path) -> None:
    few = [("TTT", "TTT", 1.1, 1.0), ("AAA", "AAA", 0.5, 1.0)]
    sector = [("TTT", "TTT", 1.1, 1.0), *[(f"S{i}", f"S{i}", 0.2 * i, 1.0) for i in range(1, 7)]]
    p = _peers_provider(tmp_path, few, sector)
    result = tools.get_valuation(p, p, _no_cpi, "TTT", today=TODAY)
    comparison = result.data["industry_comparison"]
    assert (comparison["level"], comparison["group"]) == ("sector", "Basic Materials")
    assert comparison["peer_count"] == 6
    fact = next(f for f in result.facts if f.startswith("Sektör kıyası ("))
    assert 'kaynağın "Steel" sektöründe yeterli şirket olmadığı için daha geniş' in fact


def test_a_ratio_the_source_measures_differently_is_not_compared(tmp_path: Path) -> None:
    peers = [("TTT", "TTT", 5.0, 1.0), *[(f"P{i}", f"P{i}", 1.0, 1.0) for i in range(6)]]
    p = _peers_provider(tmp_path, peers)
    result = tools.get_valuation(p, p, _no_cpi, "TTT", today=TODAY)
    assert result.data["industry_comparison"] is None
    assert any("differs from the one computed here" in f.message for f in result.quality_flags)


def test_mixed_currency_ratios_are_not_trusted(tmp_path: Path) -> None:
    """Yahoo divides a TRY price by a USD book value for some companies (Turkish Airlines: 18
    for a true 0.37) and converts for others (Sony), with nothing to tell them apart. Such
    peers are left out; a company of that kind takes the ratio computed here."""
    root = provider(tmp_path, STATEMENTS)._root

    class Mixed(PeersProvider):
        def industry_peers(self, symbol: str, *, broader: bool = False) -> IndustryPeers:
            group = super().industry_peers(symbol, broader=broader)
            usd = PeerMultiple("USDCO", "USDCO", 99.0, 1.0, 60.0, 1.0, "TRY", "USD")
            own = PeerMultiple("TTT", "TTT", 40.0, 1.0, 220.0, 5.5, "TRY", "USD")
            return dataclasses.replace(group, peers=(own, *group.peers[1:], usd))

    peers = [("TTT", "TTT", 1.1, 1.0), *[(f"P{i}", f"P{i}", 1.0, 1.0) for i in range(5)]]
    p = Mixed(root, peers)
    result = tools.get_valuation(p, p, _no_cpi, "TTT", today=TODAY)
    comparison = result.data["industry_comparison"]
    assert "USDCO" not in comparison["peer_symbols"]
    assert comparison["excluded_mixed_currency"] == 1
    assert comparison["price_to_book_basis"] == "computed"
    assert comparison["price_to_book"] == approx(1.1)  # this tool's figure, not the source's 40
    assert (comparison["peers_lower"], comparison["peers_higher"]) == (5, 0)
    fact = next(f for f in result.facts if f.startswith("Sektör kıyası ("))
    assert "hisse için yukarıdaki hesap kullanıldı" in fact
    assert "1 şirket, kaynağın oranı bu durumda güvenilir olmadığı için kıyasa alınmadı" in fact
