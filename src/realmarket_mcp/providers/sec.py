"""US company financial statements from SEC EDGAR's XBRL API (official, free, no key).

The SEC asks every automated client to declare who it is: the User-Agent must carry a contact
e-mail, read here from ``REALMARKET_SEC_CONTACT``. Without it (or with a URL in the agent string)
the SEC answers 403 — both verified live on 2026-09-25. Fair-access limit: 10 requests per
second; one ``financials`` call makes at most three requests.

Data comes from ``companyfacts``: every value the company tagged in its 10-Q and 10-K filings.
Quarterly income-statement values are reported for Q1-Q3 only; the fourth quarter is derived
as the annual figure minus the nine-month year-to-date figure from the same fiscal year, and
the result says which quarters were derived. When a later filing restates a period, the latest
filed value is used, so year-on-year comparisons are like for like.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from realmarket_mcp import __version__
from realmarket_mcp.contract import ErrorCode, ToolError
from realmarket_mcp.models import FinancialPeriod, FinancialStatements
from realmarket_mcp.providers import http

Fetch = Callable[[str, Mapping[str, str]], bytes]

CONTACT_ENV = "REALMARKET_SEC_CONTACT"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
MIN_INTERVAL_SECONDS = 0.15  # stays well under the SEC's 10 requests per second

# Income-statement (duration) concepts, in order of preference. One concept is used per field
# (the one with the most recent period, ties broken by this order), so quarters and years always
# describe the same total. "Revenues" is the total top line; the ASC 606 element can exclude
# revenue outside its scope.
FLOW_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "Revenues",
        "RevenuesNetOfInterestExpense",  # banks' quarterly top line (JPMorgan, verified)
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
}
# Balance-sheet (instant) concepts.
STOCK_CONCEPTS: dict[str, tuple[str, ...]] = {
    "total_assets": ("Assets",),
    "total_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
}
# Debt = long-term debt including its current portion, plus short-term borrowings. Long-term
# debt comes from the first form tagged at that date: a total, or noncurrent + current parts.
# Without any long-term figure debt is null, never short-term borrowings alone (JPMorgan has not
# tagged LongTermDebt since 2014; Coca-Cola moved to the lease-inclusive element in 2024).
LONG_TERM_DEBT: tuple[tuple[str, str | None], ...] = (
    ("LongTermDebt", None),
    ("LongTermDebtNoncurrent", "LongTermDebtCurrent"),
    ("LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent"),
)
# ShortTermBorrowings usually includes commercial paper (Coca-Cola), so commercial paper is
# used only when no ShortTermBorrowings figure exists; the two are never added.
SHORT_TERM_DEBT = ("ShortTermBorrowings", "CommercialPaper")

FORMS = frozenset(
    {"10-Q", "10-Q/A", "10-K", "10-K/A", "10-KT", "10-KT/A", "20-F", "20-F/A", "40-F", "40-F/A"}
)
QUARTER_DAYS = (80, 100)
YEAR_DAYS = (350, 380)
NINE_MONTH_DAYS = (260, 285)

_CIK = re.compile(r"^(?:CIK)?0*(\d{1,10})$", re.IGNORECASE)
_CIK_PREFIXED = re.compile(r"^CIK\d{1,10}$", re.IGNORECASE)

_lock = threading.Lock()
_last_request = 0.0
_tickers: dict[str, int] | None = None


def contact_from(env: Mapping[str, str]) -> str | None:
    value = env.get(CONTACT_ENV, "").strip()
    return value or None


def user_agent(contact: str) -> str:
    # No URL here: the SEC rejects agent strings that contain one (verified 2026-09-25).
    return f"realmarket-mcp/{__version__} {contact}"


def looks_like_us_symbol(symbol: str) -> bool:
    """A bare ticker (``AAPL``, ``BRK-B``) or a ``CIK``-prefixed number; not ``THYAO.IS``,
    ``VOD.L``, ``^GSPC``, ``EURUSD=X``, ``GC=F`` or a bare number such as ``7203`` (Tokyo),
    which could collide with an unrelated company's CIK."""
    s = symbol.strip().upper()
    if _CIK_PREFIXED.match(s):
        return True
    return re.fullmatch(r"[A-Z]{1,5}(?:-[A-Z]{1,2})?", s) is not None


class SecEdgarProvider:
    name = "sec_edgar"

    def __init__(self, contact: str, *, retrieved_at: str, fetch: Fetch | None = None) -> None:
        if "@" not in contact:
            raise ToolError(
                ErrorCode.MISSING_API_KEY,
                "The SEC requires a contact e-mail address in every automated request.",
                f"Set {CONTACT_ENV} to your e-mail address in the MCP server's environment. "
                "No sign-up is needed; the SEC uses it only to reach you about traffic.",
            )
        self._headers = {"User-Agent": user_agent(contact)}
        self._retrieved_at = retrieved_at
        self._fetch = fetch or _default_fetch

    def _json(self, url: str) -> Any:
        body = self._fetch(url, self._headers)
        try:
            return json.loads(body)
        except (UnicodeDecodeError, ValueError):
            raise http.unavailable("SEC EDGAR", "unreadable response") from None

    def resolve_cik(self, symbol: str) -> int:
        s = symbol.strip().upper()
        match = _CIK.match(s)
        if match:
            return int(match.group(1))
        global _tickers
        if _tickers is None:
            try:
                rows = self._json(TICKERS_URL)
            except ToolError as error:
                raise ToolError(
                    error.code,
                    f"The SEC ticker list could not be read ({error.message})",
                    "Retry shortly, or pass the company's CIK instead, e.g. CIK0000320193 for "
                    "Apple (look it up on the SEC's EDGAR company search).",
                ) from None
            _tickers = {
                str(r["ticker"]).upper(): int(r["cik_str"])
                for r in (rows.values() if isinstance(rows, dict) else rows)
            }
        cik = _tickers.get(s) or _tickers.get(s.replace(".", "-"))
        if cik is None:
            raise ToolError(
                ErrorCode.UNKNOWN_SYMBOL,
                f"{symbol} is not in the SEC's list of reporting companies.",
                "Use a US-listed ticker such as AAPL, or the company's CIK. Non-US companies "
                "are covered by the price provider's statements, not by the SEC.",
            )
        return cik

    def financials(self, symbol: str) -> FinancialStatements:
        cik = self.resolve_cik(symbol)
        no_facts = ToolError(
            ErrorCode.NO_DATA_IN_RANGE,
            f"The SEC holds no XBRL financial data for {symbol}.",
            "Funds, trusts and some foreign issuers file no tagged statements.",
        )
        facts = self._json_or(FACTS_URL.format(cik=cik), no_facts)
        try:
            submissions = self._json(SUBMISSIONS_URL.format(cik=cik))
        except ToolError:
            submissions = {}
        return parse_company_facts(
            facts,
            symbol=symbol.strip().upper(),
            industry=submissions.get("sicDescription") or None,
            retrieved_at=self._retrieved_at,
        )

    def _json_or(self, url: str, not_found: ToolError) -> Any:
        try:
            return self._json(url)
        except ToolError as error:
            if error is NOT_FOUND:
                raise not_found from None
            raise


def _default_fetch(url: str, headers: Mapping[str, str]) -> bytes:
    global _last_request
    with _lock:
        wait = _last_request + MIN_INTERVAL_SECONDS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
    forbidden = ToolError(
        ErrorCode.MISSING_API_KEY,
        "The SEC refused the request (HTTP 403).",
        f"Set {CONTACT_ENV} to a real e-mail address; the SEC blocks undeclared automated "
        "clients. If it is set, wait ten minutes: the SEC also blocks bursts of traffic.",
    )
    return http.get(url, headers, source="SEC EDGAR", not_found=NOT_FOUND, forbidden=forbidden)


# Raised by a fetch for HTTP 404; callers translate it into a message about the company.
NOT_FOUND = ToolError(
    ErrorCode.NO_DATA_IN_RANGE, "SEC EDGAR has no such document.", "Check the ticker or CIK."
)


# --- parsing --------------------------------------------------------------------------------


def _days(fact: Mapping[str, Any]) -> int | None:
    start = fact.get("start")
    if not start:
        return None
    return (dt.date.fromisoformat(fact["end"]) - dt.date.fromisoformat(start)).days


Filings = dict[tuple[str | None, str], list[tuple[str, float]]]


def _by_period(facts: list[dict[str, Any]]) -> Filings:
    """Every filed value per (start, end), oldest filing first."""
    out: Filings = {}
    for fact in facts:
        if fact.get("form") not in FORMS or not isinstance(fact.get("val"), int | float):
            continue
        out.setdefault((fact.get("start"), fact["end"]), []).append(
            (str(fact.get("filed", "")), float(fact["val"]))
        )
    for values in out.values():
        values.sort(key=lambda item: item[0])  # stable: same-day values keep source order
    return out


def _pick_unit(gaap: Mapping[str, Any]) -> str:
    """The reporting currency: the ISO currency unit with the most facts (USD on a tie)."""
    counts: dict[str, int] = {}
    for concept in ("Assets", *FLOW_CONCEPTS["revenue"], "NetIncomeLoss"):
        for unit, facts in gaap.get(concept, {}).get("units", {}).items():
            if re.fullmatch(r"[A-Z]{3}", unit):
                counts[unit] = counts.get(unit, 0) + len(facts)
    if not counts:
        return "USD"
    return max(sorted(counts), key=lambda u: (counts[u], u == "USD"))


def _filings(gaap: Mapping[str, Any], concept: str, unit: str) -> Filings:
    return _by_period(gaap.get(concept, {}).get("units", {}).get(unit, []))


def _in(days: int | None, bounds: tuple[int, int]) -> bool:
    return days is not None and bounds[0] <= days <= bounds[1]


def _duration(start: str | None, end: str) -> int | None:
    return _days({"start": start, "end": end})


def _flow_periods(
    filings: Filings, *, non_negative: bool
) -> tuple[dict[str, float | None], dict[str, float], set[str], set[str]]:
    """Quarter and fiscal-year values keyed by end date (latest filing wins, so restatements
    are used), plus the derived quarter ends and those whose fiscal year was restated.

    A fourth quarter is derived from the FIRST-reported annual and nine-month figures, which
    share one basis. Pairing a recast annual figure with a nine-month figure filed before the
    recast would push the whole year's reclassification into the fourth quarter.
    """
    quarters: dict[str, float | None] = {}
    years: dict[str, float] = {}
    nine_months: dict[tuple[str, str], float] = {}
    for (start, end), values in filings.items():
        days = _duration(start, end)
        if _in(days, QUARTER_DAYS):
            quarters[end] = values[-1][1]
        elif _in(days, YEAR_DAYS):
            years[end] = values[-1][1]
        elif _in(days, NINE_MONTH_DAYS) and start:
            nine_months[(start, end)] = values[0][1]
    derived: set[str] = set()
    restated: set[str] = set()
    for (start, end), values in filings.items():
        if not _in(_duration(start, end), YEAR_DAYS) or end in quarters:
            continue
        ytd = [(e, v) for (s, e), v in nine_months.items() if s == start and e < end]
        if not ytd:
            continue
        value = values[0][1] - max(ytd)[1]
        quarters[end] = None if non_negative and value < 0 else value
        derived.add(end)
        if values[-1][1] != values[0][1]:
            restated.add(end)
    return quarters, years, derived, restated


def _latest(gaap: Mapping[str, Any], concept: str, unit: str) -> str:
    return max((end for _, end in _filings(gaap, concept, unit)), default="")


def _choose(gaap: Mapping[str, Any], concepts: tuple[str, ...], unit: str) -> str | None:
    """The concept with the most recent period; earlier in ``concepts`` wins a tie."""
    ranked = [(_latest(gaap, c, unit), -i, c) for i, c in enumerate(concepts)]
    best = max(ranked)
    return best[2] if best[0] else None


def _instants(gaap: Mapping[str, Any], concept: str, unit: str) -> dict[str, float]:
    return {end: v[-1][1] for (start, end), v in _filings(gaap, concept, unit).items() if not start}


def _debt(gaap: Mapping[str, Any], unit: str, end: str) -> float | None:
    long_term: float | None = None
    for total_or_noncurrent, current in LONG_TERM_DEBT:
        base = _instants(gaap, total_or_noncurrent, unit).get(end)
        if base is not None:
            extra = _instants(gaap, current, unit).get(end) if current else None
            long_term = base + (extra or 0.0)
            break
    if long_term is None:
        return None
    short = next(
        (v for c in SHORT_TERM_DEBT if (v := _instants(gaap, c, unit).get(end)) is not None),
        0.0,
    )
    return long_term + short


def parse_company_facts(
    payload: Mapping[str, Any], *, symbol: str, industry: str | None, retrieved_at: str
) -> FinancialStatements:
    gaap = payload.get("facts", {}).get("us-gaap")
    if not gaap:
        raise ToolError(
            ErrorCode.NO_DATA_IN_RANGE,
            f"{symbol} files no US GAAP statements with the SEC.",
            "Foreign issuers reporting under IFRS (Form 20-F) are not covered by this source.",
        )
    unit = _pick_unit(gaap)
    quarterly: dict[str, dict[str, float | None]] = {}
    annual: dict[str, dict[str, float | None]] = {}
    derived_quarters: set[str] = set()
    restated_years: set[str] = set()
    used: dict[str, str] = {}
    for field, concepts in FLOW_CONCEPTS.items():
        chosen = _choose(gaap, concepts, unit)
        if chosen is None:
            continue
        used[field] = chosen
        quarters, years, derived, restated = _flow_periods(
            _filings(gaap, chosen, unit), non_negative=field == "revenue"
        )
        derived_quarters |= derived
        restated_years |= restated
        for end, value in quarters.items():
            quarterly.setdefault(end, {})[field] = value
        for end, amount in years.items():
            annual.setdefault(end, {})[field] = amount
    for rows in (quarterly, annual):
        for end, values in rows.items():
            for field in FLOW_CONCEPTS:
                values.setdefault(field, None)
            for field, concepts in STOCK_CONCEPTS.items():
                values[field] = next(
                    (v for c in concepts if (v := _instants(gaap, c, unit).get(end)) is not None),
                    None,
                )
            values["total_debt"] = _debt(gaap, unit, end)

    def periods(rows: dict[str, dict[str, float | None]]) -> tuple[FinancialPeriod, ...]:
        return tuple(FinancialPeriod(dt.date.fromisoformat(end), rows[end]) for end in sorted(rows))

    notes = [
        "Official source: the company's own XBRL-tagged 10-Q and 10-K filings, via SEC EDGAR "
        "(data.sec.gov). Figures are as tagged; the latest filing's value is used when a period "
        "was restated. US GAAP elements used: "
        + ", ".join(f"{field}={name}" for field, name in used.items())
        + ".",
        "Debt is long-term debt (including its current portion, and finance leases where the "
        "company tags them together) plus short-term borrowings; null when the company tags no "
        "long-term debt figure.",
    ]
    if derived_quarters:
        notes.append(
            "Fourth-quarter income figures are not filed separately; these quarter ends were "
            "derived as the first-reported annual minus nine-month year-to-date figure, so the "
            "quarter-to-year reconciliation for those years mainly checks Q1-Q3 against the "
            "nine-month figure: " + ", ".join(sorted(derived_quarters)[-4:]) + "."
        )
    recent_restated = sorted(e for e in restated_years if e in set(sorted(annual)[-4:]))
    if recent_restated:
        notes.append(
            "These fiscal years were restated after first filing; their derived fourth quarter "
            "is on the originally reported basis while the annual figure is restated: "
            + ", ".join(recent_restated)
            + "."
        )
    return FinancialStatements(
        symbol=symbol,
        currency=unit,
        sector=None,
        industry=industry,
        provider="sec_edgar",
        retrieved_at=retrieved_at,
        quarterly=periods(quarterly),
        annual=periods(annual),
        source_notes=tuple(notes),
    )
