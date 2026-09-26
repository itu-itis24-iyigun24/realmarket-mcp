"""ESEF (filings.xbrl.org) provider, with synthetic payloads shaped like the live API.

Live shape (verified 2026-09-26): /api/filings is JSON:API with `meta.count` and filing
attributes (`period_end`, `country`, `error_count`, `inconsistency_count`, `date_added`,
`json_url`); reports are xBRL-JSON whose facts carry `dimensions` {concept, entity, period,
unit} and a string `value`. Period boundaries are midnight instants: a year ending
2025-12-31 is written `2025-01-01T00:00:00/2026-01-01T00:00:00`.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.parse
from collections.abc import Mapping
from typing import Any

import pytest

from realmarket_mcp import config, tools
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.inflation import CpiSeries
from realmarket_mcp.providers import esef

STAMP = "2026-09-26T00:00:00Z"
LEI = "724500Y6DUVHQD6OXN27"


def fact(
    concept: str, period: str, value: float, unit: str = "EUR", **extra: str
) -> dict[str, Any]:
    dims = {
        "concept": concept,
        "entity": f"scheme:{LEI}",
        "period": period,
        "unit": f"iso4217:{unit}",
    }
    return {"value": str(value), "dimensions": {**dims, **extra}}


def year(y: int) -> str:
    return f"{y}-01-01T00:00:00/{y + 1}-01-01T00:00:00"


def end_of(y: int) -> str:
    return f"{y + 1}-01-01T00:00:00"


def report(*facts: dict[str, Any]) -> dict[str, Any]:
    return {"documentInfo": {"documentType": "https://xbrl.org/2021/xbrl-json"},
            "facts": {f"f{i}": f for i, f in enumerate(facts)}}  # fmt: skip


def filing(period_end: str, url: str, **extra: Any) -> dict[str, Any]:
    base = {"period_end": period_end, "country": "NL", "error_count": 0}
    return {**base, "inconsistency_count": 0, "date_added": "2026-03-01", "json_url": url, **extra}


REPORT_2025 = report(
    fact("ifrs-full:RevenueFromContractsWithCustomers", year(2025), 330),
    fact("ifrs-full:RevenueFromContractsWithCustomers", year(2024), 290),  # restated comparative
    fact("ifrs-full:ProfitLossAttributableToOwnersOfParent", year(2025), 100),
    fact("ifrs-full:ProfitLoss", year(2025), 101),  # lower priority: not used
    fact("ifrs-full:Assets", end_of(2025), 560),
    fact("ifrs-full:EquityAttributableToOwnersOfParent", end_of(2025), 240),
    fact("ifrs-full:NoncurrentPortionOfNoncurrentBorrowings", end_of(2025), 40),
    fact("ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings", end_of(2025), 5),
    # A segment breakdown (extra dimension) must not be read as the group figure.
    fact(
        "ifrs-full:RevenueFromContractsWithCustomers",
        year(2025),
        999,
        **{"ifrs-full:SegmentsAxis": "x"},
    ),
)
REPORT_2024 = report(
    fact("ifrs-full:RevenueFromContractsWithCustomers", year(2024), 280),  # first reported
    fact("ifrs-full:RevenueFromContractsWithCustomers", year(2023), 270),
    fact("ifrs-full:ProfitLossAttributableToOwnersOfParent", year(2024), 80),
    fact("ifrs-full:Assets", end_of(2024), 520),
    fact("ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings", end_of(2024), 9),
)


def parse(*docs: dict[str, Any], countries: tuple[str, ...] = ("NL",)) -> Any:
    meta = [filing(f"{2025 - i}-12-31", f"/r{i}.json") for i in range(len(docs))]
    pairs = list(zip(meta, docs, strict=True))
    return esef.parse_reports(pairs, lei=LEI, retrieved_at=STAMP, countries=countries)


def by_end(periods: Any) -> dict[str, dict[str, float | None]]:
    return {p.end.isoformat(): p.values for p in periods}


def test_annual_figures_dates_and_restatements() -> None:
    st = parse(REPORT_2025, REPORT_2024)
    years = by_end(st.annual)
    assert list(years) == ["2023-12-31", "2024-12-31", "2025-12-31"]  # midnight -> last day
    assert years["2025-12-31"]["revenue"] == 330  # the segment figure (999) is ignored
    assert years["2024-12-31"]["revenue"] == 290  # the newer report's restated comparative
    assert years["2025-12-31"]["net_income"] == 100  # attributable to owners, not ProfitLoss
    assert (st.currency, st.country, st.provider, st.quarterly) == ("EUR", "NL", "esef", ())
    assert "RevenueFromContractsWithCustomers" in st.source_notes[0]


def test_debt_needs_a_total_or_non_current_part() -> None:
    years = by_end(parse(REPORT_2025, REPORT_2024).annual)
    assert years["2025-12-31"]["total_debt"] == 40 + 5
    assert years["2024-12-31"]["total_debt"] is None  # only a current part: not the debt


def test_quarters_and_derived_fourth_quarter() -> None:
    q = "ifrs-full:Revenue"
    q1_2026 = report(fact(q, "2026-01-01T00:00:00/2026-04-01T00:00:00", 120))
    annual_2025 = report(fact(q, year(2025), 400), fact(q, year(2024), 350))
    q3_2025 = report(
        fact(q, "2025-01-01T00:00:00/2025-10-01T00:00:00", 290),  # nine months
        fact(q, "2025-07-01T00:00:00/2025-10-01T00:00:00", 100),
    )
    st = parse(q1_2026, annual_2025, q3_2025)
    quarters = by_end(st.quarterly)
    assert quarters["2025-12-31"]["revenue"] == 400 - 290
    assert quarters["2025-09-30"]["revenue"] == 100 and quarters["2026-03-31"]["revenue"] == 120
    assert list(by_end(st.annual)) == ["2024-12-31", "2025-12-31"]
    assert any("derived" in n and "2025-12-31" in n for n in st.source_notes)


def test_trailing_twelve_months_in_an_interim_report_is_not_a_fiscal_year() -> None:
    q = "ifrs-full:Revenue"
    h1_2026 = report(
        fact(q, "2025-07-01T00:00:00/2026-07-01T00:00:00", 420),  # trailing twelve months
        fact(q, "2026-01-01T00:00:00/2026-07-01T00:00:00", 210),  # half year
    )
    st = parse(h1_2026, report(fact(q, year(2025), 400)))
    assert list(by_end(st.annual)) == ["2025-12-31"]


def test_no_fourth_quarter_from_restated_figures() -> None:
    q = "ifrs-full:Revenue"
    annual_2025 = report(fact(q, year(2025), 300), fact(q, year(2024), 260))  # 2024 restated
    q3_2025 = report(fact(q, "2025-01-01T00:00:00/2025-10-01T00:00:00", 290))
    annual_2024 = report(fact(q, year(2024), 280))  # 2024 as first reported
    st = parse(annual_2025, q3_2025, annual_2024)
    assert "2025-12-31" not in by_end(st.quarterly)
    assert any("not derived" in n for n in st.source_notes)


def test_currency_comes_from_the_newest_report() -> None:
    q = "ifrs-full:Revenue"
    newest = report(fact(q, year(2025), 10, unit="EUR"))
    older = report(*(fact(q, year(y), 70, unit="HRK") for y in (2019, 2020, 2021, 2022)))
    st = parse(newest, older, countries=("HR",))
    assert st.currency == "EUR" and list(by_end(st.annual)) == ["2025-12-31"]
    assert any("HRK" in n and "not used" in n for n in st.source_notes)


def test_home_country_only_when_its_currency_is_the_reporting_currency() -> None:
    assert parse(REPORT_2025, countries=("GB", "NL")).country == "NL"  # EUR filer, two copies
    assert parse(REPORT_2025, countries=("GB",)).country is None  # GBP country, EUR figures


def test_incomplete_debt_sets_are_never_summed() -> None:
    parts = (
        fact("ifrs-full:NoncurrentPortionOfNoncurrentBorrowings", end_of(2025), 60),
        fact("ifrs-full:CurrentPortionOfLongtermBorrowings", end_of(2025), 9),
    )
    st = parse(report(fact("ifrs-full:Revenue", year(2025), 1), *parts))
    assert by_end(st.annual)["2025-12-31"]["total_debt"] is None  # short-term part missing
    complete = (*parts, fact("ifrs-full:ShorttermBorrowings", end_of(2025), 5))
    st = parse(report(fact("ifrs-full:Revenue", year(2025), 1), *complete))
    assert by_end(st.annual)["2025-12-31"]["total_debt"] == 74


def test_no_ifrs_figures() -> None:
    with pytest.raises(ToolError) as raised:
        parse(report(fact("acme:Sales", year(2025), 1)))
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE


def test_lei_detection_and_routing() -> None:
    assert esef.lei_of(LEI) == LEI and esef.lei_of(f"lei:{LEI.lower()}") == LEI
    for other in ("ASML.AS", "AAPL", "CIK0000320193", "724500Y6DUVHQD6OXN2"):
        assert esef.lei_of(other) is None
    chosen = config.load_financials_provider(LEI, retrieved_at=STAMP, env={})
    assert isinstance(chosen, esef.EsefProvider)  # keyless: no settings needed


class Api:
    """Routes /api/filings and /api/entities by the LEI or name in the JSON filter."""

    def __init__(self, filings: dict[str, list[dict[str, Any]]], docs: Mapping[str, Any]) -> None:
        self.filings, self.docs, self.urls = filings, docs, []  # type: ignore[var-annotated]

    def __call__(self, url: str, headers: Mapping[str, str]) -> bytes:
        self.urls.append(url)
        path, _, query = url.removeprefix(esef.BASE).partition("?")
        params = urllib.parse.parse_qs(query)
        if path == "/api/filings":
            lei = json.loads(params["filter"][0])[0]["val"]["val"]
            rows = self.filings.get(lei, [])
            size = int(params["page[size]"][0])
            data = [{"attributes": r} for r in rows[:size]]
            return json.dumps({"data": data, "meta": {"count": len(rows)}}).encode()
        if path == "/api/entities":
            needle = json.loads(params["filter"][0])[0]["val"].strip("%").lower()
            data = [
                {"attributes": {"name": name, "identifier": lei}}
                for lei, name in (("A" * 18 + "01", "Enel SpA"), ("B" * 18 + "02", "Genel Energy"))
                if needle in name.lower()
            ]
            return json.dumps({"data": data}).encode()
        return json.dumps(self.docs[path]).encode()


def test_provider_prefers_the_cleaner_duplicate_and_stops_at_three_years() -> None:
    rows = [
        filing("2025-12-31", "/bad.json", error_count=3),
        filing("2025-12-31", "/good.json"),
        filing("2024-12-31", "/r2024.json"),
        filing("2023-12-31", "/r2023.json"),
    ]
    api = Api({LEI: rows}, {"/good.json": REPORT_2025, "/r2024.json": REPORT_2024})
    st = esef.EsefProvider(retrieved_at=STAMP, fetch=api).financials(LEI)
    assert by_end(st.annual)["2025-12-31"]["revenue"] == 330
    fetched = [u for u in api.urls if "/api/" not in u]
    assert fetched == [esef.BASE + "/good.json", esef.BASE + "/r2024.json"]  # 3 years: stop


def test_provider_without_filings_names_the_coverage_gap() -> None:
    with pytest.raises(ToolError) as raised:
        esef.EsefProvider(retrieved_at=STAMP, fetch=Api({}, {})).financials(LEI)
    assert raised.value.code is ErrorCode.NO_DATA_IN_RANGE
    assert "Germany and Ireland" in raised.value.hint


def test_find_official_filer_lists_candidates_with_counts() -> None:
    api = Api({"A" * 18 + "01": [filing("2025-12-31", "/x.json", country="IT")]}, {})
    finder = esef.EsefProvider(retrieved_at=STAMP, fetch=api).find_filer
    result = tools.find_official_filer(
        finder, "enel", retrieved_at=STAMP, today=dt.date(2026, 9, 26)
    )
    candidates = result.data["candidates"]
    assert [(c["name"], c["filings"], c["country"]) for c in candidates] == [
        ("Enel SpA", 1, "IT"),
        ("Genel Energy", 0, None),
    ]
    empty = tools.find_official_filer(
        finder, "zzzz", retrieved_at=STAMP, today=dt.date(2026, 9, 26)
    )
    assert "no_match" in {f.code for f in empty.quality_flags}
    with pytest.raises(ToolError):
        tools.find_official_filer(finder, "ab", retrieved_at=STAMP, today=dt.date(2026, 9, 26))


def test_euro_reporter_uses_its_home_country_cpi_and_shows_the_latest_year() -> None:
    api = Api({LEI: [filing("2025-12-31", "/good.json")]}, {"/good.json": REPORT_2025})
    regions: list[str] = []

    def cpi(region: str, _s: dt.date, _e: dt.date) -> CpiSeries:
        regions.append(region)
        return CpiSeries(region, "test", "CPI", STAMP, {(2024, 12): 100.0, (2025, 12): 110.0})

    provider = esef.EsefProvider(retrieved_at=STAMP, fetch=api)
    result = tools.get_financials(provider, cpi, LEI, today=dt.date(2026, 9, 26))
    assert regions == ["NL"]
    assert result.data["latest_quarter"] is None
    assert result.data["latest_year"]["end"] == "2025-12-31"
    assert result.data["latest_year"]["net_margin"] == pytest.approx(100 / 330, abs=1e-6)
    annual = result.data["growth"]["annual"]
    assert annual["revenue"]["real"] == pytest.approx(330 / (290 * 1.1) - 1, abs=1e-6)
    assert result.provenance[0].to_dict()["attribution"].startswith("Source: the company's ESEF")
