"""facts: Turkish sentences that carry each figure with its meaning, checked by hand."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from realmarket_mcp import facts, tools
from realmarket_mcp.providers.fixture import FixtureProvider

FIXTURES = Path(__file__).parent / "fixtures" / "basic"


def test_turkish_number_formats() -> None:
    assert facts.number(1234567.891) == "1.234.567,89"
    assert facts.pct(0.71) == "+%71,0"
    assert facts.pct(-0.0469) == "-%4,69"  # small figures keep two decimals
    assert facts.pct(0.676, signed=False) == "%67,6"
    assert facts.points(-0.371) == "-37,1 puan"
    assert facts.money(20340, "TRY", signed=True) == "+20.340,00 TL"
    assert facts.money(-5, "USD") == "-5,00 USD"
    assert facts.date("2026-09-25", weekday=True) == "25 Eylül 2026 Cuma"
    assert facts.month("2026-08") == "Ağustos 2026"
    assert facts.number(-0.001) == "0,00"  # no "-0,00"


def test_portfolio_facts_bind_each_figure_to_its_meaning() -> None:
    result = tools.analyze_portfolio(
        FixtureProvider(FIXTURES),
        [
            {"type": "buy", "symbol": "TTT", "date": "2024-01-02", "quantity": 1},
            {"type": "buy", "symbol": "AAA", "date": "2024-01-02", "quantity": 1},
        ],
        compare_with="AAA",
        today=dt.date(2025, 1, 10),  # a year on: an annual rate over 8 days overflows
    )
    text = "\n".join(result.facts)
    assert "Toplam kâr/zarar +40,00 TL (alışlara oranla +%13,3)" in text  # (20 + 20) / 300
    # TTT 200 -> 220 and AAA 100 -> 120 over the same sessions: TTT is behind by 10 points.
    assert "TTT fiyatı ilk alış (2 Ocak 2024) ile son seans (8 Ocak 2024) arasında +%10,0" in text
    assert "Fark -10,0 puan: bu dönemde TTT, AAA karşısında geride." in text
    # 300 TL in AAA at 100 is 3 units, worth 360 at 120; the account is worth 340.
    assert "Hesabın tamamı:" in text and "hesap AAA karşısında geride." in text
    assert result.to_dict()["facts"] == list(result.facts)


def test_results_without_facts_keep_their_envelope() -> None:
    result = tools.get_price_summary(
        FixtureProvider(FIXTURES), "TTT", start="2024-01-01", today=dt.date(2024, 1, 10)
    )
    assert "facts" not in result.to_dict()
