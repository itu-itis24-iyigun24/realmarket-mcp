"""SEC EDGAR provider, with synthetic payloads shaped like the live companyfacts API.

Live shape (verified 2026-09-25): ``facts["us-gaap"][concept]["units"]["USD"]`` is a list of
``{start?, end, val, accn, fy, fp, form, filed, frame?}``; balance-sheet facts have no
``start``. Fourth quarters are not filed as quarters, only as the fiscal year and the
nine-month year-to-date.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import urllib.error
from collections.abc import Mapping
from typing import Any

import pytest

from realmarket_mcp import config, tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.inflation import CpiSeries
from realmarket_mcp.providers import http, sec

STAMP = "2026-09-25T00:00:00Z"


def fact(start: str | None, end: str, val: float, filed: str, form: str = "10-Q") -> dict[str, Any]:
    out: dict[str, Any] = {"end": end, "val": val, "form": form, "filed": filed, "fp": "Q"}
    if start:
        out["start"] = start
    return out


def concept(*facts: dict[str, Any], unit: str = "USD") -> dict[str, Any]:
    return {"units": {unit: list(facts)}}


def company(**gaap: dict[str, Any]) -> dict[str, Any]:
    return {"cik": 1, "entityName": "Example Corp", "facts": {"us-gaap": gaap}}


# Fiscal year = calendar year. Q1-Q3 2025 filed as quarters, FY 2025 in the 10-K.
REVENUE = concept(
    fact("2024-01-01", "2024-12-31", 360, "2025-02-01", "10-K"),
    fact("2025-01-01", "2025-03-31", 100, "2025-05-01"),
    fact("2025-04-01", "2025-06-30", 110, "2025-08-01"),
    fact("2025-04-01", "2025-06-30", 111, "2026-08-01"),  # restated in a later comparative
    fact("2025-07-01", "2025-09-30", 120, "2025-11-01"),
    fact("2025-01-01", "2025-09-30", 331, "2025-11-01"),  # nine months year to date
    fact("2025-01-01", "2025-12-31", 461, "2026-02-01", "10-K"),
    fact("2026-01-01", "2026-03-31", 130, "2026-05-01", "8-K"),  # not a statement form
)
BALANCE = {
    "Assets": concept(fact(None, "2025-12-31", 2000, "2026-02-01", "10-K")),
    "StockholdersEquity": concept(fact(None, "2025-12-31", 800, "2026-02-01", "10-K")),
    "LongTermDebtNoncurrent": concept(fact(None, "2025-12-31", 300, "2026-02-01", "10-K")),
    "LongTermDebtCurrent": concept(fact(None, "2025-12-31", 50, "2026-02-01", "10-K")),
    "CommercialPaper": concept(fact(None, "2025-12-31", 10, "2026-02-01", "10-K")),
}


def parse(payload: Mapping[str, Any]) -> Any:
    return sec.parse_company_facts(payload, symbol="EXM", industry="Widgets", retrieved_at=STAMP)


def by_end(periods: Any) -> dict[str, dict[str, float | None]]:
    return {p.end.isoformat(): p.values for p in periods}


def test_quarters_restatements_and_derived_fourth_quarter() -> None:
    st = parse(company(Revenues=REVENUE, **BALANCE))
    quarters = by_end(st.quarterly)
    assert [q["revenue"] for q in quarters.values()] == [100, 111, 120, 130]
    assert list(quarters) == ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
    assert quarters["2025-12-31"]["revenue"] == 461 - 331  # FY minus nine months
    assert any("2025-12-31" in note and "derived" in note for note in st.source_notes)
    assert by_end(st.annual)["2025-12-31"]["revenue"] == 461
    assert st.currency == "USD" and st.provider == "sec_edgar"


def test_balance_sheet_and_debt_at_period_end() -> None:
    values = by_end(parse(company(Revenues=REVENUE, **BALANCE)).quarterly)["2025-12-31"]
    assert (values["total_assets"], values["total_equity"]) == (2000, 800)
    assert values["total_debt"] == 300 + 50 + 10
    assert by_end(parse(company(Revenues=REVENUE)).quarterly)["2025-12-31"]["total_debt"] is None


def test_long_term_debt_total_is_not_added_to_its_parts() -> None:
    gaap = dict(BALANCE, LongTermDebt=concept(fact(None, "2025-12-31", 350, "2026-02-01")))
    values = by_end(parse(company(Revenues=REVENUE, **gaap)).annual)["2025-12-31"]
    assert values["total_debt"] == 350 + 10


def test_one_concept_per_field_the_most_recent_one() -> None:
    # A bank tags its annual top line as Revenues and its quarters under another element.
    st = parse(
        company(
            Revenues=concept(fact("2024-01-01", "2024-12-31", 400, "2025-02-01", "10-K")),
            RevenuesNetOfInterestExpense=concept(
                fact("2024-01-01", "2024-12-31", 390, "2025-02-01", "10-K"),
                fact("2025-04-01", "2025-06-30", 105, "2025-08-01"),
            ),
        )
    )
    assert [q.values["revenue"] for q in st.quarterly] == [105]
    assert st.annual[0].values["revenue"] == 390  # never mixed with the other element
    assert "revenue=RevenuesNetOfInterestExpense" in st.source_notes[0]


def test_fourth_quarter_uses_first_reported_figures_when_the_year_was_recast() -> None:
    revenue = concept(
        fact("2023-01-01", "2023-12-31", 100, "2024-02-01", "10-K"),
        fact("2023-01-01", "2023-12-31", 80, "2025-02-01", "10-K"),  # recast later
        fact("2023-01-01", "2023-09-30", 75, "2023-11-01"),
    )
    st = parse(company(Revenues=revenue))
    assert by_end(st.quarterly)["2023-12-31"]["revenue"] == 25  # not 80 - 75
    assert by_end(st.annual)["2023-12-31"]["revenue"] == 80
    assert any("restated after first filing" in n and "2023-12-31" in n for n in st.source_notes)


def test_negative_derived_revenue_is_null_but_losses_stay() -> None:
    st = parse(
        company(
            Revenues=concept(
                fact("2025-01-01", "2025-12-31", 90, "2026-02-01", "10-K"),
                fact("2025-01-01", "2025-09-30", 100, "2025-11-01"),
            ),
            NetIncomeLoss=concept(
                fact("2025-01-01", "2025-12-31", -30, "2026-02-01", "10-K"),
                fact("2025-01-01", "2025-09-30", -10, "2025-11-01"),
            ),
        )
    )
    values = by_end(st.quarterly)["2025-12-31"]
    assert values["revenue"] is None and values["net_income"] == -20


def test_debt_without_a_long_term_figure_is_null() -> None:
    gaap = {"ShortTermBorrowings": concept(fact(None, "2025-12-31", 70, "2026-02-01"))}
    assert (
        by_end(parse(company(Revenues=REVENUE, **gaap)).annual)["2025-12-31"]["total_debt"] is None
    )


def test_lease_inclusive_debt_and_commercial_paper_not_counted_twice() -> None:
    gaap = {
        "LongTermDebtAndCapitalLeaseObligations": concept(fact(None, "2025-12-31", 400, "2026")),
        "LongTermDebtAndCapitalLeaseObligationsCurrent": concept(
            fact(None, "2025-12-31", 20, "2026")
        ),
        "ShortTermBorrowings": concept(fact(None, "2025-12-31", 30, "2026")),
        "CommercialPaper": concept(fact(None, "2025-12-31", 25, "2026")),  # inside the 30
    }
    values = by_end(parse(company(Revenues=REVENUE, **gaap)).annual)["2025-12-31"]
    assert values["total_debt"] == 400 + 20 + 30


def test_unit_with_most_facts_wins() -> None:
    eur = [fact("2025-01-01", "2025-03-31", 5, "2025-05-01"), fact(None, "2025-03-31", 9, "x")]
    gaap = {"Revenues": {"units": {"EUR": eur, "USD": [eur[0]]}}}
    assert parse(company(**gaap)).currency == "EUR"


def test_no_us_gaap_facts() -> None:
    with pytest.raises(ToolError) as raised:
        parse({"facts": {"ifrs-full": {}}})
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE


def test_foreign_currency_reporter() -> None:
    st = parse(
        company(Revenues=concept(fact("2025-01-01", "2025-03-31", 5, "2025-05-01"), unit="EUR"))
    )
    assert st.currency == "EUR"


def test_symbol_shapes() -> None:
    for s in ("AAPL", "brk-b", "CIK0000320193", "cik320193"):
        assert sec.looks_like_us_symbol(s), s
    # A bare number is a Tokyo/Taiwan/Hong Kong code, not a CIK; it must not reach the SEC.
    for s in ("THYAO.IS", "^GSPC", "EURUSD=X", "GC=F", "VOD.L", "7203", "320193"):
        assert not sec.looks_like_us_symbol(s), s


class Fake:
    def __init__(self, routes: Mapping[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: Mapping[str, str]) -> bytes:
        self.calls.append((url, dict(headers)))
        route = self.routes.get(url)
        if isinstance(route, ToolError):
            raise route
        if route is None:
            raise sec.NOT_FOUND
        return json.dumps(route).encode()


TICKERS = {"0": {"cik_str": 1, "ticker": "EXM", "title": "Example"},
           "1": {"cik_str": 2, "ticker": "BRK-B", "title": "B"}}  # fmt: skip
FACTS_1 = sec.FACTS_URL.format(cik=1)


@pytest.fixture(autouse=True)
def _fresh_ticker_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sec, "_tickers", None)


def provider(routes: Mapping[str, Any]) -> tuple[sec.SecEdgarProvider, Fake]:
    fake = Fake(routes)
    return sec.SecEdgarProvider("me@example.org", retrieved_at=STAMP, fetch=fake), fake


def test_ticker_lookup_user_agent_and_industry() -> None:
    p, fake = provider(
        {
            sec.TICKERS_URL: TICKERS,
            FACTS_1: company(Revenues=REVENUE),
            sec.SUBMISSIONS_URL.format(cik=1): {"sicDescription": "National Commercial Banks"},
        }
    )
    st = p.financials("exm")
    assert st.industry == "National Commercial Banks" and st.symbol == "EXM"
    agent = fake.calls[0][1]["User-Agent"]
    assert "me@example.org" in agent and "http" not in agent  # the SEC rejects URLs here
    assert p.resolve_cik("BRK.B") == 2


def test_cik_needs_no_ticker_list() -> None:
    p, fake = provider({FACTS_1: company(Revenues=REVENUE)})
    p.financials("CIK0000000001")
    assert sec.TICKERS_URL not in [url for url, _ in fake.calls]


def test_unknown_ticker_and_unreachable_list(monkeypatch: pytest.MonkeyPatch) -> None:
    p, _ = provider({sec.TICKERS_URL: TICKERS})
    with pytest.raises(ToolError) as raised:
        p.financials("ZZZZ")
    assert raised.value.code is ErrorCode.UNKNOWN_SYMBOL

    monkeypatch.setattr(sec, "_tickers", None)  # the list is cached per process
    p, _ = provider({sec.TICKERS_URL: http.unavailable("SEC EDGAR", "HTTP 503")})
    with pytest.raises(ToolError) as raised:
        p.financials("EXM")
    assert raised.value.code is ErrorCode.PROVIDER_UNAVAILABLE and "CIK" in raised.value.hint


def test_company_without_facts() -> None:
    p, _ = provider({})
    with pytest.raises(ToolError) as raised:
        p.financials("CIK1")
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE and "XBRL" in raised.value.message


def test_contact_is_required() -> None:
    with pytest.raises(ToolError) as raised:
        sec.SecEdgarProvider("not-an-email", retrieved_at=STAMP)
    assert raised.value.code is ErrorCode.MISSING_API_KEY
    assert sec.CONTACT_ENV in raised.value.hint


def test_http_403_maps_to_the_given_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: Any, **_k: Any) -> Any:
        raise urllib.error.HTTPError("u", 403, "Forbidden", {}, io.BytesIO())  # type: ignore[arg-type]

    monkeypatch.setattr(http.urllib.request, "urlopen", refuse)
    forbidden = ToolError(ErrorCode.MISSING_API_KEY, "refused", "set contact")
    with pytest.raises(ToolError) as raised:
        http.get("https://data.sec.gov/x", {}, source="SEC EDGAR", forbidden=forbidden)
    assert raised.value is forbidden


def test_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(config.PROVIDER_ENV, raising=False)
    monkeypatch.delenv(config.FIXTURE_DIR_ENV, raising=False)
    with_contact = {sec.CONTACT_ENV: "me@example.org"}
    chosen = config.load_financials_provider("AAPL", retrieved_at=STAMP, env=with_contact)
    assert chosen.name == "sec_edgar"
    forced = {**with_contact, config.FINANCIALS_PROVIDER_ENV: "sec"}
    assert isinstance(
        config.load_financials_provider("AAPL", retrieved_at=STAMP, env=forced),
        sec.SecEdgarProvider,
    )
    with pytest.raises(ToolError) as raised:  # no contact, no price provider
        config.load_financials_provider("AAPL", retrieved_at=STAMP, env={})
    assert sec.CONTACT_ENV in raised.value.hint
    with pytest.raises(ToolError) as raised:
        config.load_financials_provider(
            "AAPL", retrieved_at=STAMP, env={config.FINANCIALS_PROVIDER_ENV: "sec"}
        )
    assert raised.value.code is ErrorCode.MISSING_API_KEY
    with pytest.raises(ToolError):  # a Borsa Istanbul symbol never goes to the SEC
        config.load_financials_provider("THYAO.IS", retrieved_at=STAMP, env=with_contact)


def test_tool_reports_the_official_source() -> None:
    p, _ = provider({FACTS_1: company(Revenues=REVENUE, **BALANCE)})

    def cpi(_r: str, _s: dt.date, _e: dt.date) -> CpiSeries:
        months = {(2024, 12): 100.0, (2025, 9): 102.0, (2025, 12): 103.0}
        return CpiSeries("US", "test", "CPI", STAMP, months)

    result = tools.get_financials(p, cpi, "CIK1", today=dt.date(2026, 9, 25))
    notes = " ".join(result.notes)
    assert "SEC EDGAR" in notes and "KAP" not in notes
    assert result.data["inflation_accounting"].startswith("not applied")
    annual = result.data["growth"]["annual"]
    assert annual["revenue"]["real"] == pytest.approx(461 / (360 * 1.03) - 1, abs=1e-6)
    assert result.provenance[0].provider == "sec_edgar"


class _Stub:
    def __init__(self, name: str, result: Any) -> None:
        self.name, self.result, self.calls = name, result, 0

    def financials(self, symbol: str) -> Any:
        self.calls += 1
        if isinstance(self.result, ToolError):
            raise self.result
        return self.result


def test_fallback_covers_what_the_sec_cannot() -> None:
    ifrs = ToolError(ErrorCode.NO_DATA_IN_RANGE, "TSM files no US GAAP statements.", "IFRS")
    backup = _Stub("yahoo", "statements from the price provider")
    chained = config._WithFallback(_Stub("sec_edgar", ifrs), lambda: backup)
    assert chained.financials("TSM") == "statements from the price provider"

    outage = http.unavailable("SEC EDGAR", "HTTP 503")  # an outage is reported, not hidden
    chained = config._WithFallback(_Stub("sec_edgar", outage), lambda: backup)
    with pytest.raises(ToolError) as raised:
        chained.financials("AAPL")
    assert raised.value is outage and backup.calls == 1


def test_without_a_price_provider_the_sec_error_is_kept() -> None:
    ifrs = ToolError(ErrorCode.NO_DATA_IN_RANGE, "TSM files no US GAAP statements.", "IFRS")

    def missing() -> Any:
        raise ToolError(ErrorCode.MISSING_API_KEY, "no price provider", "set it")

    with pytest.raises(ToolError) as raised:
        config._WithFallback(_Stub("sec_edgar", ifrs), missing).financials("TSM")
    assert raised.value is ifrs
