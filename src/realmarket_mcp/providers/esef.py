"""Official annual figures of European and UK listed companies, from their ESEF filings.

Since 2021 EU-listed companies file their annual financial report in ESEF (inline XBRL, IFRS)
with their national regulator; filings.xbrl.org, run by XBRL International, collects them and
serves each as xBRL-JSON. Free and keyless; its terms place no restrictions on use of the data
(read 2026-09-26). Coverage depends on the national collections it indexes: **Germany and
Ireland have no filings there** (0 on 2026-09-26), most other EU countries, Norway and the UK
have hundreds each.

Companies are identified by their LEI (Legal Entity Identifier), not a ticker. `find_filer`
searches by name and returns candidates; the caller picks one. Nothing is matched
automatically, because names are ambiguous ("enel" matches three companies).

Figures are annual (the report and its prior-year comparatives), as the company tagged them in
IFRS. They can differ from what the company reports under US GAAP elsewhere (ASML's 2024 net
profit: IFRS EUR 8.35bn here, US GAAP EUR 7.57bn to the SEC). xBRL-JSON writes period ends as
the next day at midnight; they are converted to the last day of the period.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.models import FinancialPeriod, FinancialStatements
from realmarket_mcp.providers import http

Fetch = Callable[[str, Mapping[str, str]], bytes]

BASE = "https://filings.xbrl.org"
SOURCE = "filings.xbrl.org"
NOT_COVERED = ("DE", "IE")  # no filings indexed (checked 2026-09-26)
LEI = re.compile(r"^(?:LEI:)?([A-Z0-9]{18}[0-9]{2})$", re.IGNORECASE)
MAX_REPORTS = 6  # annual reports are up to a few MB; interim reports are small
YEARS_WANTED = 3
MAX_CANDIDATES = 8

# One IFRS element per field: the first, in this order, that the latest report uses.
CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": ("ifrs-full:Revenue", "ifrs-full:RevenueFromContractsWithCustomers"),
    "gross_profit": ("ifrs-full:GrossProfit",),
    "operating_income": ("ifrs-full:ProfitLossFromOperatingActivities",),
    "net_income": ("ifrs-full:ProfitLossAttributableToOwnersOfParent", "ifrs-full:ProfitLoss"),
    "total_assets": ("ifrs-full:Assets",),
    "total_equity": ("ifrs-full:EquityAttributableToOwnersOfParent", "ifrs-full:Equity"),
}
# Debt: the first complete set tagged at the date. Every element of a set is required; a set
# with a part missing is never summed (a missing part is not zero).
DEBT_SETS: tuple[tuple[str, ...], ...] = (
    ("ifrs-full:Borrowings",),
    (
        "ifrs-full:NoncurrentPortionOfNoncurrentBorrowings",
        "ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
    ),
    (
        "ifrs-full:NoncurrentPortionOfNoncurrentBorrowings",
        "ifrs-full:CurrentPortionOfLongtermBorrowings",
        "ifrs-full:ShorttermBorrowings",
    ),
)
# The currency of each country, for choosing the inflation region of a filer: its home
# country is used only when that country's currency is the reporting currency.
EURO_AREA = frozenset(
    {"AT", "BE", "CY", "DE", "EE", "ES", "FI", "FR", "GR", "HR", "IE", "IT", "LT", "LU", "LV",
     "MT", "NL", "PT", "SI", "SK"}
)  # fmt: skip
NATIONAL_CURRENCY = {
    "GB": "GBP", "SE": "SEK", "DK": "DKK", "NO": "NOK", "PL": "PLN", "CZ": "CZK", "HU": "HUF",
    "RO": "RON", "BG": "BGN", "IS": "ISK", "CH": "CHF",
}  # fmt: skip
FLOWS = ("revenue", "gross_profit", "operating_income", "net_income")
STOCKS = ("total_assets", "total_equity")
YEAR_DAYS = (350, 380)
PLAIN_DIMENSIONS = {"concept", "entity", "period", "unit", "language"}


def currency_of(country: str | None) -> str | None:
    if not country:
        return None
    return "EUR" if country in EURO_AREA else NATIONAL_CURRENCY.get(country)


def lei_of(symbol: str) -> str | None:
    match = LEI.match(symbol.strip())
    return match.group(1).upper() if match else None


class EsefProvider:
    name = "esef"

    def __init__(self, *, retrieved_at: str, fetch: Fetch | None = None) -> None:
        self._retrieved_at = retrieved_at
        self._fetch = fetch or _default_fetch

    def _json(self, path: str) -> Any:
        body = self._fetch(BASE + path, {})
        try:
            return json.loads(body)
        except (UnicodeDecodeError, ValueError):
            raise http.unavailable(SOURCE, "unreadable response") from None

    def _filings(self, lei: str, size: int) -> tuple[int, list[dict[str, Any]]]:
        condition = [
            {"name": "entity", "op": "has", "val": {"name": "identifier", "op": "eq", "val": lei}}
        ]
        query = urllib.parse.urlencode(
            {"filter": json.dumps(condition), "page[size]": size, "sort": "-period_end"}
        )
        payload = self._json(f"/api/filings?{query}")
        return int(payload.get("meta", {}).get("count", 0)), [
            x["attributes"] for x in payload.get("data", [])
        ]

    def find_filer(self, name: str) -> list[dict[str, Any]]:
        """Companies whose registered name contains ``name``, with their filing counts."""
        literal = re.sub(r"[%_]", " ", name).strip()  # no wildcards from the caller
        condition = [{"name": "name", "op": "ilike", "val": f"%{literal}%"}]
        query = urllib.parse.urlencode(
            {"filter": json.dumps(condition), "page[size]": MAX_CANDIDATES}
        )
        entities = self._json(f"/api/entities?{query}").get("data", [])
        out = []
        for entity in entities[:MAX_CANDIDATES]:
            lei = entity["attributes"]["identifier"]
            count, latest = self._filings(lei, 1)
            out.append(
                {
                    "name": entity["attributes"]["name"],
                    "lei": lei,
                    "filings": count,
                    "latest_period_end": latest[0]["period_end"] if latest else None,
                    "country": latest[0]["country"] if latest else None,
                }
            )
        return out

    def financials(self, symbol: str) -> FinancialStatements:
        lei = lei_of(symbol)
        if lei is None:
            raise ToolError(
                ErrorCode.INVALID_ARGUMENT,
                f"{symbol} is not an LEI.",
                "Find the company's LEI with find_official_filer, then pass it as the symbol.",
            )
        _, filings = self._filings(lei, 20)
        if not filings:
            raise ToolError(
                ErrorCode.NO_DATA_IN_RANGE,
                f"filings.xbrl.org holds no annual report for LEI {lei}.",
                "Companies in Germany and Ireland are not covered; for others the national "
                "collection may not have reached the index yet. Use the company's ticker for "
                "figures from the price provider instead.",
            )
        by_period: dict[str, dict[str, Any]] = {}
        countries: dict[str, list[str]] = {}
        for filing in filings:  # one report per period: fewest errors, then the latest added
            key = filing["period_end"]
            countries.setdefault(key, []).append(str(filing.get("country") or ""))
            best = by_period.get(key)
            rank = (-int(filing.get("error_count") or 0), str(filing.get("date_added", "")))
            if best is None or rank > (
                -int(best.get("error_count") or 0),
                str(best.get("date_added", "")),
            ):
                by_period[key] = filing
        # Newest first until the annual reports read cover three years (or two annual reports
        # are read): a company that also files interim reports has several before its latest
        # annual one.
        documents: list[tuple[dict[str, Any], Any]] = []
        for key in sorted(by_period, reverse=True)[:MAX_REPORTS]:
            documents.append((by_period[key], self._json(by_period[key]["json_url"])))
            annual_docs = [d for _, d in documents if _profile(_plain_facts(d))[1]]
            years = {e for d in annual_docs for e in _year_ends(_plain_facts(d))}
            if len(annual_docs) >= 2 or len(years) >= YEARS_WANTED:
                break
        homes = sorted({c for key in by_period for c in countries[key] if c})
        return parse_reports(documents, lei=lei, retrieved_at=self._retrieved_at, countries=homes)


_cache: OrderedDict[str, bytes] = OrderedDict()
CACHE_SIZE = 6  # report JSON files are immutable per URL and a few MB each


def _default_fetch(url: str, headers: Mapping[str, str]) -> bytes:
    immutable = "/api/" not in url
    if immutable and url in _cache:
        _cache.move_to_end(url)
        return _cache[url]
    not_found = ToolError(
        ErrorCode.NO_DATA_IN_RANGE,
        "filings.xbrl.org has no such document.",
        "The report may have been withdrawn; retry find_official_filer.",
    )
    body = http.get(url, headers, source=SOURCE, timeout=60, not_found=not_found)
    if immutable:
        _cache[url] = body
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return body


# --- parsing --------------------------------------------------------------------------------


def _day_before(stamp: str) -> dt.date:
    """xBRL-JSON period boundaries are instants at midnight; the period ends the day before."""
    return dt.date.fromisoformat(stamp[:10]) - dt.timedelta(days=1)


def _plain_facts(document: Mapping[str, Any]) -> list[tuple[str, str, str, float]]:
    """(concept, unit, period, value) for undimensioned monetary facts."""
    out = []
    for fact in document.get("facts", {}).values():
        dims = fact.get("dimensions", {})
        unit = dims.get("unit", "")
        if not set(dims) <= PLAIN_DIMENSIONS or not unit.startswith("iso4217:"):
            continue
        try:
            value = float(fact["value"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append((dims["concept"], unit.removeprefix("iso4217:"), dims.get("period", ""), value))
    return out


def _span(period: str) -> tuple[dt.date, dt.date] | None:
    if "/" not in period:
        return None
    raw_start, raw_end = period.split("/")
    return dt.date.fromisoformat(raw_start[:10]), _day_before(raw_end)


def _days(span: tuple[dt.date, dt.date]) -> int:
    return (span[1] - span[0]).days + 1


def _is_year(span: tuple[dt.date, dt.date]) -> bool:
    return YEAR_DAYS[0] <= _days(span) <= YEAR_DAYS[1]


def _revenue_spans(rows: list[tuple[str, str, str, float]]) -> list[tuple[dt.date, dt.date]]:
    return [
        span
        for concept, _, period, _ in rows
        if concept in CONCEPTS["revenue"] and (span := _span(period)) is not None
    ]


def _profile(rows: list[tuple[str, str, str, float]]) -> tuple[dt.date | None, bool]:
    """(the report's own period end, whether it is an annual report). A report is annual when a
    year-long revenue period ends on its date and no shorter one does: an interim report's
    trailing-twelve-month figure comes with the quarter or half year ending the same day."""
    spans = _revenue_spans(rows)
    if not spans:
        return None, False
    end = max(e for _, e in spans)
    at_end = [span for span in spans if span[1] == end]
    return end, any(_is_year(x) for x in at_end) and not any(_days(x) < 300 for x in at_end)


def _year_ends(rows: list[tuple[str, str, str, float]]) -> set[dt.date]:
    return {e for span in _revenue_spans(rows) if _is_year(span) for e in [span[1]]}


def _near_fiscal_end(end: dt.date, fiscal: set[tuple[int, int]]) -> bool:
    """Within a week of a fiscal year end's month and day (52/53-week years move a few days)."""
    for month, day in fiscal:
        for year in (end.year - 1, end.year, end.year + 1):
            if abs((end - dt.date(year, month, min(day, 28))).days) <= 7 + max(0, day - 28):
                return True
    return False


def _majority_currency(rows: list[tuple[str, str, str, float]]) -> str | None:
    counts: dict[str, int] = {}
    for concept, unit, _, _ in rows:
        if concept in CONCEPTS["revenue"] + CONCEPTS["total_assets"]:
            counts[unit] = counts.get(unit, 0) + 1
    return max(sorted(counts), key=lambda u: counts[u]) if counts else None


def parse_reports(
    documents: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    *,
    lei: str,
    retrieved_at: str,
    countries: Sequence[str] = (),
) -> FinancialStatements:
    """``documents``: (filing attributes, xBRL-JSON), newest report first. A value from a newer
    report wins, so earlier periods appear as restated in the latest comparatives.
    ``countries``: the collections the filer's reports appear in."""
    all_rows = [_plain_facts(doc) for _, doc in documents]
    currencies = [_majority_currency(rows) for rows in all_rows]
    currency = next((c for c in currencies if c), None)  # the newest report's currency
    if currency is None:
        raise ToolError(
            ErrorCode.NO_DATA_IN_RANGE,
            f"The ESEF reports for LEI {lei} tag no IFRS revenue or total assets.",
            "Its figures may use company-specific elements only; read the report itself.",
        )
    other_currency = sorted(
        {c for c in currencies if c and c != currency}
    )  # e.g. a change of presentation currency; those reports are not mixed in
    facts = [rows for rows, c in zip(all_rows, currencies, strict=True) if c == currency]
    profiles = [_profile(rows) for rows in facts]
    annual_rows = [rows for rows, (_, is_annual) in zip(facts, profiles, strict=True) if is_annual]
    fiscal = {(end.month, end.day) for end, is_annual in profiles if end and is_annual}

    used: dict[str, str] = {}
    for field, concepts in CONCEPTS.items():  # the newest annual report decides each element
        for scope in (annual_rows[:1], facts[:1], facts):
            present = {c for rows in scope for c, u, _, _ in rows if u == currency}
            chosen = next((c for c in concepts if c in present), None)
            if chosen:
                used[field] = chosen
                break

    # Newest report first: the first value seen for a period is kept; every value is recorded
    # to detect restatements.
    durations: dict[str, dict[tuple[dt.date, dt.date], float]] = {f: {} for f in FLOWS}
    seen: dict[str, dict[tuple[dt.date, dt.date], set[float]]] = {f: {} for f in FLOWS}
    instants: dict[tuple[str, dt.date], float] = {}
    for rows in facts:
        for concept, unit, period, value in rows:
            if unit != currency or not period:
                continue
            span = _span(period)
            if span is None:
                instants.setdefault((concept, _day_before(period)), value)
                continue
            for field in FLOWS:
                if used.get(field) == concept:
                    durations[field].setdefault(span, value)
                    seen[field].setdefault(span, set()).add(value)

    quarterly: dict[dt.date, dict[str, float | None]] = {}
    annual: dict[dt.date, dict[str, float | None]] = {}
    derived: set[dt.date] = set()
    not_derived: set[str] = set()
    for field, series in durations.items():
        restated = any(len(values) > 1 for values in seen[field].values())
        filed_quarters = {e for span in series if 80 <= _days(span) <= 100 for e in [span[1]]}
        nine_months = {k: v for k, v in series.items() if 260 <= _days(k) <= 285}
        for span, value in series.items():
            start, end = span
            if 80 <= _days(span) <= 100:
                quarterly.setdefault(end, {})[field] = value
            elif _is_year(span) and _near_fiscal_end(end, fiscal):
                annual.setdefault(end, {})[field] = value
                ytd = [(e, v) for (s, e), v in nine_months.items() if s == start and e < end]
                if not ytd or end in filed_quarters:
                    continue
                if restated:  # annual and nine-month figures may not share a basis
                    not_derived.add(field)
                    continue
                q4 = value - max(ytd)[1]
                quarterly.setdefault(end, {})[field] = None if field == "revenue" and q4 < 0 else q4
                derived.add(end)

    for table in (quarterly, annual):
        for end, row in table.items():
            for field in STOCKS:
                row[field] = instants.get((used[field], end)) if field in used else None
            row["total_debt"] = _debt(instants, end)
            for field in FLOWS:
                row.setdefault(field, None)

    def periods(table: dict[dt.date, dict[str, float | None]]) -> tuple[FinancialPeriod, ...]:
        return tuple(
            FinancialPeriod(end, table[end])
            for end in sorted(table)
            if any(table[end].get(f) is not None for f in FLOWS)
        )

    latest = documents[0][0]
    home = next((c for c in countries if currency_of(c) == currency), None)
    notes = [
        "Official source: the company's reports in ESEF (IFRS), as filed with its national "
        "regulator, via filings.xbrl.org (XBRL International). Earlier periods as restated in "
        "the latest comparatives. Elements used (chosen from the newest annual report): "
        + ", ".join(f"{k}={v}" for k, v in used.items())
        + ".",
        "ESEF requires only the annual report; quarterly figures appear only when the company "
        "also files its interim reports there. IFRS figures can differ from what the company "
        "reports under US GAAP elsewhere, e.g. to the SEC.",
        "Debt is IFRS borrowings from a complete set of elements (total, or non-current plus "
        "current parts); null when the company tags none completely.",
    ]
    if not fiscal:
        notes.append("No annual report was among the reports read, so there are no annual figures.")
    if derived:
        notes.append(
            "Fourth-quarter figures derived as annual minus nine-month year-to-date: "
            + ", ".join(d.isoformat() for d in sorted(derived)[-4:])
            + "."
        )
    if not_derived:
        notes.append(
            "Fourth quarters were not derived for "
            + ", ".join(sorted(not_derived))
            + ": the company restated some periods, so the annual and nine-month figures may "
            "not share a basis."
        )
    if other_currency:
        notes.append(
            f"Reports presented in {', '.join(other_currency)} were not used; figures are in "
            f"{currency} only."
        )
    issues = int(latest.get("inconsistency_count") or 0) + int(latest.get("error_count") or 0)
    if issues:
        notes.append(
            f"XBRL validation of the latest report found {latest.get('error_count') or 0} "
            f"error(s) and {latest.get('inconsistency_count') or 0} calculation "
            "inconsistency(ies); verify material figures in the report itself."
        )
    return FinancialStatements(
        symbol=lei,
        currency=currency,
        sector=None,
        industry=None,
        provider="esef",
        retrieved_at=retrieved_at,
        quarterly=periods(quarterly),
        annual=periods(annual),
        source_notes=tuple(notes),
        country=home,
    )


def _debt(instants: Mapping[tuple[str, dt.date], float], end: dt.date) -> float | None:
    for elements in DEBT_SETS:
        values = [instants.get((c, end)) for c in elements]
        if all(v is not None for v in values):
            return sum(v for v in values if v is not None)
    return None
